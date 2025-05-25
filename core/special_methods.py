from __future__ import annotations

import os
import subprocess
import traceback
import difflib
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path

import discord
import sentry_sdk
from discord.ext import commands
from discord import app_commands, ui

from core import database
from core.common import (
    ConsoleColors,
    Colors,
)
from core.logging_module import get_log

_log = get_log(__name__)
target_phrases = [
    "lack of events",
    "EVENT PLZ",
    "plz another event",
    "could anyone host any event?",
    "any events",
    "when will there be another AR or other events?",
    "host an event now",
    "host event",
    "please host",
    "please host an event",
    "event when",
    "can someone host an event?",
    "any event soon?",
    "when’s the next event?",
    "can we have an event?",
    "someone host event pls",
    "pls host event",
    "more events pls",
    "why no events?",
    "is there an event today?",
    "let’s do an event",
    "when event",
    "hosting event?"
]


def is_similar(message, phrases, threshold=0.6):
    """
    Check if a message is similar to any of the provided phrases.
    Args:
        message (str): The user message to check.
        phrases (list): List of target phrases.
        threshold (float): Similarity threshold (0 to 1).
    Returns:
        bool: True if similar, False otherwise.
    """
    message = message.lower()
    for phrase in phrases:
        similarity = difflib.SequenceMatcher(None, message, phrase.lower()).ratio()
        if similarity >= threshold:
            return True
    return False


async def before_invoke_(ctx: commands.Context):
    q = database.CommandAnalytics.create(
        command=ctx.command.name,
        user=ctx.author.id,
        date=datetime.now(),
        command_type="regular",
        guild_id=ctx.guild.id,
    ).save()

    # Set user context for Sentry
    sentry_sdk.set_user(None)
    sentry_sdk.set_user({"id": ctx.author.id, "username": ctx.author.name})
    sentry_sdk.set_tag("username", f"{ctx.author.name}#{ctx.author.discriminator}")

    # Add command execution breadcrumb
    command_name = ctx.command.name if ctx.command else "Unknown"
    command_args = " ".join([f"{k}={v}" for k, v in ctx.kwargs.items()]) if hasattr(ctx, 'kwargs') and ctx.kwargs else ""

    sentry_sdk.add_breadcrumb(
        category="command",
        message=f"Command executed: {command_name} {command_args}".strip(),
        level="info",
        data={
            "command": command_name,
            "args": ctx.args[1:] if hasattr(ctx, 'args') and len(ctx.args) > 1 else [],
            "kwargs": ctx.kwargs if hasattr(ctx, 'kwargs') else {},
            "prefix": ctx.prefix if hasattr(ctx, 'prefix') else None,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "channel_id": ctx.channel.id if ctx.channel else None,
        }
    )

    # Set command context
    if ctx.command is None:
        sentry_sdk.set_context(
            "user",
            {
                "name": ctx.author.name,
                "id": ctx.author.id,
                "command": "Unknown",
                "guild": ctx.guild.name if ctx.guild else "DM",
                "guild_id": ctx.guild.id if ctx.guild else None,
                "channel": ctx.channel.name if ctx.channel else "Unknown",
                "channel_id": ctx.channel.id if ctx.channel else None,
            },
        )
    else:
        sentry_sdk.set_context(
            "user",
            {
                "name": ctx.author.name,
                "id": ctx.author.id,
                "command": ctx.command.name,
                "guild": ctx.guild.name if ctx.guild else "DM",
                "guild_id": ctx.guild.id if ctx.guild else None,
                "channel": ctx.channel.name if ctx.channel else "Unknown",
                "channel_id": ctx.channel.id if ctx.channel else None,
            },
        )


async def on_ready_(bot):
    now = datetime.now()
    query: database.CheckInformation = (
        database.CheckInformation.select()
        .where(database.CheckInformation.id == 1)
        .get()
    )

    if not query.PersistantChange:
        # Add the DeleteView as a persistent view
        bot.add_view(DeleteView())

        query.PersistantChange = True
        query.save()

    if not os.getenv("USEREAL"):
        IP = os.getenv("DATABASE_IP")
        databaseField = f"{ConsoleColors.OKGREEN}Selected Database: External ({IP}){ConsoleColors.ENDC}"
    else:
        databaseField = (
            f"{ConsoleColors.FAIL}Selected Database: localhost{ConsoleColors.ENDC}\n{ConsoleColors.WARNING}WARNING: Not "
            f"recommended to use SQLite.{ConsoleColors.ENDC} "
        )

    try:
        p = subprocess.run(
            "git describe --always",
            shell=True,
            text=True,
            capture_output=True,
            check=True,
        )
        output = p.stdout
    except subprocess.CalledProcessError:
        output = "ERROR"

    # chat_exporter.init_exporter(bot)

    print(
        f"""
            ArasakaBot OS

            Bot Account: {bot.user.name} | {bot.user.id}
            {ConsoleColors.OKCYAN}Discord API Wrapper Version: {discord.__version__}{ConsoleColors.ENDC}
            {ConsoleColors.WARNING}ArasakaBot Version: {output}{ConsoleColors.ENDC}
            {databaseField}

            {ConsoleColors.OKCYAN}Current Time: {now}{ConsoleColors.ENDC}
            {ConsoleColors.OKGREEN}Cogs, libraries, and views have successfully been initialized.{ConsoleColors.ENDC}
            ==================================================
            {ConsoleColors.WARNING}Statistics{ConsoleColors.ENDC}

            Guilds: {len(bot.guilds)}
            Members: {len(bot.users)}
            """
    )


