from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path
from threading import Thread
import roblox
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Union,
    TYPE_CHECKING,
)

import discord
import gspread
import pytz
import requests
from discord import ui, Button, ButtonStyle
from discord.ext import commands
from discord.ui import View
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from roblox import Client

from core import database
from core.logging_module import get_log

if TYPE_CHECKING:
    pass

load_dotenv()

# Module Variables
CoroutineType = Callable[[Any, Any], Awaitable[Any]]
_log = get_log(__name__)

class SheetsClient:
    def __init__(
        self,
        creds_path: str = "ArasakaBotCreds.json",
        sheet_name: str = "Arasaka Corp. Database V2",
    ):
        # set up Google Sheets API
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        self.client = gspread.authorize(creds)
        # open the workbook and grab the first worksheet (or by index)
        self.sheet = self.client.open(sheet_name).sheet1


class OpenAIClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("OPENAI_API")
        if not key:
            raise RuntimeError("OPENAI_API environment variable not set")
        # wrap the OpenAI client
        self.client = OpenAI(api_key=key)


class RobloxClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("ROBLOX_SECURITY")
        if not key:
            raise RuntimeError("Roblox API environment variable not set")
        self.client = roblox.Client(key)


class LoggingChannels:
    xp_log_ch = 1224907141060628532
    officer_role_id = 1143736564002861146
    log_ch = 1145110858272346132
    guild = 1143709921326682182


class ArasakaRanks:
    rank_xp_thresholds = {
        'Initiate': 0,  # A-1
        'Junior Operative': 15,  # A-2
        'Operative': 30,  # A-3
        'Specialist': 50,  # A-4
        'Senior Agent': 80,  # A-5
        'Sergeant': 120,  # N-1
        # 'Command Sergeant': 150,  # N-2
        # 'Commander': 200,  # N-3
        # ... continue as needed
    }

    status_dict = {
        "IN": "on an inactivity notice",
        "EX": "exempt from receiving XP",
        "RH": "a recent hire"
    }

    next_rank = {
        'Initiate': 'Junior Operative',
        'Junior Operative': 'Operative',
        'Operative': 'Specialist',
        'Specialist': 'Senior Agent',
        'Senior Agent': 'Sergeant',
        'Sergeant': 'RL',
        # 'Command Sergeant': 'Commander',
        # 'Commander': '🔒'
    }

    quota_dict = {
        "Initiate": 6,
        "Junior Operative": 6,
        "Operative": 6,
        "Specialist": 6,
        "Senior Agent": 6,
        "Sergeant": 4,
        "Sergeant Major": 4,
        "Commander": 4,
        "Corporate Officer on Trial": 4,
        "Junior Corporate Field Officer": 4,
        "Corporate Field Officer": 4,
        "Senior Corporate Field Officer": 3,
        "Chief Corporate Field Officer": 2,
    }


class ButtonHandler(ui.Button):
    """
    Adds a Button to a specific message and returns it's value when pressed.
    Usage:
        To do something after the callback function is invoked (the button is pressed), you have to pass a
        coroutine to the class. IMPORTANT: The coroutine has to take two arguments (discord.Interaction, discord.View)
        to work.
    """

    def __init__(
            self,
            style: ButtonStyle,
            label: str,
            custom_id: Union[str, None] = None,
            emoji: Union[str, None] = None,
            url: Union[str, None] = None,
            disabled: bool = False,
            button_user: Union[discord.Member, discord.User, None] = None,
            roles: List[discord.Role] = None,
            interaction_message: Union[str, None] = None,
            ephemeral: bool = True,
            coroutine: CoroutineType = None,
            view_response=None,
    ):
        """
        Parameters:
            style: Label for the button
            label: Custom ID that represents this button. Default to None.
            custom_id: Style for this button. Default to None.
            emoji: An emoji for this button. Default to None.
            url: A URL for this button. Default to None.
            disabled: Whenever the button should be disabled or not. Default to False.
            button_user: The user that can perform this action, leave blank for everyone. Defaults to None.
            roles: The roles which the user needs to be able to click the button.
            interaction_message: The response message when pressing on a selection. Default to None.
            ephemeral: Whenever the response message should only be visible for the select_user or not. Default to True.
            coroutine: A coroutine that gets invoked after the button is pressed. If None is passed, the view is stopped after the button is pressed. Default to None.
        """
        self.style_ = style
        self.label_ = label
        self.custom_id_ = custom_id
        self.emoji_ = emoji
        self.url_ = url
        self.disabled_ = disabled
        self.button_user = button_user
        self.roles = roles
        self.interaction_message_ = interaction_message
        self.ephemeral_ = ephemeral
        self.coroutine = coroutine
        self.view_response = view_response

        if self.custom_id_:
            super().__init__(
                style=self.style_,
                label=self.label_,
                custom_id=self.custom_id_,
                emoji=self.emoji_,
                url=self.url_,
                disabled=self.disabled_,
            )
        else:
            super().__init__(
                style=self.style_,
                label=self.label_,
                emoji=self.emoji_,
                url=self.url_,
                disabled=self.disabled_,
            )

    async def callback(self, interaction: discord.Interaction):
        if self.button_user in [None, interaction.user] or any(
                role in interaction.user.roles for role in self.roles
        ):
            if self.custom_id_ is None:
                self.view.value = self.label_
                self.view_response = self.label_
            else:
                self.view.value = self.custom_id_
                self.view_response = self.custom_id_

            if self.interaction_message_:
                await interaction.response.send_message(
                    content=self.interaction_message_, ephemeral=self.ephemeral_
                )

            if self.coroutine is not None:
                await self.coroutine(interaction, self.view)
            else:
                self.view.stop()
        else:
            await interaction.response.send_message(
                content="You're not allowed to interact with that!", ephemeral=True
            )


