import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
from zoneinfo import ZoneInfo
import asyncio
import sqlite3
import os


# =========================================================
# 기본 설정
# =========================================================

TOKEN = os.environ.get("DISCORD_TOKEN")

# 포럼 채널 ID
FORUM_CHANNEL_ID = 1478583260580937791

# 와드박스 서버 ID
GUILD_ID = 1470812966705168598

# 매일 자동으로 모집글을 올리는 시간 (한국 시간)
POST_UPLOAD_TIME = time(hour=12, minute=0)

# 자동 모집글의 기본 내전 시작 시간
MATCH_START_TIME = time(hour=20, minute=30)

# 최대 참여 인원
MAX_PLAYERS = 10

# 관리자 역할 ID
# 특정 관리자 역할을 멘션하고 싶으면 역할 ID 입력
# 필요 없으면 0 그대로 사용
ADMIN_ROLE_ID = 0

# SQLite 파일
# Railway Volume을 /data에 연결한 경우:
# Variables에 DB_PATH=/data/wardbox.db 입력하면 됨
DB_PATH = os.environ.get("DB_PATH", "wardbox.db")


# =========================================================
# Discord 설정
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# 데이터베이스
# =========================================================

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_database():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            message_id INTEGER PRIMARY KEY,
            thread_id INTEGER NOT NULL,
            match_time TEXT NOT NULL,
            title TEXT NOT NULL,
            created_date TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (message_id, user_id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS auto_posts (
            post_date TEXT PRIMARY KEY
        )
    """)

    db.commit()
    db.close()

    print("✅ 데이터베이스 준비 완료")


def get_match(message_id: int):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM matches
        WHERE message_id = ?
        """,
        (message_id,)
    ).fetchone()

    db.close()

    return row


def get_players(message_id: int, status: str):
    db = get_db()

    rows = db.execute(
        """
        SELECT user_id, display_name
        FROM participants
        WHERE message_id = ?
        AND status = ?
        ORDER BY rowid
        """,
        (message_id, status)
    ).fetchall()

    db.close()

    return rows


def get_player_count(message_id: int, status: str):
    db = get_db()

    count = db.execute(
        """
        SELECT COUNT(*)
        FROM participants
        WHERE message_id = ?
        AND status = ?
        """,
        (message_id, status)
    ).fetchone()[0]

    db.close()

    return count


def set_player_status(
    message_id: int,
    user_id: int,
    display_name: str,
    status: str
):
    db = get_db()

    db.execute(
        """
        INSERT INTO participants (
            message_id,
            user_id,
            display_name,
            status
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(message_id, user_id)
        DO UPDATE SET
            display_name = excluded.display_name,
            status = excluded.status
        """,
        (
            message_id,
            user_id,
            display_name,
            status
        )
    )

    db.commit()
    db.close()


def remove_player(message_id: int, user_id: int):
    db = get_db()

    cursor = db.execute(
        """
        DELETE FROM participants
        WHERE message_id = ?
        AND user_id = ?
        """,
        (
            message_id,
            user_id
        )
    )

    removed = cursor.rowcount > 0

    db.commit()
    db.close()

    return removed


def get_player_status(message_id: int, user_id: int):
    db = get_db()

    row = db.execute(
        """
        SELECT status
        FROM participants
        WHERE message_id = ?
        AND user_id = ?
        """,
        (
            message_id,
            user_id
        )
    ).fetchone()

    db.close()

    if row:
        return row["status"]

    return None


