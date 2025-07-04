from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core import database
from core.checks import (
    slash_is_bot_admin_4,
    slash_is_bot_admin,
)
from core.common import LoggingChannels

load_dotenv()

def get_extensions():
    extensions = ["jishaku"]
    for file in Path("utils").glob("**/*.py"):
        if "!" in file.name or "DEV" in file.name:
            continue
        extensions.append(str(file).replace("/", ".").replace(".py", ""))
    return extensions


class CoreBotConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.__cog_name__ = "Core Bot Config"
        self.bot = bot

    @property
    def display_emoji(self) -> str:
        return "⚙️"

    PM = app_commands.Group(
        name="permit",
        description="Configure the bots permit settings.",
        guild_ids=[LoggingChannels.guild]
    )

    @PM.command(description="Lists all permit levels and users.")
    @slash_is_bot_admin()
    async def list(self, interaction: discord.Interaction):
        adminList = []

        query1 = database.Administrators.select().where(
            database.Administrators.TierLevel == 1
        )
        for admin in query1:
            user = self.bot.get_user(admin.discordID)
            if user is None:
                try:
                    user = await self.bot.fetch_user(admin.discordID)
                except:
                    continue
            adminList.append(f"`{user.name}` -> `{user.id}`")

        adminLEVEL1 = "\n".join(adminList)

        adminList = []
        query2 = database.Administrators.select().where(
            database.Administrators.TierLevel == 2
        )
        for admin in query2:
            user = self.bot.get_user(admin.discordID)
            if user is None:
                try:
                    user = await self.bot.fetch_user(admin.discordID)
                except:
                    continue
            adminList.append(f"`{user.name}` -> `{user.id}`")

        adminLEVEL2 = "\n".join(adminList)

        adminList = []
        query3 = database.Administrators.select().where(
            database.Administrators.TierLevel == 3
        )
        for admin in query3:
            user = self.bot.get_user(admin.discordID)
            if user is None:
                try:
                    user = await self.bot.fetch_user(admin.discordID)
                except:
                    continue
            adminList.append(f"`{user.name}` -> `{user.id}`")

        adminLEVEL3 = "\n".join(adminList)

        adminList = []
        query4 = database.Administrators.select().where(
            database.Administrators.TierLevel == 4
        )
        for admin in query4:
            user = self.bot.get_user(admin.discordID)
            if user is None:
                try:
                    user = await self.bot.fetch_user(admin.discordID)
                except:
                    continue
            adminList.append(f"`{user.name}` -> `{user.id}`")

        adminLEVEL4 = "\n".join(adminList)

        embed = discord.Embed(
            title="Bot Administrators",
            description="Whitelisted Users that have Increased Authorization",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Whitelisted Users",
            value=f"Format:\n**Username** -> **ID**"
            f"\n\n**Permit 4:** *Owners*\n{adminLEVEL4}"
            f"\n\n**Permit 3:** *Sudo Administrators*\n{adminLEVEL3}"
            f"\n\n**Permit 2:** *Administrators*\n{adminLEVEL2}"
            f"\n\n**Permit 1:** *Bot Managers*\n{adminLEVEL1}",
        )
        embed.set_footer(
            text="Only Owners/Permit 4's can modify Bot Administrators."
        )

        await interaction.response.send_message(embed=embed)

    @PM.command(description="Remove a user from the Bot Administrators list.")
    @app_commands.describe(
        user="The user to remove from the Bot Administrators list.",
    )
    @slash_is_bot_admin_4()
    async def remove(self, interaction: discord.Interaction, user: discord.User):
        database.db.connect(reuse_if_open=True)

        query = database.Administrators.select().where(
            database.Administrators.discordID == user.id
        )
        if query.exists():
            query = query.get()

            query.delete_instance()

            embed = discord.Embed(
                title="Successfully Removed User!",
                description=f"{user.name} has been removed from the database!",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)

        else:
            embed = discord.Embed(
                title="Invalid User!",
                description="Invalid Provided: (No Record Found)",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)

        database.db.close()

    @PM.command(description="Add a user to the Bot Administrators list.")
    @app_commands.describe(
        user="The user to add to the Bot Administrators list.",
    )
    @slash_is_bot_admin_4()
    async def add(
        self, interaction: discord.Interaction, user: discord.User, level: int
    ):
        database.db.connect(reuse_if_open=True)
        q: database.Administrators = database.Administrators.create(
            discordID=user.id, TierLevel=level
        )
        q.save()
        embed = discord.Embed(
            title="Successfully Added User!",
            description=f"{user.name} has been added successfully with permit level `{str(level)}`.",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

        database.db.close()


async def setup(bot):
    await bot.add_cog(CoreBotConfig(bot))