def get_extensions():
    extensions = ["jishaku"]
    if sys.platform == "win32" or sys.platform == "cygwin":
        dirpath = "\\"
    else:
        dirpath = "/"

    for file in Path("utils").glob("**/*.py"):
        if "!" in file.name or "DEV" in file.name or "view_models" in file.name:
            continue
        extensions.append(str(file).replace(dirpath, ".").replace(".py", ""))
    return extensions


async def force_restart(ctx, host_dir):
    p = subprocess.run(
        "git status -uno", shell=True, text=True, capture_output=True, check=True
    )

    embed = discord.Embed(
        title="Restarting...",
        description="Doing GIT Operation (1/3)",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Checking GIT (1/3)", value=f"**Git Output:**\n```shell\n{p.stdout}\n```"
    )

    msg = await ctx.send(embed=embed)
    true_dir = {
        "LosPollosBot": "LosPollosBot",
    }
    try:
        result = subprocess.run(
            f"sudo /home/{true_dir[host_dir]}/timmystart.sh",
            shell=True,
            text=True,
            capture_output=True,
            check=True,
        )
        process = subprocess.Popen([sys.executable, "main.py"])

        run_thread = Thread(target=process.communicate)
        run_thread.start()

        embed.add_field(
            name="Started Environment and Additional Process (2/3)",
            value="Executed `source` and `nohup`.",
            inline=False,
        )
        await msg.edit(embed=embed)

    except Exception as e:
        embed = discord.Embed(title="Operation Failed", description=e, color=discord.Colors.red)
        embed.set_footer(text="Main bot process will be terminated.")

        await ctx.send(embed=embed)

    else:
        embed.add_field(
            name="Killing Old Bot Process (3/3)",
            value="Executing `sys.exit(0)` now...",
            inline=False,
        )
        await msg.edit(embed=embed)
        sys.exit(0)


def string_time_convert(string: str):
    """
    Filters out the different time units from a string (e.g. from '2d 4h 6m 7s') and returns a ``dict``.
    NOTE: The sequence of the time units doesn't matter. Could also be '6m 2d 7s 4h'.
    Params:
        string: The string which should get converted to the time units. (e.g. '2d 4h 6m 7s')
    Returns: A ``dict`` which the keys are 'days', 'hours', 'minutes', 'seconds' and the value is either a ``int`` or ``None``.
    """

    time_dict: dict = {}

    days = re.search("\d+d", string)
    hours = re.search("\d+h", string)
    minutes = re.search("\d+m", string)
    seconds = re.search("\d+s", string)

    if days is not None:
        time_dict["days"] = int(days.group(0).strip("d"))
    else:
        time_dict["days"] = None

    if hours is not None:
        time_dict["hours"] = int(hours.group(0).strip("h"))
    else:
        time_dict["hours"] = None

    if minutes is not None:
        time_dict["minutes"] = int(minutes.group(0).strip("m"))
    else:
        time_dict["minutes"] = None

    if seconds is not None:
        time_dict["seconds"] = int(seconds.group(0).strip("s"))
    else:
        time_dict["seconds"] = None

    return time_dict


class ConsoleColors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class Colors:
    """
    Colors for the bot. Can be custom hex colors or built-in colors.
    """

    # *** Standard Colors ***
    blurple = discord.Color.blurple()
    green = discord.Color.brand_green()
    yellow = discord.Color.yellow()
    fuchsia = discord.Color.fuchsia()
    red = discord.Color.brand_red()

    # *** Hex Colors ***
    orange = 0xFCBA03
    dark_gray = 0x2F3136
    light_purple = 0xD6B4E8
    mod_blurple = 0x4DBEFF
    ss_blurple = 0x7080FA


