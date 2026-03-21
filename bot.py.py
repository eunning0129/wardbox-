import discord
from discord.ext import commands, tasks
from datetime import datetime, time
import asyncio
import os

TOKEN = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

FORUM_CHANNEL_ID = 1478583260580937791
POST_TIME = time(hour=21, minute=30)

class VoteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.up = 0
        self.wait = 0

    @discord.ui.button(label="👍 참여", style=discord.ButtonStyle.success)
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.up += 1
        await interaction.response.edit_message(content=self.text(), view=self)

    @discord.ui.button(label="🕒 대기", style=discord.ButtonStyle.danger)
    async def downvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.wait += 1
        await interaction.response.edit_message(content=self.text(), view=self)

    def text(self):
        return f"📊 오늘의 투표\n👍 {self.up} | 🕒 {self.wait}"

@bot.event
async def on_ready():
    print(f"{bot.user} 실행됨")
    daily_post.start()

@tasks.loop(minutes=1)
async def daily_post():
    now = datetime.now()

    if now.hour == POST_TIME.hour and now.minute == POST_TIME.minute:
        channel = bot.get_channel(FORUM_CHANNEL_ID)

        if isinstance(channel, discord.ForumChannel):
            today = now.strftime("%Y-%m-%d")

            thread = await channel.create_thread(
                name=f"📢 {today} 내전 모집",
                content="@everyone\n참여=👍 대기=🕒"
            )

            await thread.thread.send(
                content="📊 오늘의 투표\n👍 0 | 🕒 0",
                view=VoteView()
            )

            await asyncio.sleep(60)

bot.run(TOKEN)