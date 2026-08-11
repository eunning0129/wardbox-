import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
from zoneinfo import ZoneInfo
import asyncio
import os


# =========================================================
# 기본 설정
# =========================================================

TOKEN = os.environ.get("DISCORD_TOKEN")

# 포럼 채널 ID
FORUM_CHANNEL_ID = 1478583260580937791

# 봇을 사용하는 서버 ID
# 슬래시 명령어를 빠르게 등록하기 위해 사용
GUILD_ID = 1470812966705168598

# 자동 모집글 업로드 시간
POST_UPLOAD_TIME = time(hour=12, minute=0)

# 기본 내전 시작 시간
MATCH_START_TIME = time(hour=20, minute=30)

# 내전 최대 인원
MAX_PLAYERS = 10


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# 내전 현황판
# =========================================================

class MatchView(discord.ui.View):

    def __init__(self, match_time: str):
        super().__init__(timeout=None)

        self.match_time = match_time

        # user_id : display_name
        self.participants = {}

        self.waiting = {}


    # -----------------------------------------------------
    # 현황판 내용 만들기
    # -----------------------------------------------------

    def make_embed(self):

        embed = discord.Embed(
            title="🕘 와드박스 모바시 내전 정보",
            description=f"시작 시간 : {self.match_time}",
        )

        # 참여자
        if self.participants:

            participant_text = "\n".join(
                f"• {name}"
                for name in self.participants.values()
            )

        else:
            participant_text = "아직 아무도 없습니다"


        embed.add_field(
            name=f"👍 모바시 참여 ({len(self.participants)}/{MAX_PLAYERS})",
            value=participant_text,
            inline=False
        )


        # 대기열
        if self.waiting:

            waiting_text = "\n".join(
                f"• {name}"
                for name in self.waiting.values()
            )

        else:
            waiting_text = "대기 인원이 없습니다"


        embed.add_field(
            name=f"🕒 대기열 ({len(self.waiting)})",
            value=waiting_text,
            inline=False
        )


        embed.add_field(
            name="💌 안내",
            value="모바시 10인이 모이면 관리자 호출을 눌러주세요!",
            inline=False
        )

        return embed


    # =====================================================
    # 참여 버튼
    # =====================================================

    @discord.ui.button(
        label="✅ 내전 참여",
        style=discord.ButtonStyle.success,
        custom_id="wardbox_join"
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id
        name = interaction.user.display_name


        # 이미 참여 중
        if user_id in self.participants:

            await interaction.response.send_message(
                "이미 내전에 참여하고 있어요!",
                ephemeral=True
            )

            return


        # 10명 꽉 찼으면 대기열로
        if len(self.participants) >= MAX_PLAYERS:

            self.waiting[user_id] = name

            await interaction.response.edit_message(
                embed=self.make_embed(),
                view=self
            )

            return


        # 대기열에 있었다면 제거
        self.waiting.pop(user_id, None)

        self.participants[user_id] = name


        await interaction.response.edit_message(
            embed=self.make_embed(),
            view=self
        )


    # =====================================================
    # 대기열 모집 버튼
    # =====================================================

    @discord.ui.button(
        label="📣 대기열 소집",
        style=discord.ButtonStyle.primary,
        custom_id="wardbox_wait"
    )
    async def waiting_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id
        name = interaction.user.display_name


        # 참여 목록에서 제거
        self.participants.pop(user_id, None)

        # 대기열 추가
        self.waiting[user_id] = name


        await interaction.response.edit_message(
            embed=self.make_embed(),
            view=self
        )


    # =====================================================
    # 대기열 삭제 버튼
    # =====================================================

    @discord.ui.button(
        label="❌ 대기열 삭제",
        style=discord.ButtonStyle.danger,
        custom_id="wardbox_leave"
    )
    async def leave_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        user_id = interaction.user.id

        removed = False


        if user_id in self.participants:

            del self.participants[user_id]

            removed = True


        if user_id in self.waiting:

            del self.waiting[user_id]

            removed = True


        if not removed:

            await interaction.response.send_message(
                "현재 참여 또는 대기 목록에 등록되어 있지 않아요.",
                ephemeral=True
            )

            return


        await interaction.response.edit_message(
            embed=self.make_embed(),
            view=self
        )


    # =====================================================
    # 관리자 호출
    # =====================================================

    @discord.ui.button(
        label="👑 관리자 호출",
        style=discord.ButtonStyle.secondary,
        custom_id="wardbox_admin"
    )
    async def admin_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if len(self.participants) < MAX_PLAYERS:

            await interaction.response.send_message(
                f"현재 참여자가 {len(self.participants)}명입니다.\n"
                f"{MAX_PLAYERS}명이 모인 뒤 호출해주세요!",
                ephemeral=True
            )

            return


        await interaction.response.send_message(
            "👑 관리자님! 내전 인원이 모두 모였습니다!"
        )


# =========================================================
# 내전 포럼 생성 함수
# 자동 / 수동에서 공통으로 사용
# =========================================================

async def create_match_post(
    match_time: str,
    manual=False
):

    channel = bot.get_channel(FORUM_CHANNEL_ID)


    if not isinstance(channel, discord.ForumChannel):

        print("포럼 채널을 찾을 수 없습니다.")

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

    weekday = days[now.weekday()]


    title = (
        f"📢 {date_str} ({weekday}) "
        f"{match_time} 협곡 내전 모집"
    )


    try:

        # 포럼 생성
        thread = await channel.create_thread(

            name=title,

            content=(
                "@everyone\n"
                f"🎮 **{title}**\n\n"
                "아래 버튼을 눌러 참여해주세요!"
            ),

            allowed_mentions=discord.AllowedMentions(
                everyone=True
            )
        )


        # 현황판
        view = MatchView(match_time)


        await thread.thread.send(
            embed=view.make_embed(),
            view=view
        )


        print(
            f"내전 모집글 생성 완료: {title}"
        )


        return thread.thread


    except Exception as e:

        print(
            f"내전 모집 생성 오류: "
            f"{type(e).__name__}: {e}"
        )

        return None


# =========================================================
# /내전모집 슬래시 명령어
# =========================================================

@bot.tree.command(
    name="내전모집",
    description="와드박스 내전 모집글을 수동으로 생성합니다."
)

@app_commands.describe(
    시간="내전 시작 시간 (예: 20:30)"
)

async def manual_match(
    interaction: discord.Interaction,
    시간: str = "20:30"
):

    # 관리자만 사용 가능
    if not interaction.user.guild_permissions.manage_guild:

        await interaction.response.send_message(
            "❌ 서버 관리 권한이 있는 사용자만 사용할 수 있어요.",
            ephemeral=True
        )

        return


    # HH:MM 형식 검사
    try:

        datetime.strptime(
            시간,
            "%H:%M"
        )

    except ValueError:

        await interaction.response.send_message(
            "❌ 시간은 `20:30`처럼 입력해주세요.",
            ephemeral=True
        )

        return


    await interaction.response.defer(
        ephemeral=True
    )


    result = await create_match_post(
        시간,
        manual=True
    )


    if result:

        await interaction.followup.send(
            f"✅ `{시간}` 내전 모집글을 생성했습니다!",
            ephemeral=True
        )

    else:

        await interaction.followup.send(
            "❌ 모집글 생성에 실패했습니다. Railway 로그를 확인해주세요.",
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

        match_time = MATCH_START_TIME.strftime(
            "%H:%M"
        )


        await create_match_post(
            match_time
        )


        # 같은 분에 두 번 올라가는 것 방지
        await asyncio.sleep(60)


# =========================================================
# Task 시작 전
# =========================================================

@daily_match_post.before_loop

async def before_daily_post():

    await bot.wait_until_ready()


# =========================================================
# 봇 준비
# =========================================================

@bot.event

async def on_ready():

    print(
        f"✅ {bot.user} 로그인 완료"
    )


    # 자동 포럼 루프
    if not daily_match_post.is_running():

        daily_match_post.start()


# =========================================================
# 슬래시 명령어 동기화
# =========================================================

@bot.event

async def setup_hook():

    guild = discord.Object(
        id=GUILD_ID
    )


    bot.tree.copy_global_to(
        guild=guild
    )


    commands_synced = await bot.tree.sync(
        guild=guild
    )


    print(
        f"✅ 슬래시 명령어 "
        f"{len(commands_synced)}개 동기화 완료"
    )


# =========================================================
# 실행
# =========================================================

if TOKEN is None:

    raise RuntimeError(
        "DISCORD_TOKEN 환경변수가 없습니다."
    )


bot.run(TOKEN)
