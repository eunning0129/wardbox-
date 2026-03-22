import discord
from discord.ext import commands, tasks
from datetime import datetime, time
from zoneinfo import ZoneInfo
import asyncio
import os

TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 🔧 설정
FORUM_CHANNEL_ID = 1478583260580937791  # 포럼 채널 ID
POST_UPLOAD_TIME = time(hour=12, minute=00)   # 포럼 글 올라가는 시간
MATCH_START_TIME = time(hour=21, minute=30)  # 내전 시작 시간


class VoteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.participants = set()
        self.waiting = set()

    def make_text(self):
        participant_list = "\n".join(f"- {name}" for name in sorted(self.participants))
        waiting_list = "\n".join(f"- {name}" for name in sorted(self.waiting))

        if not participant_list:
            participant_list = "- 없음"
        if not waiting_list:
            waiting_list = "- 없음"

        return (
            f"📊 오늘의 투표\n\n"
            f"👍 참여 ({len(self.participants)})\n{participant_list}\n\n"
            f"🕒 대기 ({len(self.waiting)})\n{waiting_list}"
        )

    @discord.ui.button(label="👍 참여", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_name = interaction.user.display_name

        # 대기에서 제거 후 참여로 이동
        self.waiting.discard(user_name)
        self.participants.add(user_name)

        await interaction.response.edit_message(
            content=self.make_text(),
            view=self
        )

    @discord.ui.button(label="🕒 대기", style=discord.ButtonStyle.secondary)
    async def wait_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_name = interaction.user.display_name

        # 참여에서 제거 후 대기로 이동
        self.participants.discard(user_name)
        self.waiting.add(user_name)

        await interaction.response.edit_message(
            content=self.make_text(),
            view=self
        )


@bot.event
async def on_ready():
    print(f"{bot.user} 실행됨")
    if not daily_post.is_running():
        daily_post.start()


@tasks.loop(minutes=1)
async def daily_post():
    now = datetime.now(ZoneInfo("Asia/Seoul"))

    if now.hour == POST_UPLOAD_TIME.hour and now.minute == POST_UPLOAD_TIME.minute:
        channel = bot.get_channel(FORUM_CHANNEL_ID)

        if isinstance(channel, discord.ForumChannel):
            days = ["월", "화", "수", "목", "금", "토", "일"]

            date_str = now.strftime("%m/%d")
            weekday = days[now.weekday()]
            match_time_str = MATCH_START_TIME.strftime("%H:%M")

            try:
                thread = await channel.create_thread(
                    name=f"📢 {date_str} ({weekday}) {match_time_str} 내전 모집",
                    content=(
                        f"@everyone\n"
                        f"내전 시작 시간: {match_time_str}\n"
                        f"참여=👍 대기=🕒\n"
                        f"시간 조정 필요하면 댓글로 남겨주세요!"
                    )
                )

                view = VoteView()

                await thread.thread.send(
                    content=view.make_text(),
                    view=view
                )

                print("포럼 생성 완료")

            except Exception as e:
                print(f"에러: {e}")

        await asyncio.sleep(60)


bot.run(TOKEN)