def get_host_dir():
    """
    Get the directory of the current host.

    Format: /home/<HOST>/
    -> which 'HOST' is either 'stable` or 'beta'

    NOTE: THIS ONLY WORKS ON THE VPS.
    """

    run_path = os.path.realpath(__file__)
    run_dir = re.search("/home/[^/]*", run_path)
    if run_dir is not None:
        run_dir = run_dir.group(0)
    else:
        run_dir = None

    return run_dir


class RobloxDiscordLinker:
    """
    A centralized class for handling Discord ↔ Roblox profile linking.

    This class provides methods for converting between Discord IDs/usernames and Roblox IDs/usernames,
    using various sources including the Blox.link API, Discord member list, and Google Sheets.

    Attributes:
        bot (discord.Client): The Discord bot instance.
        guild_id (int): The ID of the Discord guild.
        sheet (gspread.Worksheet, optional): The Google Sheet containing user data.
        client (roblox.Client, optional): The Roblox client for API interactions.

    Methods:
        discord_id_to_roblox_username(discord_id): Convert a Discord ID to a Roblox username.
        discord_id_to_roblox_user(discord_id, group): Convert a Discord ID to a Roblox user in a group.
        roblox_username_to_discord_id(roblox_username): Convert a Roblox username to a Discord ID.
        get_user_xp_data(username): Get a user's XP data from the Google Sheet.
    """

    def __init__(self, bot: discord.Client, guild_id: int, sheet=None):
        self.bot = bot
        self.guild_id = guild_id
        self.sheet = sheet
        self.client = Client(os.getenv("ROBLOX_SECURITY")) if os.getenv("ROBLOX_SECURITY") else None

    async def discord_id_to_roblox_username(self, discord_id: int) -> Union[str, None]:
        """
        Convert a Discord ID to a Roblox username using the Blox.link API.

        Args:
            discord_id (int): The Discord ID to convert.

        Returns:
            str or None: The Roblox username if found, None otherwise.
        """
        response = requests.get(
            f'https://api.blox.link/v4/public/guilds/{LoggingChannels.guild}/discord-to-roblox/{discord_id}',
            headers={"Authorization": os.getenv("BLOXLINK_TOKEN")})

        if response.status_code == 200:
            roblox_id = response.json()['robloxID']
            roblox_user = await self.client.get_user(roblox_id)
            return roblox_user.name if roblox_user else None
        else:
            return None

    def discord_id_to_roblox_user(self, discord_id: int, group):
        """
        Convert a Discord ID to a Roblox user in a group using the Blox.link API.

        Args:
            discord_id (int): The Discord ID to convert.
            group: The Roblox group to get the member from.

        Returns:
            roblox.Member or None: The Roblox group member if found, None otherwise.
        """
        response = requests.get(
            f'https://api.blox.link/v4/public/guilds/{LoggingChannels.guild}/discord-to-roblox/{discord_id}',
            headers={"Authorization": os.getenv("BLOXLINK_TOKEN")})

        if response.status_code == 200:
            return group.get_member(response.json()['robloxID'])
        else:
            return None

    def roblox_username_to_discord_id(self, roblox_username: str) -> Union[int, str]:
        """
        Convert a Roblox username to a Discord ID.

        This method tries several approaches:
        1. Look for a Discord member with a matching display name
        2. Search in the Google Sheet for the username and extract the Discord ID

        Args:
            roblox_username (str): The Roblox username to convert.

        Returns:
            int or str: The Discord ID if found, or the original Roblox username if not found.
        """
        # Try to find a Discord member with a matching display name
        member = discord.utils.get(self.bot.get_guild(self.guild_id).members, display_name=roblox_username)
        if member:
            return member.id

        # Try to find the username in the Google Sheet
        if self.sheet:
            try:
                user = self.sheet.find(roblox_username, case_sensitive=False)
                user = self.sheet.cell(user.row, 15)
                # Strip non-numeric characters from the value
                cleaned = int(re.sub(r"[^0-9]", "", user.value))
                return cleaned
            except:
                pass

        # If all else fails, return the original username
        return roblox_username

    async def get_user_xp_data(self, username: str) -> Union[dict, None]:
        """
        Get a user's XP data from the Google Sheet.

        This method first tries to find the username directly in the sheet.
        If that fails and the username is a Discord ID, it tries to convert it to a Roblox username
        using the Blox.link API and then search for that in the sheet.

        Args:
            username (str): The username or Discord ID to search for.

        Returns:
            dict or None: A dictionary containing the user's rank, weekly XP, and total XP if found,
                         None otherwise.
        """
        # First try to find the username directly in the sheet
        cell = self.sheet.find(str(username), in_column=2, case_sensitive=False) if self.sheet else None

        # If not found and username is a Discord ID, try to convert it to a Roblox username
        if not cell and isinstance(username, (int, str)) and str(username).isdigit():
            roblox_username = await self.discord_id_to_roblox_username(int(username))
            if roblox_username:
                cell = self.sheet.find(roblox_username, in_column=2, case_sensitive=False) if self.sheet else None

        if not cell:
            return None  # User not found

        # Fetch the entire row where the user is found
        user_row = self.sheet.row_values(cell.row)

        # Create a dictionary with the user's data
        user_data = {
            'rank': user_row[3],  # Index 4 corresponds to column E
            'weekly_xp': user_row[7],  # Index 9 corresponds to column J
            'total_xp': float(user_row[8]),  # Index 10 corresponds to column K
            'division': user_row[4],  # Index 5 corresponds to column E
        }

        return user_data


