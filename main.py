"""
Copyright (C) rohitp30 - All Rights Reserved
 * Permission is granted to use this application as a code reference for educational purposes.
 * Written by TriageSpace, October 2022
"""

__author__ = "TriageSpace"
__author_email__ = "null"
__project__ = "Arasaka Discord Bot"

import faulthandler
import logging
import os
import time
from datetime import datetime

import discord
from alive_progress import alive_bar
from discord import app_commands, Message
from discord.ext import commands
from discord_sentry_reporting import use_sentry
from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from core import database
from core.common import get_extensions
from core.logging_module import get_log
from core.special_methods import (
    initializeDB,
    on_ready_, on_command_error_, on_message_, DeleteView,
)

load_dotenv()
faulthandler.enable()

logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
_log = get_log(__name__)
_log.info("Starting ArasakaBot...")


async def officer_check(guild: discord.Guild, user: discord.User, interaction: discord.Interaction):
    Officer_Corps = discord.utils.get(interaction.guild.roles, id=1143736564002861146)
    HICOM = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
    BIGBOSS = discord.utils.get(interaction.guild.roles, id=1163157560237510696)
    ClanLeader = discord.utils.get(interaction.guild.roles, id=1158472045248651434)
    user = guild.get_member(user.id)

    if not any(role in user.roles for role in
               [HICOM, BIGBOSS, ClanLeader, Officer_Corps]) and user.id not in [
        409152798609899530]:
        return await interaction.response.send_message("You do not have permission to use this command.",
                                                       ephemeral=True)


class ArasakaSlashTree(app_commands.CommandTree):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        blacklisted_users = [p.discordID for p in database.Blacklist]
        if interaction.user.avatar is None:
            await interaction.response.send_message(
                "Due to a discord limitation, you must have an avatar set to use this command.")
            return False
        if interaction.user.id in blacklisted_users:
            await interaction.response.send_message(
                "You have been blacklisted from using commands!", ephemeral=True
            )
            return False

        # Check if maintenance mode is enabled
        maintenance_check = database.MaintenanceMode.select().where(database.MaintenanceMode.id == 1)
        if not maintenance_check.exists():
            query = database.MaintenanceMode.create(enabled=False, reason="No reason provided.")
        else:
            query = maintenance_check.get()

        if query.enabled:
            # Get admin level 4 users (owners)
            admin_ids = []
            query = database.Administrators.select().where(
                database.Administrators.TierLevel >= 4
            )
            for admin in query:
                admin_ids.append(admin.discordID)

            # If user is not an owner and maintenance mode is enabled, reject the interaction

            if interaction.user.id not in admin_ids:
                embed = discord.Embed(
                    title="Maintenance Mode",
                    description="The bot is currently in maintenance mode. Only bot owners can use commands at this time.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Information", value=f"Maintenance Started: {discord.utils.format_dt(maintenance_check.start_time, style='R')}\nNotes: {maintenance_check.reason}\n\nIf you need to use the bot immediately, please contact Triage.")
                embed.set_footer(text="Please check back later.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return False

        return True

    async def on_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        print(error)
        from core.special_methods import on_app_command_error_
        await on_app_command_error_(self.bot, interaction, error)


class ArasakaBot(commands.Bot):
    """
    Generates a Arasaka Instance.
    """

    def __init__(self, uptime: time.time):
        super().__init__(
            command_prefix=commands.when_mentioned_or(os.getenv("AC_PREFIX")),
            intents=discord.Intents.all(),
            case_insensitive=True,
            tree_cls=ArasakaSlashTree,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="/help"
            ),
        )
        self.help_command = None
        #self.add_check(self.check)
        self._start_time = uptime

    async def on_ready(self):
        await on_ready_(self)

    async def on_command_error(self, context, exception) -> None:
        await on_command_error_(self, context, exception)

    async def setup_hook(self) -> None:
        with alive_bar(
                len(get_extensions()),
                ctrl_c=False,
                bar="bubbles",
                title="Initializing Cogs:",
        ) as bar:

            for ext in get_extensions():
                try:
                    await bot.load_extension(ext)
                except commands.ExtensionAlreadyLoaded:
                    await bot.unload_extension(ext)
                    await bot.load_extension(ext)
                except commands.ExtensionNotFound:
                    raise commands.ExtensionNotFound(ext)
                bar()
        self.add_view(DeleteView())

    async def is_owner(self, user: discord.User):
        """admin_ids = []
        query = database.Administrators.select().where(
            database.Administrators.TierLevel >= 3
        )
        for admin in query:
            admin_ids.append(admin.discordID)

        if user.id in admin_ids:
            return True"""

        return await super().is_owner(user)

    async def on_message(self, message: Message, /) -> None:
        if message.author.bot:
            return
        await on_message_(bot, message)
        await self.process_commands(message)

    @property
    def version(self):
        """
        Returns the current version of the bot.
        """
        version = "1.0.1"

        return version

    @property
    def author(self):
        """
        Returns the author of the bot.
        """
        return __author__

    @property
    def author_email(self):
        """
        Returns the author email of the bot.
        """
        return __author_email__

    @property
    def start_time(self):
        """
        Returns the time the bot was started.
        """
        return self._start_time


