import sys
import time
import pytz
from datetime import timedelta, datetime

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from core import database
from core.checks import is_botAdmin4, slash_is_bot_admin_3, slash_is_bot_admin_4
from core.logging_module import get_log
from core.common import LoggingChannels, OpenAIClient

_log = get_log(__name__)
client = OpenAIClient().client

class MiscCMD(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.interaction = []

    @property
    def display_emoji(self) -> str:
        return "🎮"

    @app_commands.command(name="ping", description="Pong!")
    async def ping(self, interaction: discord.Interaction):
        current_time = float(time.time())
        difference = int(round(current_time - float(self.bot.start_time)))
        text = str(timedelta(seconds=difference))

        pingembed = discord.Embed(
            title="Pong! ⌛",
            color=discord.Colour.dark_red(),
            description="Current Discord API Latency",
        )
        pingembed.set_author(
            name="Arasaka Development Team"
        )
        pingembed.add_field(
            name="Ping & Uptime:",
            value=f"```diff\n+ Ping: {round(self.bot.latency * 1000)}ms\n+ Uptime: {text}\n```",
        )

        pingembed.add_field(
            name="System Resource Usage",
            value=f"```diff\n- CPU Usage: {psutil.cpu_percent()}%\n- Memory Usage: {psutil.virtual_memory().percent}%\n```",
            inline=False,
        )
        pingembed.set_footer(
            text=f"ArasakaCorpBot Version: {self.bot.version}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.response.send_message(embed=pingembed)

    @app_commands.command()
    @app_commands.guilds(LoggingChannels.guild)
    @slash_is_bot_admin_3()
    async def say(self, interaction: discord.Interaction, message: str):
        NE = database.AdminLogging.create(
            discordID=interaction.user.id, action="SAY", content=message
        )
        NE.save()
        await interaction.response.send_message("Sent!", ephemeral=True)
        await interaction.channel.send(message)

    @commands.command()
    @is_botAdmin4
    async def t_say(self, ctx: commands.Context, *, message: str):
        NE = database.AdminLogging.create(
            discordID=ctx.author.id, action="t_say", content=message
        )
        NE.save()
        await ctx.message.delete()
        await ctx.send(message)

    @app_commands.command(name="direct-message", description="DM a user")
    @app_commands.guilds(LoggingChannels.guild)
    @slash_is_bot_admin_3()
    async def dm(self, interaction: discord.Interaction, user: discord.Member, message: str):
        NE = database.AdminLogging.create(
            discordID=interaction.user.id, action="DM", content=message
        )
        NE.save()
        try:
            await user.send(message)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Failed to DM user!", ephemeral=True
            )
        else:
            await interaction.response.send_message("Sent!", ephemeral=True)

    @commands.command()
    @is_botAdmin4
    async def kill(self, ctx: commands.Context):
        await ctx.send("Shutting down...")
        await sys.exit(1)

    @commands.command(name="help", description="List of commands available for ArasakaCorpBot.")
    async def _help(self, ctx: commands.Context):
        await ctx.send("Use **/help** to view the list of commands.\n> This command is deprecated and will be removed in the future.")

    @app_commands.command(name="help", description="List of commands available for ArasakaCorpBot.")
    async def help(self, interaction: discord.Interaction):
        BM = discord.utils.get(interaction.guild.roles, name="Bot Manager")
        OC = discord.utils.get(interaction.guild.roles, id=1143736564002861146)
        HC = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
        CH = discord.utils.get(interaction.guild.roles, id=1158472045248651434)
        BB = discord.utils.get(interaction.guild.roles, id=1163157560237510696)
        IC = discord.utils.get(interaction.guild.roles, id=1176645976723816579)

        # check if any of the roles are in the user first.
        if BM in interaction.user.roles or OC in interaction.user.roles or HC in interaction.user.roles or CH in interaction.user.roles or BB in interaction.user.roles or IC in interaction.user.roles:
            embed = discord.Embed(
                title="Help",
                color=discord.Colour.gold(),
                description="List of commands available for ArasakaCorpBot.",
            )

            # General commands
            general_commands = """
            **/say <message>** - Sends a message to the channel as the bot. | HICOM+ only.
            **/direct-message <user> <message>** - Sends a direct message to the specified user from the bot. | HICOM+ only.
            **/event-log <host-username> <event-type> <proof (file but optional)>** - Logs an event hosted by a user with an optional proof attachment.
            """
            embed.add_field(name="General Commands", value=general_commands, inline=False)

            # XP commands
            xp_commands = """
            **/xp update <user> <action: add/remove> <xp_amount>** - Updates the XP of a single user. The action can be 'add' or 'remove'.
            **/xp bulk_update <users (comma separated)> <action: add/remove> <xp_amount>** - Updates the XP of multiple users at once, separated by commas. The action can be 'add' or 'remove'.
            **/xp modify_status <user> <status>** - Modifies the weekly point status of a user. The status can be 'IN' *inactivity notice* or 'EX' *exempt*.
            """
            embed.add_field(name="XP Commands", value=xp_commands, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            await interaction.response.send_message("No permission to view the help page. | *This bot is for officers only.*")

    # Creating a slash command in discord.py
    @app_commands.command(name="ask", description="Ask a question")
    @app_commands.guilds(LoggingChannels.guild)
    async def ask(interaction: discord.Interaction, *, question: str):
        """if interaction.channel_id != 1216431006031282286:
            return await interaction.response.send_message("lil bro, you can't use this command here. take your ass to <#1216431006031282286>")"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system",
                 "content": "respond passive aggressively"},
                {"role": "user", "content": question}
            ]
        )
        await interaction.response.send_message(response.choices[0].message.content)

    @app_commands.command(name="maintenance", description="Toggle maintenance mode")
    @app_commands.guilds(LoggingChannels.guild)
    @slash_is_bot_admin_4()
    async def maintenance(self, interaction: discord.Interaction, reason: str):
        # Get the current maintenance status
        query: database.MaintenanceMode = database.MaintenanceMode.select().where(database.MaintenanceMode.id == 1)
        if not query.exists():
            query = database.MaintenanceMode.create(enabled=False, reason="No reason provided.")

        query = query.get()
        # Toggle the maintenance mode
        query.enabled = not query.enabled
        query.reason = reason
        query.start_time = datetime.now(tz=pytz.timezone("America/New_York"))
        query.save()

        # Log the action
        NE = database.AdminLogging.create(
            discordID=interaction.user.id, 
            action="MAINTENANCE", 
            content=f"Maintenance mode {'enabled' if query.enabled else 'disabled'}"
        )
        NE.save()

        # Send a response
        await interaction.response.send_message(
            f"Maintenance mode {'enabled' if query.enabled else 'disabled'}. "
            f"{'Only bot owners can use commands now.' if query.enabled else 'All users can use commands now.'}",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MiscCMD(bot))