def retrieve_discord_user(username: Union[str, int], bot: discord.Client, guild_id, sheet=None):
    """
    Retrieve the Discord user from the Roblox username.

    This function retrieves the Discord user from the Roblox username by searching for the
    specified Roblox username and returning the corresponding Discord user.

    Args:
        username (str): The Roblox username for which the Discord user should be retrieved.
        bot (commands.Bot): The Discord bot instance.
        guild_id (int): The ID of the Discord guild in which the user should be searched.
        sheet (gspread.Worksheet, optional): The Google Sheet containing user data.

    Returns:
        Union[str, int]: The Discord user ID corresponding to the specified Roblox username,
            or the original username if not found.
    """
    # Use the new RobloxDiscordLinker class
    linker = RobloxDiscordLinker(bot, guild_id, sheet)
    return linker.roblox_username_to_discord_id(username)


class EventLogForm(discord.ui.Modal, title="Other Game Link"):
    event_type = ui.TextInput(
        label="Event Type",
        placeholder="Enter a valid event type.",
        style=discord.TextStyle.short
    )

    host_username = ui.TextInput(
        label="Host Username:",
        placeholder="Enter a valid username",
        style=discord.TextStyle.short
    )

    cohost_username = ui.TextInput(
        label="Co-Host Username",
        placeholder="Leave blank if none",
        style=discord.TextStyle.short
    )

    supervisor_username = ui.TextInput(
        label="Supervisor",
        placeholder="Enter a valid username",
        style=discord.TextStyle.short
    )

    attendees = ui.TextInput(
        label="Attendees",
        placeholder="Ensure they are separated by a comma",
        style=discord.TextStyle.long
    )

    proof = ui.TextInput(
        label="Proof of Event",
        placeholder="Enter a valid link",
        style=discord.TextStyle.long
    )

    async def on_submit(self, interaction: discord.Interaction):
        # make an embed with the data
        embed = discord.Embed(
            title="Event Log",
            color=discord.Color.brand_red()
        )

        embed.add_field(name="Event Type", value=self.event_type.value)
        embed.add_field(name="Host Username", value=self.host_username.value)
        embed.add_field(name="Co-Host Username", value=self.cohost_username.value)
        embed.add_field(name="Supervisor Username", value=self.supervisor_username.value)
        embed.add_field(name="Attendees", value=self.attendees.value)
        embed.add_field(name="Proof of Event", value=self.proof.value)

        await interaction.response.send_message(embed=embed)


class ConfirmationView(View):
    def __init__(self, *, timeout=30):
        super().__init__(timeout=timeout)
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.value = False
        self.stop()


def calculate_new_xp_values(weekly_points, total_points, xp, special_status=False):
    """
    Calculate new XP values based on the specified action.

    This function calculates the new weekly and total XP values based on the specified action ('add' or 'remove')
    and the amount of XP to be added or removed. It also handles special conditions such as 'IN' (inactivity notice),
    'EX' (exempt), and 'RH' (reset hours).

    Args:
        weekly_points (float | str): The current weekly XP value for the user.
        total_points (float | str): The current total XP value for the user.
        xp (float | list): The amount of XP to be added or removed. If a list is provided, the first element
            represents the weekly XP to be added or removed, and the second element represents the total XP.
        action (str): The action to be performed. Should be either 'add' or 'remove'.
        special_status (bool): Indicates whether the user is on an inactivity notice or exempt. Default is False.

    Returns:
        tuple: A tuple containing the new weekly and total XP values after the specified action has been performed.
    """
    # Handle special conditions for weekly and total points.
    if weekly_points not in ["RH", "IN", "EX"]:
        weekly_points = float(weekly_points)
    total_points = float(total_points) if total_points not in ["RH", "IN", "EX"] else 0

    # Calculate the new XP values based on the action.
    if isinstance(xp, list):
        if xp[0] >= 0:
            calc_weekly_points = weekly_points + abs(xp[0]) if isinstance(weekly_points, float) else weekly_points
        else:
            calc_weekly_points = max(0, weekly_points - abs(xp[0])) if isinstance(weekly_points, float) else weekly_points

        if xp[1] >= 0:
            calc_total_points = total_points + abs(xp[1])
        else:
            calc_total_points = max(0, total_points - abs(xp[1]))
    else:
        if xp >= 0:
            calc_weekly_points = weekly_points + abs(xp) if isinstance(weekly_points, float) else weekly_points
            calc_total_points = total_points + abs(xp)
        else:
            calc_weekly_points = max(0, weekly_points - abs(xp)) if isinstance(weekly_points, float) else weekly_points
            calc_total_points = max(0, total_points - abs(xp))

    return calc_weekly_points, calc_total_points