def save_match(
    message_id: int,
    thread_id: int,
    match_time: str,
    title: str,
    created_date: str
):
    db = get_db()

    db.execute(
        """
        INSERT OR REPLACE INTO matches (
            message_id,
            thread_id,
            match_time,
            title,
            created_date
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            message_id,
            thread_id,
            match_time,
            title,
            created_date
        )
    )

    db.commit()
    db.close()


def was_auto_posted_today(date_string: str):
    db = get_db()

    row = db.execute(
        """
        SELECT post_date
        FROM auto_posts
        WHERE post_date = ?
        """,
        (date_string,)
    ).fetchone()

    db.close()

    return row is not None


def mark_auto_posted(date_string: str):
    db = get_db()

    db.execute(
        """
        INSERT OR IGNORE INTO auto_posts (post_date)
        VALUES (?)
        """,
        (date_string,)
    )

    db.commit()
    db.close()


# =========================================================
# 내전 현황판 Embed
# =========================================================

def make_match_embed(message_id: int):
    match = get_match(message_id)

    if not match:
        return discord.Embed(
            title="❌ 내전 정보를 찾을 수 없습니다.",
            description="봇 데이터에 해당 내전이 존재하지 않습니다."
        )

    participants = get_players(
        message_id,
        "participant"
    )

    waiting = get_players(
        message_id,
        "waiting"
    )

    if participants:
        participant_text = "\n".join(
            f"• {row['display_name']}"
            for row in participants
        )
    else:
        participant_text = "아직 아무도 없습니다"

    if waiting:
        waiting_text = "\n".join(
            f"• {row['display_name']}"
            for row in waiting
        )
    else:
        waiting_text = "대기 인원이 없습니다"

    embed = discord.Embed(
        title="🕘 와드박스 협곡 내전 정보",
        description=(
            f"시작 시간 : **{match['match_time']}**"
        )
    )

    embed.add_field(
        name=(
            f"👍 내전 참여 "
            f"({len(participants)}/{MAX_PLAYERS})"
        ),
        value=participant_text,
        inline=False
    )

    embed.add_field(
        name=f"🕒 대기열 ({len(waiting)})",
        value=waiting_text,
        inline=False
    )

    embed.add_field(
        name="💌 안내",
        value=(
            f"내전 인원 {MAX_PLAYERS}명이 모두 모이면 "
            "👑 관리자 호출 버튼을 눌러주세요!"
        ),
        inline=False
    )

    return embed


# =========================================================
# 버튼 View
#
# 중요:
# 참가자 데이터를 self 안에 저장하지 않음.
# interaction.message.id를 이용해서 DB에서 불러옴.
#
# 그래서 봇이 재시작되어도 버튼이 다시 작동함.
# =========================================================

class MatchView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)


    # =====================================================
    # ✅ 내전 참여
    # =====================================================

    @discord.ui.button(
        label="✅ 내전 참여",
        style=discord.ButtonStyle.success,
        custom_id="wardbox_match_join"
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        message_id = interaction.message.id
        user_id = interaction.user.id
        name = interaction.user.display_name

        match = get_match(message_id)

        if not match:
            await interaction.response.send_message(
                "❌ 이 내전의 데이터를 찾을 수 없어요.",
                ephemeral=True
            )
            return

        current_status = get_player_status(
            message_id,
            user_id
        )

        if current_status == "participant":
            await interaction.response.send_message(
                "✅ 이미 내전에 참여 중이에요!",
                ephemeral=True
            )
            return

        participant_count = get_player_count(
            message_id,
            "participant"
        )

        # 이미 10명이라면 자동으로 대기열
        if participant_count >= MAX_PLAYERS:

            set_player_status(
                message_id,
                user_id,
                name,
                "waiting"
            )

            await interaction.response.edit_message(
                embed=make_match_embed(message_id),
                view=self
            )

            await interaction.followup.send(
                "🕒 참여 인원이 가득 차서 대기열에 등록했어요!",
                ephemeral=True
            )

            return

        set_player_status(
            message_id,
            user_id,
            name,
            "participant"
        )

        await interaction.response.edit_message(
            embed=make_match_embed(message_id),
            view=self
        )


    # =====================================================
    # 📣 대기열 등록
    # =====================================================

    @discord.ui.button(
        label="📣 대기열 소집",
        style=discord.ButtonStyle.primary,
        custom_id="wardbox_match_wait"
    )
    async def waiting_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        message_id = interaction.message.id
        user_id = interaction.user.id
        name = interaction.user.display_name

        match = get_match(message_id)

        if not match:
            await interaction.response.send_message(
                "❌ 이 내전의 데이터를 찾을 수 없어요.",
                ephemeral=True
            )
            return

        current_status = get_player_status(
            message_id,
            user_id
        )

        if current_status == "waiting":
            await interaction.response.send_message(
                "🕒 이미 대기열에 등록되어 있어요!",
                ephemeral=True
            )
            return

        set_player_status(
            message_id,
            user_id,
            name,
            "waiting"
        )

        await interaction.response.edit_message(
            embed=make_match_embed(message_id),
            view=self
        )


    # =====================================================
    # ❌ 참여 / 대기 취소
    # =====================================================

    @discord.ui.button(
        label="❌ 대기열 삭제",
        style=discord.ButtonStyle.danger,
        custom_id="wardbox_match_leave"
    )
    async def leave_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        message_id = interaction.message.id
        user_id = interaction.user.id

        match = get_match(message_id)

        if not match:
            await interaction.response.send_message(
                "❌ 이 내전의 데이터를 찾을 수 없어요.",
                ephemeral=True
            )
            return

        removed = remove_player(
            message_id,
            user_id
        )

        if not removed:
            await interaction.response.send_message(
                "현재 참여 또는 대기 목록에 등록되어 있지 않아요.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            embed=make_match_embed(message_id),
            view=self
        )


    # =====================================================
    # 👑 관리자 호출
    # =====================================================

    @discord.ui.button(
        label="👑 관리자 호출",
        style=discord.ButtonStyle.secondary,
        custom_id="wardbox_match_admin"
    )
    async def admin_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        message_id = interaction.message.id

        match = get_match(message_id)

        if not match:
            await interaction.response.send_message(
                "❌ 이 내전의 데이터를 찾을 수 없어요.",
                ephemeral=True
            )
            return

        participant_count = get_player_count(
            message_id,
            "participant"
        )

        if participant_count < MAX_PLAYERS:

            await interaction.response.send_message(
                (
                    f"현재 참여자가 **{participant_count}명**이에요.\n"
                    f"{MAX_PLAYERS}명이 모두 모인 뒤 호출해주세요!"
                ),
                ephemeral=True
            )

            return

        # 관리자 역할을 지정한 경우
        if ADMIN_ROLE_ID:

            admin_mention = f"<@&{ADMIN_ROLE_ID}>"

            await interaction.response.send_message(
                (
                    f"{admin_mention}\n"
                    f"👑 **내전 인원 {MAX_PLAYERS}명이 모두 모였습니다!**\n"
                    "내전 진행을 준비해주세요."
                ),
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                )
            )

        else:

            await interaction.response.send_message(
                (
                    f"👑 **내전 인원 {MAX_PLAYERS}명이 모두 모였습니다!**\n"
                    "관리자분들은 내전 진행을 준비해주세요."
                )
            )


# =========================================================
# 포럼 내전글 생성
#
# 자동 / /내전모집 모두 이 함수를 사용
# =========================================================

async def create_match_post(
    match_time: str,
    manual: bool = False
):

    channel = bot.get_channel(
        FORUM_CHANNEL_ID
    )

    # 캐시에 없으면 API로 한번 더 가져오기
    if channel is None:
        try:
            channel = await bot.fetch_channel(
                FORUM_CHANNEL_ID
            )
        except Exception as e:
            print(
                f"❌ 포럼 채널 불러오기 실패: "
                f"{type(e).__name__}: {e}"
            )
            return None

    if not isinstance(
        channel,
        discord.ForumChannel
    ):
        print(
            "❌ FORUM_CHANNEL_ID가 "
            "포럼 채널이 아닙니다."
        )
        return None

    now = datetime.now(
        ZoneInfo("Asia/Seoul")
    )

    days = [
        "월",
        "화",
        "수",
        "목",
        "금",
        "토",
        "일"
    ]

    date_str = now.strftime("%m/%d")
    db_date = now.strftime("%Y-%m-%d")
    weekday = days[now.weekday()]

    title = (
        f"📢 {date_str} ({weekday}) "
        f"{match_time} 협곡 내전 모집"
    )

    try:

        # -------------------------------------------------
        # 1. 포럼 게시글 생성
        # -------------------------------------------------

        result = await channel.create_thread(
            name=title,
            content=(
                "@everyone\n"
                f"🎮 **{title}**\n\n"
                "아래 현황판의 버튼을 눌러 참여해주세요!"
            ),
            allowed_mentions=discord.AllowedMentions(
                everyone=True
            )
        )

        thread = result.thread

        print(
            f"✅ 포럼 생성 완료: {title}"
        )

        # -------------------------------------------------
        # 2. 우선 현황 메시지를 버튼 없이 전송
        #
        # 메시지 ID가 있어야 DB에 내전을 저장할 수 있음.
        # -------------------------------------------------

        temp_embed = discord.Embed(
            title="🕘 와드박스 협곡 내전 정보",
            description=f"시작 시간 : **{match_time}**"
        )

        temp_embed.add_field(
            name=f"👍 내전 참여 (0/{MAX_PLAYERS})",
            value="아직 아무도 없습니다",
            inline=False
        )

        temp_embed.add_field(
            name="🕒 대기열 (0)",
            value="대기 인원이 없습니다",
            inline=False
        )

        temp_embed.add_field(
            name="💌 안내",
            value=(
                f"내전 인원 {MAX_PLAYERS}명이 모두 모이면 "
                "👑 관리자 호출 버튼을 눌러주세요!"
            ),
            inline=False
        )

        vote_message = await thread.send(
            embed=temp_embed
        )

        # -------------------------------------------------
        # 3. 내전 정보를 DB 저장
        # -------------------------------------------------

        save_match(
            message_id=vote_message.id,
            thread_id=thread.id,
            match_time=match_time,
            title=title,
            created_date=db_date
        )

        # -------------------------------------------------
        # 4. 저장 완료 후 버튼 활성화
        # -------------------------------------------------

        await vote_message.edit(
            embed=make_match_embed(
                vote_message.id
            ),
            view=MatchView()
        )

        print(
            f"✅ 내전 현황판 생성 완료 "
            f"(message_id={vote_message.id})"
        )

        return thread


    except Exception as e:

        print(
            f"❌ 내전 모집 생성 오류: "
            f"{type(e).__name__}: {e}"
        )

        return None


# =========================================================
# /내전모집
# =========================================================

@bot.tree.command(
    name="내전모집",
    description="와드박스 협곡 내전 모집글을 생성합니다."
)
@app_commands.describe(
    시간="내전 시작 시간 (예: 20:30)"
)
async def manual_match(
    interaction: discord.Interaction,
    시간: str = "20:30"
):

    # 서버 관리 권한 사용자만 실행
    if (
        not isinstance(
            interaction.user,
            discord.Member
        )
        or
        not interaction.user.guild_permissions.manage_guild
    ):

        await interaction.response.send_message(
            "❌ 서버 관리 권한이 있는 사용자만 사용할 수 있어요.",
            ephemeral=True
        )
        return

    # HH:MM 검증
    try:
        parsed_time = datetime.strptime(
            시간,
            "%H:%M"
        )

        # 입력값을 0패딩된 HH:MM으로 통일
        시간 = parsed_time.strftime(
            "%H:%M"
        )

    except ValueError:

        await interaction.response.send_message(
            "❌ 시간은 `20:30`처럼 입력해주세요.",
            ephemeral=True
        )
        return

    # Discord Interaction 3초 제한 대응
    await interaction.response.defer(
    ephemeral=True,
    thinking=True
)

try:
    result = await create_match_post(
        match_time=시간,
        manual=True
    )

    if result:
        await interaction.followup.send(
            f"✅ **{시간} 협곡 내전 모집글**을 생성했습니다!",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ 모집글 생성에 실패했습니다. Railway 로그를 확인해주세요.",
            ephemeral=True
        )

except Exception as e:
    print(
        f"❌ /내전모집 오류: "
        f"{type(e).__name__}: {e}"
    )

    await interaction.followup.send(
        f"❌ 내전 모집 처리 중 오류가 발생했습니다: `{type(e).__name__}`",
        ephemeral=True
    )

    result = await create_match_post(
        match_time=시간,
        manual=True
    )

    if result:

        await interaction.followup.send(
            f"✅ **{시간} 협곡 내전 모집글**을 생성했습니다!",
            ephemeral=True
        )

    else:

        await interaction.followup.send(
            (
                "❌ 모집글 생성에 실패했습니다.\n"
                "Railway Deploy Logs를 확인해주세요."
            ),
            ephemeral=True
        )


# =========================================================
# 자동 내전 모집
# =========================================================

@tasks.loop(minutes=1)
async def daily_match_post():

    now = datetime.now(
        ZoneInfo("Asia/Seoul")
    )

    if (
        now.hour == POST_UPLOAD_TIME.hour
        and
        now.minute == POST_UPLOAD_TIME.minute
    ):

        today = now.strftime(
            "%Y-%m-%d"
        )

        # Railway 재시작 등으로 같은 날
        # 자동글이 중복 생성되는 것 방지
        if was_auto_posted_today(today):

            print(
                f"ℹ️ {today} 자동 모집글은 "
                "이미 생성되었습니다."
            )

            await asyncio.sleep(60)
            return

        match_time = MATCH_START_TIME.strftime(
            "%H:%M"
        )

        result = await create_match_post(
            match_time=match_time,
            manual=False
        )

        if result:

            mark_auto_posted(today)

            print(
                f"✅ {today} 자동 모집글 완료"
            )

        # 같은 분 중복 실행 방지
        await asyncio.sleep(60)


@daily_match_post.before_loop
async def before_daily_post():

    await bot.wait_until_ready()


# =========================================================
# 봇 실행 준비
# =========================================================

@bot.event
async def setup_hook():

    # -----------------------------------------------------
    # 핵심 수정 부분
    #
    # Railway가 재시작되어도 기존 Discord 버튼을
    # 다시 처리할 수 있도록 Persistent View 등록
    # -----------------------------------------------------

    bot.add_view(
        MatchView()
    )

    print(
        "✅ Persistent 버튼 등록 완료"
    )

    # DB 초기화
    init_database()

    # 슬래시 명령어 동기화
    guild = discord.Object(
        id=GUILD_ID
    )

    bot.tree.copy_global_to(
        guild=guild
    )

    synced = await bot.tree.sync(
        guild=guild
    )

    print(
        f"✅ 슬래시 명령어 "
        f"{len(synced)}개 동기화 완료"
    )


# =========================================================
# 봇 로그인 완료
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ {bot.user} 로그인 완료"
    )

    print(
        f"✅ 봇 ID: {bot.user.id}"
    )

    print(
        "✅ 한국 시간: "
        f"{datetime.now(ZoneInfo('Asia/Seoul'))}"
    )

    if not daily_match_post.is_running():

        daily_match_post.start()

        print(
            "✅ 자동 내전 모집 스케줄 시작"
        )


# =========================================================
# 실행
# =========================================================

if TOKEN is None:

    raise RuntimeError(
        "❌ DISCORD_TOKEN 환경변수가 없습니다."
    )


bot.run(TOKEN)