bot = ArasakaBot(time.time())


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        # Log command analytics to database
        database.CommandAnalytics.create(
            command=interaction.command.name,
            guild_id=interaction.guild.id,
            user=interaction.user.id,
            date=datetime.now(),
            command_type="slash",
        ).save()

        # Set user context for Sentry
        sentry_sdk.set_user(None)
        sentry_sdk.set_user({"id": interaction.user.id, "username": interaction.user.name})
        sentry_sdk.set_tag("command", interaction.command.name)

        # Extract command options for breadcrumb
        options = {}
        if hasattr(interaction, 'data') and 'options' in interaction.data:
            for option in interaction.data['options']:
                if 'value' in option:
                    options[option['name']] = option['value']
                elif 'options' in option:
                    # Handle subcommands
                    for suboption in option['options']:
                        if 'value' in suboption:
                            options[suboption['name']] = suboption['value']

        # Add command execution breadcrumb
        command_name = interaction.command.name if interaction.command else "Unknown"
        command_args = " ".join([f"{k}={v}" for k, v in options.items()]) if options else ""

        sentry_sdk.add_breadcrumb(
            category="slash_command",
            message=f"Slash command executed: {command_name} {command_args}".strip(),
            level="info",
            data={
                "command": command_name,
                "options": options,
                "guild_id": interaction.guild.id if interaction.guild else None,
                "channel_id": interaction.channel.id if interaction.channel else None,
            }
        )

        # Set command context
        sentry_sdk.set_context(
            "slash_command",
            {
                "name": command_name,
                "qualified_name": interaction.command.qualified_name if hasattr(interaction.command, 'qualified_name') else command_name,
                "guild": interaction.guild.name if interaction.guild else "DM",
                "guild_id": interaction.guild.id if interaction.guild else None,
                "channel": interaction.channel.name if interaction.channel else "Unknown",
                "channel_id": interaction.channel.id if interaction.channel else None,
                "user": f"{interaction.user.name}#{interaction.user.discriminator}",
                "user_id": interaction.user.id,
            },
        )


if os.getenv("DSN_SENTRY") is not None:
    sentry_logging = LoggingIntegration(
        level=logging.INFO,  # Capture info and above as breadcrumbs
        event_level=logging.ERROR,  # Send errors as events
    )

    # Traceback tracking, DO NOT MODIFY THIS
    use_sentry(
        bot,
        dsn=os.getenv("DSN_SENTRY"),
        traces_sample_rate=1.0,
        _experiments={
            "profiles_sample_rate": 1.0,
        },
        send_default_pii=True,  # capture user context pls
        enable_tracing=True,  # turn on performance tracing
        integrations=[AioHttpIntegration(), FlaskIntegration(), sentry_logging],
    )

initializeDB(bot)

if __name__ == "__main__":
    bot.run(os.getenv("TOKEN"))