async def process_xp_updates(interaction, sheet, usernames, reason, get_attendees=False, event_log=False):
    """
    Process XP updates for a single user or multiple users, constructing embed messages.

    This function handles finding users in a Google Sheet, checking for special conditions (e.g., 'IN', 'EX'),
    calculating new XP values based on the specified action ('add' or 'remove'), and compiling results into
    an embed for feedback. It supports both single and bulk updates efficiently by treating a single username
    input as a list with one item. It ensures that all updates are reflected in the Google Sheet and that
    detailed feedback is provided to the user through Discord embeds.

    Args:
        interaction (discord.Interaction): The Discord interaction initiating the command.
        sheet (gspread.Worksheet): The worksheet object from the gspread library, representing the Google Sheet to be updated.
        usernames (str | list): A single username (str) or a list of usernames (list) for whom the XP will be updated.
            If a single username is provided, it will be converted to a list for uniform processing.
        action (str): Specifies the XP update action to be performed. Should be either 'add' or 'remove' to indicate
            whether to add XP to or remove XP from the specified users' totals.
        xp (float): The amount of XP to be added or removed. The function includes checks to ensure that
            the operation does not result in negative XP totals.
        reason (str): The reason for the XP adjustment. This is used purely for logging and feedback purposes
            and does not affect the calculation of XP values.

    This function does not return any value. Instead, it sends an embed message directly to the Discord channel
    associated with the provided `interaction` object, detailing the results of the XP update operation.
    """
    if isinstance(usernames, str):
        usernames = [usernames.strip()]  # Ensure it's a list and strip any whitespace.

    embed = discord.Embed(
        title="XP Update",
        description=f"Processing XP update for {', '.join(usernames)}.\n**Reason:** {reason}",
        color=discord.Color.blurple()
    )

    console_output = ["```diff"]
    line_number = 1
    parsed_usernames = []
    username_to_disc_parsed = []
    all_usernames = sheet.col_values(2)[1:]

    for username in usernames:
        if "N/A" in username:
            continue
        if ":" not in username:
            warning_embed = discord.Embed(
                color=discord.Color.red(),
                title="XP Update Error",
                description=f"Invalid username format: `{username}`. Please use the format `username:XP` or `username:weekly_xp:total_xp`."
            )
            warning_embed.add_field(
                name="Need Help?",
                value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
            )
            await interaction.followup.send(embed=warning_embed, ephemeral=True)
            continue
        format = username.count(":")

        if format == 1:
            try:
                username, xp = username.split(":")
            except ValueError:
                warning_embed = discord.Embed(
                    color=discord.Color.red(),
                    title="XP Update Error",
                    description=f"Invalid username format: `{username}`. Please use the format `username:XP`."
                )
                warning_embed.add_field(
                    name="Need Help?",
                    value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
                )
                await interaction.followup.send(embed=warning_embed, ephemeral=True)
                continue
            try:
                xp = float(xp)
            except ValueError:
                warning_embed = discord.Embed(
                    color=discord.Color.red(),
                    title="XP Update Error",
                    description=f"Invalid XP value: `{xp}`. Please provide a valid integer value for XP."
                )
                warning_embed.add_field(
                    name="Need Help?",
                    value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
                )
                await interaction.followup.send(embed=warning_embed, ephemeral=True)
                continue
        elif format == 2:
            try:
                username, weekly_xp, total_xp = username.split(":")
            except ValueError:
                warning_embed = discord.Embed(
                    color=discord.Color.red(),
                    title="XP Update Error",
                    description=f"Invalid username format: `{username}`. Please use the format `username:weekly_xp:total_xp`."
                )
                warning_embed.add_field(
                    name="Need Help?",
                    value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
                )
                await interaction.followup.send(embed=warning_embed, ephemeral=True)
                continue
            try:
                weekly_xp = float(weekly_xp)
                total_xp = float(total_xp)
            except ValueError:
                warning_embed = discord.Embed(
                    color=discord.Color.red(),
                    title="XP Update Error",
                    description=f"Invalid XP value: `{weekly_xp}` or `{total_xp}`. Please provide a valid integer value for XP."
                )
                warning_embed.add_field(
                    name="Need Help?",
                    value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
                )
                await interaction.followup.send(embed=warning_embed, ephemeral=True)
                continue
        else:
            warning_embed = discord.Embed(
                color=discord.Color.red(),
                title="XP Update Error",
                description=f"Invalid username format: `{username}`. Please use the format `username:XP` or `username:weekly_xp:total_xp`."
            )
            warning_embed.add_field(
                name="Need Help?",
                value="Remember that even your Supervisors and Co-Hosts need to be in this format.",
            )
            await interaction.followup.send(embed=warning_embed, ephemeral=True)
            continue

        cell = sheet.find(username, case_sensitive=False)
        if not cell:
            close_matches = get_close_matches(username, all_usernames, n=1, cutoff=0.6)
            if close_matches:
                closest_username = close_matches[0]
                confirmation_embed = discord.Embed(
                    color=discord.Color.blurple(),
                    title="XP Update Confirmation",
                    description=f"The username `{username}` was not found. Did you mean `{closest_username}`?"
                )
                view = ConfirmationView()

                confirmation_message = await interaction.followup.send(embed=confirmation_embed, view=view,
                                                                       ephemeral=True)
                await view.wait()
                event_log = True

                if view.value is True:
                    # User confirmed the closest match
                    console_output.append(f"+ {line_number}: Proceeding with closest match: {closest_username}.")
                    await confirmation_message.edit(
                        content=f"Confirmed! Proceeding with the closest match: {closest_username}.", view=None)
                    cell = sheet.find(closest_username)
                    username = closest_username
                    line_number += 1
                else:
                    console_output.append(
                        f"- {line_number}: Error: {username} not found in spreadsheet, and no close match could be identified.")
                    line_number += 1
                    await confirmation_message.edit(
                        content=f"Confirmed! I won't proceed with this username then.", view=None)
                    continue
            else:
                console_output.append(
                    f"- {line_number}: Error: {username} not found in spreadsheet, and no close match could be identified.")
                line_number += 1
                continue

        user_row = cell.row
        weekly_points, total_points = sheet.cell(user_row, 8).value, sheet.cell(user_row, 9).value

        if weekly_points in ArasakaRanks.status_dict:
            status = ArasakaRanks.status_dict[weekly_points]
            console_output.append(f"- {line_number}: Warning: {username} is {status}. (WP will not be updated, only TP will be)")

        if format == 1:
            if abs(xp) > 50:
                console_output.append(f"- {line_number}: Error: You can only add/remove up to 50 XP at a time.")
                line_number += 1
                continue
            new_weekly_points, new_total_points = calculate_new_xp_values(weekly_points, total_points, xp)
        elif format == 2:
            if abs(weekly_xp) > 50 or abs(total_xp) > 50:
                console_output.append(f"- {line_number}: Error: You can only add/remove up to 50 XP at a time.")
                line_number += 1
                continue
            new_weekly_points, new_total_points = calculate_new_xp_values(weekly_points, total_points,
                                                                          [weekly_xp, total_xp])
        else:
            console_output.append(f"- {line_number}: Error: Invalid format for XP update.")
            line_number += 1
            continue

        values = [[new_weekly_points, new_total_points]]
        sheet.update(values, f'H{user_row}:I{user_row}')

        # Use the RobloxDiscordLinker class to get the Discord ID
        linker = RobloxDiscordLinker(interaction.client, interaction.guild.id, sheet)
        disc_id = linker.roblox_username_to_discord_id(username)

        if get_attendees:
            username_to_disc_parsed.append(disc_id)
        q: database.EventLoggingRecords = database.EventLoggingRecords.create(
            datetime_object=datetime.now(tz=pytz.timezone("America/New_York")),
            host_username=interaction.user.display_name,
            host_id=interaction.user.id,
            event_type=reason,
            attendee_username=username,
            attendee_id=disc_id if isinstance(disc_id, int) else 0,
            xp_awarded=weekly_xp if format == 2 else xp,
        )
        q.save()

        if format == 1:
            if xp >= 0:
                action = "gained"
            else:
                action = "lost"
            console_output.append(
                f"+ {line_number}: Success: {username} {action} {abs(xp)} XP.")
        else:
            if weekly_xp >= 0:
                w_action = "gained"
            else:
                w_action = "lost"

            if total_xp >= 0:
                t_action = "gained"
            else:
                t_action = "lost"
            console_output.append(
                f"+ {line_number}: Success: {username} {w_action} {abs(weekly_xp)} weekly XP and {t_action} {abs(total_xp)} total XP.")
        line_number += 1
        parsed_usernames.append(username)

    console_output.append("```")
    embed.add_field(name="Console Output:", value="\n".join(console_output), inline=False)
    embed.set_footer(text=f"Authorized by: {interaction.user.display_name}")

    if not event_log:
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                print(e)

    xp_channel = await interaction.client.fetch_channel(LoggingChannels.xp_log_ch)
    await xp_channel.send(embed=embed)

    if get_attendees:
        if len(parsed_usernames) > 0:
            users_d = [f"<@{username_to_disc_parsed}>" if isinstance(username_to_disc_parsed, int) else username_to_disc_parsed for username_to_disc_parsed in username_to_disc_parsed]

            formatted_message = f"{', '.join(users_d)}\n\n**<:bot:1227807111660961822> Your XP has been updated by {interaction.user.mention}!**\n> Feel free to review your XP with </xp view:1224925340506390538> in <#1143717377738022992>"
            general_channel = await interaction.guild.fetch_channel(1143716666392457226)
            await general_channel.send(formatted_message)


