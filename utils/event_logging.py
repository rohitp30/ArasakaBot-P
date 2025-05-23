import os
import typing
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from roblox import Client
from sentry_sdk import start_transaction

from core.common import (
    process_xp_updates, RankHierarchy, LoggingChannels, SheetsClient
)
from core.logging_module import get_log

_log = get_log(__name__)
sheet = SheetsClient().sheet


XP = app_commands.Group(
    name="xp",
    description="Update XP for users in the spreadsheet.",
    guild_ids=[1223473430410690630, 1143709921326682182],
)

class EventLogging(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.ROBLOX_client = Client(os.getenv("ROBLOX_SECURITY"))
        self.group_id = 33764698
        self.interaction = []


    @XP.command(description="Bulk update the XP of multiple users or a single user.")
    @app_commands.describe(
        usernames="Enter the usernames (COMMA SEPARATED) of the users you want to update.",
        reason="Enter a reason for the XP update. (You can just say the event type)",
        ping_attendees="Ping attendees in the general chat saying their XP has been updated.",
    )
    async def update(
            self,
            interaction: discord.Interaction,
            usernames: str,
            reason: str,
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

        # Acknowledge the command invocation
        await interaction.response.defer(ephemeral=True, thinking=True)
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            usernames = [username.strip() for username in usernames.split(",")]
            await process_xp_updates(interaction, sheet, usernames, reason, ping_attendees)

    @XP.command(description="Change the XP status of a user.")
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


    @XP.command(
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

        group = await self.ROBLOX_client.get_group(self.group_id)

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

    @XP.command(
        name="update_discord_ids_in_sheet",
        description="Update the Discord IDs in the XP sheet. | BOT OWNER ONLY"
    )
    async def update_discord_ids_in_sheet(
            self,
            interaction: discord.Interaction
    ):
        if interaction.user.id != 409152798609899530:
            return await interaction.response.send_message("You do not have permission to use this command. | **Bot Owner ONLY**", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        # okay so for all the members in test_sheet column 2, we need to find their discord ID and update it in the same row but in column 8
        members = sheet.col_values(1)
        for member in members[1:]:
            username = member
            member = member.strip()
            member = member.replace(" ", "")
            member = discord.utils.get(interaction.guild.members, display_name=member)
            if member:
                discord_id = member.id
                cell = sheet.find(member.display_name)
                sheet.update_cell(cell.row, 17, f":{discord_id}")
            else:
                print(f"Could not find Discord ID for {username}")

        await interaction.followup.send("Discord IDs have been populated in the XP sheet.", ephemeral=True)

    @XP.command(
        name="blacklist",
        description="Blacklist a user from the group. | HICOM+ ONLY"
    )
    async def blacklist(
            self,
            interaction: discord.Interaction,
            discord_user: discord.Member,
            roblox_username: str,
            reason: str,
            appealable: bool,
            end_date: str = "-"
    ):
        return await interaction.response.send_message("Not in operation...")
        HICOM = discord.utils.get(interaction.guild.roles, id=1143736740075552860)
        BIGBOSS = discord.utils.get(interaction.guild.roles, id=1163157560237510696)
        ClanLeader = discord.utils.get(interaction.guild.roles, id=1158472045248651434)
        if not any(role in interaction.user.roles for role in
                   [HICOM, BIGBOSS, ClanLeader]) and interaction.user.id not in [409152798609899530]:
            return await interaction.response.send_message("You do not have permission to use this command.",
                                                           ephemeral=True)
        if interaction.user.id == discord_user.id:
            return await interaction.response.send_message("You cannot blacklist yourself.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        kicked = False
        dmed = False
        error_message = "N/A"

        group = await self.ROBLOX_client.get_group(self.group_id)
        user = await group.get_member_by_username(roblox_username)
        try:
            await user.kick()
            kicked = True
        except Exception as e:
            error_message = e

        # sheet update now
        workspace = client.open("Arasaka Corp. Database V2").worksheet("Blacklists")
        today_date = datetime.now().strftime("%m/%d/%Y")

        def next_available_row(worksheet):
            return len(worksheet.col_values(2)) + 1

        # status calculation
        if end_date == "-":
            status = "PERMANENT"
        else:
            status = "BLACKLISTED"
        reason += " | Appealable: " + str(appealable)
        values = [[roblox_username, "", today_date, end_date, status, reason]]
        workspace.update(f'A{next_available_row(workspace)}:F{next_available_row(workspace)}', values)

        try:
            await discord_user.send(f"You have been blacklisted from Arasaka Corp. for the following reason: {reason}\n**Appealable:** {appealable} | **End Date:** {end_date}\n\nForward any questions to {interaction.user.mention}.")
            dmed = True
        except discord.Forbidden:
            pass
        await discord_user.ban(reason=f"User {roblox_username} has been blacklisted from the group for the following reason: {reason} by {interaction.user.display_name}")

        # make en embed detailing what it was able to do and what it wasn't
        embed = discord.Embed(
            title="Blacklist Report",
            color=discord.Color.red()
        )
        embed.add_field(name="User", value=discord_user.mention, inline=False)
        kicked = "✅" if kicked else f"❌ | {error_message}"
        dmed = "✅" if dmed else "❌"
        banned_from_discord = "✅"
        appealable = "✅" if appealable else "❌"
        embed.add_field(
            name="Actions Executed",
            value=f"""
            **Kicked from Roblox Group:**  {kicked}
            **DM Sent:**  {dmed}
            **Banned from Discord:**  {banned_from_discord}
            **Appealable:**  {appealable}
            
            **Blacklist Reason:**  {reason}
            """,
            inline=False
        )
        embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | BLACKLIST")
        await interaction.followup.send(embed=embed)

        log_channel = self.bot.get_channel(xp_log_ch)
        await log_channel.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EventLogging(bot))