def initializeDB(bot):
    """
    Initializes the database, and creates the needed table data if they don't exist.
    """
    database.db.connect(reuse_if_open=True)
    CIQ = database.CheckInformation.select().where(database.CheckInformation.id == 1)

    if not CIQ.exists():
        database.CheckInformation.create(
            MasterMaintenance=False,
            guildNone=False,
            externalGuild=True,
            ModRoleBypass=True,
            ruleBypass=True,
            publicCategories=True,
            elseSituation=True,
            PersistantChange=False,
        )
        _log.info("Created CheckInformation Entry.")

    if len(database.Administrators) == 0:
        for person in bot.owner_ids:
            database.Administrators.create(discordID=person, TierLevel=4)
            _log.info("Created Administrator Entry.")
        database.Administrators.create(discordID=409152798609899530, TierLevel=4)

    query: database.CheckInformation = (
        database.CheckInformation.select()
        .where(database.CheckInformation.id == 1)
        .get()
    )
    query.PersistantChange = False
    query.save()
    database.db.close()


async def on_command_error_(bot, ctx: commands.Context, error: Exception):
    tb = error.__traceback__
    etype = type(error)
    exception = traceback.format_exception(etype, error, tb, chain=True)
    exception_msg = ""
    for line in exception:
        exception_msg += line

    # Set Sentry context for the error
    sentry_sdk.set_context(
        "command",
        {
            "name": ctx.command.name if ctx.command else "Unknown",
            "qualified_name": ctx.command.qualified_name if ctx.command else "Unknown",
            "guild": ctx.guild.name if ctx.guild else "DM",
            "guild_id": ctx.guild.id if ctx.guild else None,
            "channel": ctx.channel.name if ctx.channel else "Unknown",
            "channel_id": ctx.channel.id if ctx.channel else None,
            "author": f"{ctx.author.name}#{ctx.author.discriminator}" if ctx.author else "Unknown",
            "author_id": ctx.author.id if ctx.author else None,
        },
    )

    error = getattr(error, "original", error)
    if ctx.command is not None:
        if ctx.command.name == "rule":
            return "No Rule..."

    if isinstance(error, (commands.CheckFailure, commands.CheckAnyFailure)):
        return

    if hasattr(ctx.command, "on_error"):
        return

    elif isinstance(error, (commands.CommandNotFound, commands.errors.CommandNotFound)):
        cmd = ctx.invoked_with
        cmds = [cmd.name for cmd in bot.commands]
        matches = get_close_matches(cmd, cmds)
        if len(matches) > 0:
            return await ctx.send(
                f'Command "{cmd}" not found, maybe you meant "{matches[0]}"?'
            )
        else:
            """return await ctx.send(
                f'Command "{cmd}" not found, use the help command to know what commands are available. '
                f"Some commands have moved over to slash commands, please check "
                f"url"
                f"for more updates! "
            )"""
            return await ctx.message.add_reaction("❌")

    elif isinstance(
        error, (commands.MissingRequiredArgument, commands.TooManyArguments)
    ):
        signature = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"

        em = discord.Embed(
            title="Missing/Extra Required Arguments Passed In!",
            description="You have missed one or several arguments in this command"
            "\n\nUsage:"
            f"\n`{signature}`",
            color=Colors.red,
        )
        em.set_thumbnail(url=bot.user.avatar.url)
        em.set_footer(
            text="Consult the Help Command if you are having trouble or call over a Bot Manager!"
        )
        return await ctx.send(embed=em)

    elif isinstance(
        error,
        (
            commands.MissingAnyRole,
            commands.MissingRole,
            commands.MissingPermissions,
            commands.errors.MissingAnyRole,
            commands.errors.MissingRole,
            commands.errors.MissingPermissions,
        ),
    ):
        em = discord.Embed(
            title="Invalid Permissions!",
            description="You do not have the associated role in order to successfully invoke this command! "
            "Contact an administrator/developer if you believe this is invalid.",
            color=Colors.red,
        )
        em.set_thumbnail(url=bot.user.avatar.url)
        em.set_footer(
            text="Consult the Help Command if you are having trouble or call over a Bot Manager!"
        )
        await ctx.send(embed=em)
        return

    elif isinstance(
        error,
        (commands.BadArgument, commands.BadLiteralArgument, commands.BadUnionArgument),
    ):
        signature = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"

        em = discord.Embed(
            title="Bad Argument!",
            description=f"Unable to parse arguments, check what arguments you provided."
            f"\n\nUsage:\n`{signature}`",
            color=Colors.red,
        )
        em.set_thumbnail(url=bot.user.avatar.url)
        em.set_footer(
            text="Consult the Help Command if you are having trouble or call over a Bot Manager!"
        )
        return await ctx.send(embed=em)

    elif isinstance(
        error, (commands.CommandOnCooldown, commands.errors.CommandOnCooldown)
    ):
        m, s = divmod(error.retry_after, 60)
        h, m = divmod(m, 60)

        msg = "This command cannot be used again for {} minutes and {} seconds".format(
            round(m), round(s)
        )

        embed = discord.Embed(
            title="Command On Cooldown", description=msg, color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    else:
        # Capture the error in Sentry
        sentry_sdk.capture_exception(error)

        error_file = Path("error.txt")
        error_file.touch()
        with error_file.open("w") as f:
            f.write(exception_msg)
        embed = discord.Embed(
            title="Error Detected!",
            description="Seems like I've ran into an unexpected error!",
            color=Colors.red,
        )
        embed.add_field(
            name="Error Message",
            value=f"Check the console for more information.",
        )
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(text=f"Error: {str(error)}")
        await ctx.send(embed=embed)
    raise error


async def on_app_command_error_(bot, interaction: discord.Interaction, error: app_commands.AppCommandError):
    """
    Global error handler for application commands (slash commands).
    This function captures errors from slash commands and reports them to Sentry.
    """
    tb = error.__traceback__
    etype = type(error)
    exception = traceback.format_exception(etype, error, tb, chain=True)
    exception_msg = ""
    for line in exception:
        exception_msg += line

    # Set Sentry context for the error
    sentry_sdk.set_context(
        "app_command",
        {
            "name": interaction.command.name if interaction.command else "Unknown",
            "qualified_name": interaction.command.qualified_name if interaction.command else "Unknown",
            "guild": interaction.guild.name if interaction.guild else "DM",
            "guild_id": interaction.guild.id if interaction.guild else None,
            "channel": interaction.channel.name if interaction.channel else "Unknown",
            "channel_id": interaction.channel.id if interaction.channel else None,
            "user": f"{interaction.user.name}#{interaction.user.discriminator}" if interaction.user else "Unknown",
            "user_id": interaction.user.id if interaction.user else None,
        },
    )

    # Get the original error if it's wrapped
    error = getattr(error, "original", error)

    # Handle different types of errors
    if isinstance(error, app_commands.CommandNotFound):
        return

    elif isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(
            title="Missing Permissions",
            description="You don't have the required permissions to use this command.",
            color=Colors.red,
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return

    elif isinstance(error, app_commands.BotMissingPermissions):
        embed = discord.Embed(
            title="Bot Missing Permissions",
            description="I don't have the required permissions to execute this command.",
            color=Colors.red,
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return

    elif isinstance(error, app_commands.CommandOnCooldown):
        m, s = divmod(error.retry_after, 60)
        h, m = divmod(m, 60)

        msg = f"This command is on cooldown. Try again in {int(h)}h {int(m)}m {int(s)}s."

        embed = discord.Embed(
            title="Command On Cooldown",
            description=msg,
            color=Colors.red,
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # For all other errors, capture in Sentry and show a generic error message
    sentry_sdk.capture_exception(error)

    error_file = Path("error.txt")
    error_file.touch()
    with error_file.open("w") as f:
        f.write(exception_msg)

    embed = discord.Embed(
        title="Error Detected!",
        description="An unexpected error occurred while executing this command.",
        color=Colors.red,
    )
    embed.add_field(
        name="Error Message",
        value=f"The error has been logged. Please try again later or contact an administrator if the issue persists.",
    )
    embed.set_footer(text=f"Error: {str(error)}")

    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        # If we can't respond to the interaction, log the error
        _log.error(f"Failed to respond to interaction after error: {error}")

    # Re-raise the error for console logging
    raise error


class DeleteButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Delete This?",
            style=discord.ButtonStyle.danger,
            custom_id="delete_autoresponse",
            emoji="🗑️",
        )

    async def callback(self, interaction: discord.Interaction):
        # Check if the user is the one who triggered the message or has moderation permissions
        if interaction.message.mentions and interaction.user.id == interaction.message.mentions[0].id:
            await interaction.message.delete()
            await interaction.response.send_message("Auto-response deleted.", ephemeral=True)
        elif interaction.user.guild_permissions.manage_messages:
            await interaction.message.delete()
            await interaction.response.send_message("Auto-response deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have permission to delete this message.", ephemeral=True)


class DeleteView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DeleteButton())


async def on_message_(bot, message: discord.Message):
    if message.author.bot:
        return

    guild = bot.get_guild(1143709921326682182)
    high_command = guild.get_role(1143736740075552860)
    officer_role = guild.get_role(1154522379654008882)

    if is_similar(message.content, target_phrases, threshold=0.6) and not message.author.bot:
        if not (high_command in message.author.roles or officer_role in message.author.roles):
            view = DeleteView()
            await message.channel.send(f"{message.author.mention} use <#1359919471271215226>", view=view)