async def get_user_xp_data(discord_username, sheet, bot=None, guild_id=None):
    """
    Fetches the rank, weekly XP, and total XP for a user from a Google Sheet.

    This function is kept for backward compatibility. It now uses the RobloxDiscordLinker class
    if bot and guild_id are provided, otherwise it falls back to the old implementation.

    Args:
        discord_username (str): The Discord username to search for in the Google Sheet.
        sheet (gspread.Worksheet): The worksheet object from the gspread library.
        bot (discord.Client, optional): The Discord bot instance.
        guild_id (int, optional): The ID of the Discord guild.

    Returns:
        dict | None: A dictionary containing the user's rank, weekly XP, and total XP if the user is found in the Google Sheet.
            Returns None if the user is not found.
    """
    # If bot and guild_id are provided, use the new RobloxDiscordLinker class
    if bot and guild_id:
        linker = RobloxDiscordLinker(bot, guild_id, sheet)
        return await linker.get_user_xp_data(discord_username)

    # Otherwise, fall back to the old implementation
    # Assuming that the first column A contains Discord IDs as strings
    cell = sheet.find(str(discord_username), in_column=2, case_sensitive=False)
    if not cell:
        return None  # User not found

    # Fetch the entire row where the user is found
    user_row = sheet.row_values(cell.row)
    print(user_row[2], user_row, cell.row)

    # Assuming the rank is in column E and the total XP is in column K
    user_data = {
        'rank': user_row[3],  # Index 4 corresponds to column E
        'weekly_xp': user_row[7],  # Index 9 corresponds to column J
        'total_xp': float(user_row[8])  # Index 10 corresponds to column K
    }

    return user_data


