"""
Copyright (C) SpaceTurtle0 - All Rights Reserved
 * Permission is granted to use this application as a code reference for educational purposes.
 * Written by SpaceTurtle#2587, October 2022
"""

__author__ = "SpaceTurtle#2587"
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
from gtts import gTTS
from openai import OpenAI
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from core import database
from core.checks import is_botAdmin2
from core.common import get_extensions, PromotionButtons, ReviewInactivityView
from core.logging_module import get_log
from core.special_methods import (
    initializeDB,
    on_ready_, on_command_error_, on_message_,
)

load_dotenv()
faulthandler.enable()

logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)

_log = get_log(__name__)
_log.info("Starting ArasakaBot...")

client = OpenAI(
    # This is the default and can be omitted
    api_key=os.getenv("OPENAI_API"),
)


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
        return True

    async def on_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        print(error)
        # await on_app_command_error_(self.bot, interaction, error)
        raise error


class ArasakaBot(commands.Bot):
    """
    Generates a LosPollos Instance.
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

        q = database.LastCount.select().where(database.LastCount.id == 1)
        if not q.exists():
            database.LastCount.create(last_number=0, last_counted_by=0)
        self.current_count = database.LastCount.get(id=1).last_number
        self.last_counter = database.LastCount.get(id=1).last_counted_by

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

            # add persistence view button PromotionButtons
            bot.add_view(PromotionButtons(bot))
            bot.add_view(ReviewInactivityView(bot))

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
        database.CommandAnalytics.create(
            command=interaction.command.name,
            guild_id=interaction.guild.id,
            user=interaction.user.id,
            date=datetime.now(),
            command_type="slash",
        ).save()


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
        integrations=[FlaskIntegration(), sentry_logging],
    )

initializeDB(bot)


# Creating a slash command in discord.py
@bot.tree.command(name="ask", description="Ask a question", guild=discord.Object(id=1143709921326682182))
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


@bot.command()
@is_botAdmin2
async def sayvc(ctx: commands.Context, *, text=None):
    if 1 == 1:
        await ctx.message.delete()

        if not text:
            # We have nothing to speak
            await ctx.send(f"Hey {ctx.author.mention}, I need to know what to say please.")
            return

        vc = ctx.voice_client  # We use it more then once, so make it an easy variable
        if not vc:
            # We are not currently in a voice channel
            await ctx.send("I need to be in a voice channel to do this, please use the connect command.")
            return

        # Lets prepare our text, and then save the audio file
        tts = gTTS(text=text, lang="en")
        tts.save("text.mp3")

        try:
            # Lets play that mp3 file in the voice channel
            vc.play(discord.FFmpegPCMAudio('text.mp3'), after=lambda e: print(f"Finished playing: {e}"))

            # Lets set the volume to 1
            vc.source = discord.PCMVolumeTransformer(vc.source)
            vc.source.volume = 1

        # Handle the exceptions that can occur
        except discord.ClientException as e:
            await ctx.send(f"A client exception occured:\n`{e}`")

        except TypeError as e:
            await ctx.send(f"TypeError exception:\n`{e}`")
    else:
        await ctx.send("You do not have permission to use this command.")


@bot.tree.context_menu(name="How do I verify?", guild=discord.Object(id=1143709921326682182))
async def verify_info(interaction: discord.Interaction, message: discord.Message):
    msg = await officer_check(interaction.guild, interaction.user, interaction)
    if not msg:
        await message.reply(
            f"A: **Is it really that hard to check the pinned messages?**\n> You can verify yourself by running /verify in <#1205691124543389787>.\nIf you are already a member, you can run /update in <#1143717377738022992>.\n\n**Next time check the pinned messages: https://discord.com/channels/1143709921326682182/1183227413476417587/1183228010967609524**\nSent from: {interaction.user.mention}")
    await interaction.response.send_message("1 idiot's question answered.", ephemeral=True)

@bot.tree.context_menu(name="How do I join/get the clan code?", guild=discord.Object(id=1143709921326682182))
async def join_clan_code(interaction: discord.Interaction, message: discord.Message):
    msg = await officer_check(interaction.guild, interaction.user, interaction)
    if not msg:
        await message.reply(
            f"A: **Is it really that hard to check the pinned messages?**\n> To join The Arasaka Corporation, you have to complete the steps in our application channel (<#1183769117380050976>) and join 4 events. If you are accepted and do everything correctly, you will receive the Junior Operative rank and be DM'ed the clan code at the end of the week.\n\n**Next time check the pinned messages: https://discord.com/channels/1143709921326682182/1183227413476417587/1183228010967609524**\nSent from: {interaction.user.mention}")
    await interaction.response.send_message("1 idiot's question answered.", ephemeral=True)

@bot.tree.context_menu(name="How often are apps checked?", guild=discord.Object(id=1143709921326682182))
async def applications_checked(interaction: discord.Interaction, message: discord.Message):
    msg = await officer_check(interaction.guild, interaction.user, interaction)
    if not msg:
        await message.reply(
            f"A: **Is it really that hard to check the pinned messages?**\n> Applications are checked by HICOM within 48 hours after they are sent. Please be patient as we may be busy. Constantly asking about your application will not speed up the process.\n\n**Next time check the pinned messages: https://discord.com/channels/1143709921326682182/1183227413476417587/1183228010967609524**\nSent from: {interaction.user.mention}")
    await interaction.response.send_message("1 idiot's question answered.", ephemeral=True)

@bot.tree.context_menu(name="How do I get promoted?", guild=discord.Object(id=1143709921326682182))
async def promotion_issue(interaction: discord.Interaction, message: discord.Message):
    msg = await officer_check(interaction.guild, interaction.user, interaction)
    if not msg:
        await message.reply(
            f"A: **Is it really that hard to check the pinned messages?**\n> Submit a promotion request in <#1225898217833496697> with the required information through the command. Read the pinned messages for more help.\n\n**Next time check the pinned messages: https://discord.com/channels/1143709921326682182/1183227413476417587/1183228010967609524**\nSent from: {interaction.user.mention}")
    await interaction.response.send_message("1 idiot's question answered.", ephemeral=True)

@bot.tree.context_menu(name="How do I become an officer?", guild=discord.Object(id=1143709921326682182))
async def become_officer(interaction: discord.Interaction, message: discord.Message):
    msg = await officer_check(interaction.guild, interaction.user, interaction)
    if not msg:
        await message.reply(
            f"A: **Is it really that hard to check the pinned messages?**\n> To join the Officer Corps, you must be A-2+ and apply when applications are open. These are open around once every 2 months.\n\n**Next time check the pinned messages: https://discord.com/channels/1143709921326682182/1183227413476417587/1183228010967609524**\nSent from: {interaction.user.mention}")
    await interaction.response.send_message("1 idiot's question answered.", ephemeral=True)

@bot.command()
async def connect(ctx, vc_id):
    try:
        ch = await bot.fetch_channel(vc_id)
        await ch.connect()
    except:
        await ctx.send("not a channel noob")
    else:
        await ctx.send("connected")


if __name__ == "__main__":
    bot.run(os.getenv("TOKEN"))
