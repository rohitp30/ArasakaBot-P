import os
import typing

import discord
from discord import app_commands
from discord.ext import commands
from sentry_sdk import start_transaction

from core.common import (
    process_xp_updates, RankHierarchy, LoggingChannels, SheetsClient, RobloxClient
)
from core.logging_module import get_log
from core import event_quota

_log = get_log(__name__)
sheet = SheetsClient().sheet
RClient = RobloxClient().client

class EventLogging(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.group_id = 33764698
        self.interaction = []

    XPM = app_commands.Group(
        name="xp_manage",
        description="Update XP for users in the spreadsheet.",
        guild_ids=[1223473430410690630, 1143709921326682182],
    )

    # noinspection PyInconsistentReturns
    @XPM.command(description="Bulk update the XP of multiple users or a single user.")
    @app_commands.describe(
        usernames="Enter the usernames (COMMA SEPARATED) of the users you want to update.",
        reason="Enter a reason for the XP update. (You can just say the event type)",
        ping_attendees="Ping attendees in the general chat saying their XP has been updated.",
        event_type="Identify the type of event for quota tracking.",
    )
    async def update(
            self,
            interaction: discord.Interaction,
            usernames: str,
            reason: str,
            event_type: typing.Literal["Spar", "Gamenight", "General Training", "Agent Rally", "Combat Training", "VBR GT", "Disciplinary Training"],
            ping_attendees: bool = True,
    ):
        o_two = discord.utils.get(interaction.guild.roles, id=1143729159479234590)
        o_three = discord.utils.get(interaction.guild.roles, id=1156342512500351036)
        o_four = discord.utils.get(interaction.guild.roles, id=1143729281806127154)
        high_command = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
        retired_hicom_role = discord.utils.get(interaction.guild.roles, id=1192942534968758342)

        # Permission check
        if not any(role in interaction.user.roles for role in
                   [o_two, o_three, o_four, high_command, retired_hicom_role]) and interaction.user.id not in [
            409152798609899530]:  # List of allowed user IDs can be expanded
            return await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )

        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            # Acknowledge the command invocation
            await interaction.response.defer(ephemeral=True, thinking=True)
            usernames = [username.strip() for username in usernames.split(",")]
            await process_xp_updates(interaction, sheet, usernames, reason, ping_attendees)

            # Add event to quota database
            await event_quota.add_event_to_quota(interaction.user.id, event_type)

            # Update the event quota embed
            # Channel ID 1 and Message ID 2 are placeholders - replace with actual IDs
            channel_id = int(os.getenv("QUOTA_CHANNEL_ID", "1"))
            message_id = int(os.getenv("QUOTA_MESSAGE_ID", "0"))

            # Update or create the quota embed
            new_message_id = await event_quota.update_quota_embed(self.bot, channel_id, message_id)

            # If this is a new message or the message ID has changed, update the environment variable
            if new_message_id and new_message_id != message_id:
                os.environ["QUOTA_MESSAGE_ID"] = str(new_message_id)
                _log.info(f"Updated QUOTA_MESSAGE_ID to {new_message_id}")


    @XPM.command(description="Change the XP status of a user.")
    @app_commands.describe(
        username="Enter the username of the user you want to update.",
        action="Select the action you want to perform. (IN = Inactivity Notice, EX = Exempt, clear = Clear status: this will give them 0 for WP.)",
    )
    async def modify_status(
            self,
            interaction: discord.Interaction,
            username: str,
            action: typing.Literal["RH", "IN", "EX", "clear"],
    ):
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            embed = discord.Embed(
                title="XP Status Modification",
                description="Modifying XP status for a single user...",
                color=discord.Color.dark_gold()
            )
            embed.add_field(
                name="Action",
                value=f"Executing change to {action} for the following user: {username}",
                inline=False,
            )
            embed.add_field(
                name="Console Output:",
                value="```diff\n1: In Progress...",
                inline=False,
            )
            line_number = 1

            if interaction.user.id == 882526905679626280:
                return await interaction.response.send_message(
                    "You do not have permission to use this command.",
                    ephemeral=True,
                )

            xp_channel = await self.bot.fetch_channel(LoggingChannels.xp_log_ch)
            officer_role = discord.utils.get(interaction.guild.roles, id=LoggingChannels.officer_role_id)
            retired_hicom_role = discord.utils.get(interaction.guild.roles, id=1192942534968758342)

            if not officer_role in interaction.user.roles and not retired_hicom_role in interaction.user.roles:
                if interaction.user.id == 409152798609899530:
                    pass
                else:
                    return await interaction.response.send_message(
                        "You do not have permission to use this command.",
                        ephemeral=True,
                    )

            cell = sheet.find(username, case_sensitive=False)
            await interaction.response.send_message(embed=embed)

            if cell is None:
                field = embed.fields[1].value + f"\n- {line_number + 1}: Error: {username} not found in spreadsheet.\n```"
                embed.set_field_at(1, name="Console Output:", value=field)
                return await interaction.edit_original_response(embed=embed)

            user_row = cell.row

            if action == "IN":
                new_weekly_points = "IN"
            elif action == "EX":
                new_weekly_points = "EX"
            elif action == "RH":
                new_weekly_points = "RH"
            else:
                new_weekly_points = 0

            values = [[new_weekly_points]]
            sheet.update(values, f'H{user_row}')

            field = embed.fields[
                        1].value + f"\n+ {line_number + 1}: Success: {username} -> **({action})** updated status!\n```"
            embed.set_field_at(1, name="Console Output:", value=field)
            embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | XP STATUS UPDATE")
            await interaction.edit_original_response(embed=embed)
            await xp_channel.send(embed=embed)


    @XPM.command(
        name="set_rank",
        description="Manage the ranks of users in the Roblox Group."
    )
    async def rank_manage(
            self,
            interaction: discord.Interaction,
            reason: str,
            roblox_usernames: str = None,
            discord_username: discord.Member = None,
            target_rank: str = None,
    ):
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            Officer_four = discord.utils.get(interaction.guild.roles, id=1143729281806127154)
            HICOM = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
            BIGBOSS = discord.utils.get(interaction.guild.roles, id=1163157560237510696)
            ClanLeader = discord.utils.get(interaction.guild.roles, id=1158472045248651434)
            if not any(role in interaction.user.roles for role in
                       [HICOM, BIGBOSS, ClanLeader, Officer_four]) and interaction.user.id not in [409152798609899530]:
                return await interaction.response.send_message("You do not have permission to use this command.",
                                                               ephemeral=True)

            if not roblox_usernames and not discord_username:
                return await interaction.response.send_message("You must provide a target user.", ephemeral=True)

            await interaction.response.defer()

            rank_obj = RankHierarchy(self.group_id, sheet)
            await rank_obj.set_officer_rank(interaction.user)

            group = await RClient.get_group(self.group_id)

            if discord_username:
                r_user = rank_obj.discord_to_roblox(discord_username.id, group)
                confirm_name = discord_username.display_name
                roblox_usernames = [confirm_name]  # For uniform handling below
            else:
                roblox_usernames = [name.strip() for name in roblox_usernames.split(",")]

            action = "change"

            for roblox_username in roblox_usernames:
                try:
                    r_user = await group.get_member_by_username(roblox_username)
                    confirm_name = roblox_username

                    if target_rank != "[KICK FROM GROUP] Remove/Exile User from Group":
                        roles = await group.get_roles()
                        await group.set_role(r_user.id, next((role.id for role in roles if role.name == target_rank), None))

                        confirmation_embed = discord.Embed(
                            title="Rank Change",
                            description=f"Successfully {action}d {confirm_name} to {target_rank}.",
                            color=discord.Colour.green(),
                        )
                        confirmation_embed.add_field(name="Reason", value=reason)
                        await interaction.followup.send(embed=confirmation_embed)

                        log_channel = self.bot.get_channel(LoggingChannels.xp_log_ch)
                        log_embed = discord.Embed(
                            title="Rank Change",
                            description=f"Successfully {action}d {confirm_name} to {target_rank}.",
                            color=discord.Colour.green(),
                        )
                        log_embed.add_field(name="Reason", value=reason)
                        log_embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | RANK CHANGE")
                        await log_channel.send(embed=log_embed)
                        return None
                    else:
                        await group.kick_user(r_user.id)

                        confirmation_embed = discord.Embed(
                            title="Rank Change",
                            description=f"Successfully kicked {confirm_name} from the group.",
                            color=discord.Colour.green(),
                        )
                        confirmation_embed.add_field(name="Reason", value=reason)
                        await interaction.followup.send(embed=confirmation_embed)

                        log_channel = self.bot.get_channel(LoggingChannels.xp_log_ch)
                        log_embed = discord.Embed(
                            title="Rank Change",
                            description=f"Successfully kicked {confirm_name} from the group.",
                            color=discord.Colour.green(),
                        )
                        log_embed.add_field(name="Reason", value=reason)
                        log_embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | GROUP REMOVAL")
                        await log_channel.send(embed=log_embed)
                        return None
                except Exception as e:
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Failed to {action} {confirm_name} to {target_rank}.",
                        color=discord.Colour.red(),
                    )
                    error_embed.add_field(name="Error", value=str(e))
                    await interaction.followup.send(embed=error_embed)
                    return None
            return None

    @rank_manage.autocomplete('target_rank')
    async def rank_manage_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> typing.List[app_commands.Choice[str]]:
        raw_ranks = [
            "[O-2] Corporate Field Officer",
            "[O-1] Junior Corporate Field Officer",
            "[COOT] Corporate Officer on Trial",
            "[O-1] Junior Corporate Field Officer",
            "[N-3] Commander",
            "[N-2] Command Sergeant",
            "[N-1] Sergeant",
            "[A-5] Senior Agent",
            "[A-4] Specialist",
            "[A-3] Operative",
            "[A-2] Junior Operative",
            "[A-1] Initiate",
            "Civilian",  # Lowest
            "[KICK FROM GROUP] Remove/Exile User from Group",
        ]

        return [
            app_commands.Choice(name=rank, value=rank)
            for rank in raw_ranks if current.lower() in rank.lower()
        ]

    @XPM.command(name="quota", description="Update or initialize the event quota embed.")
    @app_commands.describe(
        channel_id="The channel ID where the embed should be displayed (default: from env var).",
        message_id="The message ID to update (default: from env var or create new).",
    )
    async def update_quota_embed(
            self,
            interaction: discord.Interaction,
            channel_id: str = None,
            message_id: str = None,
    ):
        # Permission check
        o_two = discord.utils.get(interaction.guild.roles, id=1143729159479234590)
        o_three = discord.utils.get(interaction.guild.roles, id=1156342512500351036)
        o_four = discord.utils.get(interaction.guild.roles, id=1143729281806127154)
        high_command = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
        retired_hicom_role = discord.utils.get(interaction.guild.roles, id=1192942534968758342)

        if not any(role in interaction.user.roles for role in
                   [o_two, o_three, o_four, high_command, retired_hicom_role]) and interaction.user.id not in [
            409152798609899530]:
            return await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Use provided values or defaults from environment variables
            ch_id = int(channel_id) if channel_id else int(os.getenv("QUOTA_CHANNEL_ID", "1"))
            msg_id = int(message_id) if message_id else int(os.getenv("QUOTA_MESSAGE_ID", "0"))

            # Update or create the quota embed
            new_message_id = await event_quota.update_quota_embed(self.bot, ch_id, msg_id if msg_id != 0 else None)

            # If this is a new message or the message ID has changed, update the environment variable
            if new_message_id and (msg_id == 0 or new_message_id != msg_id):
                os.environ["QUOTA_MESSAGE_ID"] = str(new_message_id)
                os.environ["QUOTA_CHANNEL_ID"] = str(ch_id)
                _log.info(f"Updated QUOTA_MESSAGE_ID to {new_message_id} and QUOTA_CHANNEL_ID to {ch_id}")

            await interaction.followup.send(
                f"Event quota embed has been {'updated' if msg_id != 0 else 'created'} in channel {ch_id}.",
                ephemeral=True
            )
        except Exception as e:
            _log.error(f"Error updating event quota embed: {e}")
            await interaction.followup.send(
                f"Error updating event quota embed: {e}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EventLogging(bot))