def find_next_rank(current_rank_full_name, total_xp, rank_xp_thresholds):
    """
    Find the next rank and the remaining XP needed to reach it based on the current rank and total XP.

    Args:
        current_rank_full_name (str): The full name of the current rank.
        total_xp (float): The total XP of the user.
        rank_xp_thresholds (dict): A dictionary mapping rank names to their corresponding XP thresholds.

    Returns:
        tuple[str, float] | tuple[None, None]: A tuple containing the name of the next rank and the remaining XP needed to reach it.
            Returns (None, None) if the current rank is not found in the rank thresholds.

    """
    ranks_ordered = list(rank_xp_thresholds.keys())
    try:
        current_rank_index = ranks_ordered.index(current_rank_full_name)
    except ValueError:
        return None, None

    for next_rank_index in range(current_rank_index + 1, len(ranks_ordered)):
        next_rank = ranks_ordered[next_rank_index]
        next_rank_xp = rank_xp_thresholds[next_rank]
        if total_xp < next_rank_xp:
            return next_rank, next_rank_xp - total_xp
    return None, None


class RankHierarchy:
    """
    A class that represents a rank hierarchy with associated XP thresholds that can compute specific rank-related operations.

    Attributes:
      group_id (int): The group ID associated with the rank hierarchy.
      sheet (gspread.Worksheet): The worksheet object from the gspread library.
      officer_rank (str): The rank of the officer who is performing rank-related operations.
      client (Client): The Bloxlink client for fetching Roblox usernames.
      ranks (list): A list of rank names in descending order of hierarchy.

    Methods:
        set_officer_rank(officer): Set the officer's rank based on their Discord ID.
        discord_to_roblox(discord_id, group): Convert a Discord ID to a Roblox user in the group.
        get_rank(roblox_username): Get the rank of a user based on their Roblox username.
        next_rank(current_rank): Get the next rank based on the current rank.
        back_rank(current_rank): Get the previous rank based on the current rank.
        return_rank_enum(): Return the ranks lower than the officer's rank. (Used for Autocomplete Operations)
        return_officer_rank(): Return the officer's rank.
        return_raw_group_rank(formatted_rank): Return the raw rank name based on the formatted rank name.
    """

    def __init__(self, group_id: int, sheet, officer_rank: str = None):
        self.group_id = group_id
        self.sheet = sheet
        self.officer_rank = officer_rank
        self.client = Client(os.getenv("ROBLOX_SECURITY"))
        self.ranks = [
            "Big Boss of Arasaka"
            "Clan Leader",  # Highest
            "Chief Executive Officer",
            "Chief Executive Secretary",
            "Board of Directors",
            "Chief Corporate Field Officer",
            "Senior Corporate Field Officer",
            "Corporate Field Officer",
            "Junior Corporate Field Officer",
            "Corporate Officer on Trial",
            "Commander",
            "Command Sergeant",
            "Sergeant",
            "Senior Agent",
            "Specialist",
            "Operative",
            "Junior Operative",
            "Initiate",
            "Civilian"  # Lowest
        ]

    async def set_officer_rank(self, officer: discord.Member):
        # Use the RobloxDiscordLinker class
        linker = RobloxDiscordLinker(officer.guild._client, officer.guild.id, self.sheet)
        roblox_username = await linker.discord_id_to_roblox_username(officer.id)

        if roblox_username:
            user_data = await linker.get_user_xp_data(roblox_username)
            if user_data:
                self.officer_rank = user_data['rank']
                return roblox_username
            else:
                raise ValueError("User not found in the Google Sheet.")
        else:
            raise ValueError("Could not find Roblox username for this Discord user.")

    def discord_to_roblox(self, discord_id, group):
        # Use the RobloxDiscordLinker class
        linker = RobloxDiscordLinker(None, LoggingChannels.guild, None)
        return linker.discord_id_to_roblox_user(discord_id, group)

    async def get_rank(self, roblox_username):
        # Use the RobloxDiscordLinker class
        linker = RobloxDiscordLinker(None, LoggingChannels.guild, self.sheet)
        user_data = await linker.get_user_xp_data(roblox_username)
        if user_data:
            return user_data['rank']
        return None

    def next_rank(self, current_rank):
        """Return the next higher rank based on the current rank,
        unless the officer's rank is not high enough."""
        if self.officer_rank not in self.ranks or current_rank not in self.ranks:
            return None

        officer_index = self.ranks.index(self.officer_rank)
        current_index = self.ranks.index(current_rank)

        # Check if officer's rank is lower than the current rank
        if officer_index <= current_index:
            return -1  # Officer does not have authority to promote/demote

        next_index = current_index - 1
        if next_index >= 0:
            return self.ranks[next_index]
        else:
            return None

    def back_rank(self, current_rank):
        """Return the next lower rank based on the current rank,
        unless the officer's rank is not high enough."""
        if self.officer_rank not in self.ranks or current_rank not in self.ranks:
            return None

        officer_index = self.ranks.index(self.officer_rank)
        current_index = self.ranks.index(current_rank)

        # Check if officer's rank is lower than or equal to the current rank
        if officer_index <= current_index:
            return -1  # Officer does not have authority to promote/demote

        back_index = current_index + 1
        if back_index < len(self.ranks):
            return self.ranks[back_index]
        else:
            return None

    def return_rank_enum(self):
        # return ranks lower than the officer
        ranks = [
            "[CH] Big Boss of Arasaka"
            "[CL] Clan Leader",  # Highest
            "[H-3] Chief Executive Officer",
            "[H-2] Chief Executive Secretary",
            "[H-1] Board of Directors",
            "[O-4] Chief Corporate Field Officer",
            "[O-3] Senior Corporate Field Officer",
            "[O-2] Corporate Field Officer",
            "[O-1] Junior Corporate Field Officer",
            "[COOT] Corporate Officer on Trial",
            "[N-3] Commander",
            "[N-2] Command Sergeant",
            "[N-1] Sergeant",
            "[A-5] Senior Agent",
            "[A-4] Specialist",
            "[A-3] Operative",
            "[A-2] Junior Operative",
            "[A-1] Initiate",
            "Civilian"  # Lowest
        ]
        officer_index = self.ranks.index(self.officer_rank)
        return ranks[officer_index + 1:]

    def return_officer_rank(self):
        return self.officer_rank

    def return_raw_group_rank(self, formatted_rank):
        raw_ranks = [
            "[CH] Big Boss of Arasaka"
            "[CL] Clan Leader",  # Highest
            "[H-3] Chief Executive Officer",
            "[H-2] Chief Executive Secretary",
            "[H-1] Board of Directors",
            "[O-4] Chief Corporate Field Officer",
            "[O-3] Senior Corporate Field Officer",
            "[O-2] Corporate Field Officer",
            "[O-1] Junior Corporate Field Officer",
            "[COOT] Corporate Officer on Trial",
            "[N-3] Commander",
            "[N-2] Command Sergeant",
            "[N-1] Sergeant",
            "[A-5] Senior Agent",
            "[A-4] Specialist",
            "[A-3] Operative",
            "[A-2] Junior Operative",
            "[A-1] Initiate",
            "Civilian"  # Lowest
        ]
        # find the formatted_rank in self.ranks and return the raw rank

        return raw_ranks[self.ranks.index(formatted_rank)]
