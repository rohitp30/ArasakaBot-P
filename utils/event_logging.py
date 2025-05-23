import os
import typing
from datetime import datetime

import discord
import gspread
from discord import app_commands
from discord.ext import commands
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from roblox import Client

from core import database
from core.common import (
    make_form, process_xp_updates, get_user_xp_data, RankHierarchy, ConfirmationView,
    PromotionButtons, InactivityModal, DischargeModel, retrieve_discord_user,
)
from core.logging_module import get_log

_log = get_log(__name__)

log_ch = 1145110858272346132
guild = 1143709921326682182

xp_log_ch = 1224907141060628532
officer_role_id = 1143736564002861146

rank_xp_thresholds = {
    'Initiate': 0,  # A-1
    'Junior Operative': 15,  # A-2
    'Operative': 30,  # A-3
    'Specialist': 50,  # A-4
    'Senior Agent': 80,  # A-5
    'Sergeant': 120,  # N-1
    #'Command Sergeant': 150,  # N-2
    #'Commander': 200,  # N-3
    # ... continue as needed
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

next_rank = {
    'Initiate': 'Junior Operative',
    'Junior Operative': 'Operative',
    'Operative': 'Specialist',
    'Specialist': 'Senior Agent',
    'Senior Agent': 'Sergeant',
    'Sergeant': 'RL',
    #'Command Sergeant': 'Commander',
    #'Commander': '🔒'
}

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('ArasakaBotCreds.json', scope)
client = gspread.authorize(creds)
sheet = client.open("Arasaka Corp. Database V2").sheet1
print(sheet)

AI_client = OpenAI(
    api_key=os.getenv("OPENAI_API"),
)

class EventLogging(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.ROBLOX_client = Client(os.getenv("ROBLOX_SECURITY"))
        self.group_id = 33764698
        self.interaction = []

    XP = app_commands.Group(
        name="xp",
        description="Update XP for users in the spreadsheet.",
        guild_ids=[1223473430410690630, 1143709921326682182],
    )

    @app_commands.command(
        name="event_log",
        description="Log an event | Event Hosts Only",
    )
    @app_commands.guilds(1223473430410690630, 1143709921326682182)
    @app_commands.describe(
        host_username="Enter the event host's ROBLOX username (this should be yours).",
        event_type_opt="Select the event type you hosted.",
        proof_upload="Upload proof of the event. THIS IS NOT REQUIRED IF YOU WOULD RATHER UPLOAD A LINK AS PROOF.",
        ping_attendees="Ping attendees in the general chat saying their XP has been updated.",
    )
    async def event_log(
            self,
            interaction: discord.Interaction,
            host_username: str,
            event_type_opt: typing.Literal["General Training", "Combat Training", "Agent Rally", "Gamenight", "Other"],
            proof_upload: discord.Attachment = None,
            ping_attendees: bool = True,
    ):
        bot_ref = self.bot
        event_host_role = discord.utils.get(interaction.guild.roles, id=1143736564002861146)
        #event_host_role = discord.utils.get(interaction.guild.roles, id=1223480830920229005) test role
        retired_hicom_role = discord.utils.get(interaction.guild.roles, id=1192942534968758342)
        return await interaction.response.send_message("Not in operation...")

        if not any(role in interaction.user.roles for role in
                   [event_host_role, retired_hicom_role]) and interaction.user.id not in [
            409152798609899530]:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        EventLogForm = make_form(host_username, event_type_opt, proof_upload, bot_ref, sheet, ping_attendees)
        await interaction.response.send_modal(EventLogForm(title="Event Logging Form"))

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

        xp_channel = await self.bot.fetch_channel(xp_log_ch)
        officer_role = discord.utils.get(interaction.guild.roles, id=officer_role_id)
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
        name="view",
        description="View XP and progress towards the next rank for yourself or another user."
    )
    @app_commands.describe(
        target_user="The user whose XP you want to view. Leave empty to view your own XP.",
        roblox_username="If the user has not linked/updated their Discord username to be their Roblox username, you can manually provide their Roblox username here."
    )
    async def _view(
            self,
            interaction: discord.Interaction,
            target_user: discord.Member = None,
            roblox_username: str = None,
    ):
        if target_user and roblox_username:
            confirmation_embed = discord.Embed(
                color=discord.Color.brand_red(),
                title="Too Many Arguments!",
                description=f"Hey {interaction.user.mention}, you provided both a discord user and a roblox username. "
                            f"Please provide only one!"
            )
            return await interaction.response.send_message(embed=confirmation_embed, ephemeral=True)
        await interaction.response.defer(thinking=True)

        if roblox_username:
            target_user = roblox_username
        elif target_user:
            target_user = target_user
        else:
            target_user = interaction.user
        promoted = False

        if isinstance(target_user, discord.Member) or isinstance(target_user, discord.User):
            user_data = await get_user_xp_data(target_user.display_name, sheet)
            if not user_data:
                query = database.DiscordToRoblox.select().where(
                    database.DiscordToRoblox.discord_id == target_user.id
                )
                if query.exists():
                    query = query.get()
                    roblox_username = query.roblox_username
                    user_data = await get_user_xp_data(roblox_username, sheet)
                    if user_data is None:
                        confirmation_embed = discord.Embed(
                            color=discord.Color.brand_red(),
                            title="Unknown Roblox Username",
                            description=f"Hey {interaction.user.mention}, I couldn't find the roblox username for data for "
                                        f"the user you specified."
                        )
                        confirmation_embed.add_field(
                            name="Resolutions",
                            value="Your DISCORD Username is *clearly* not your Roblox username. Use the `roblox_username` field in the slash command to find yourself/whoever."
                        )
                        return await interaction.followup.send(embed=confirmation_embed, ephemeral=True)

                else:
                    confirmation_embed = discord.Embed(
                        color=discord.Color.brand_red(),
                        title="Unknown Roblox Username",
                        description=f"Hey {interaction.user.mention}, I couldn't find the roblox username for data for "
                                    f"the user you specified."
                    )
                    confirmation_embed.add_field(
                        name="Resolutions",
                        value="Your DISCORD Username is *clearly* not your Roblox username. Use the `roblox_username` field in the slash command to find yourself/whoever."
                    )
                    return await interaction.followup.send(embed=confirmation_embed, ephemeral=True)
        else:
            user_data = await get_user_xp_data(target_user, sheet)
            if user_data is None:
                confirmation_embed = discord.Embed(
                    color=discord.Color.brand_red(),
                    title="Unknown Roblox Username",
                    description=f"Hey {interaction.user.mention}, I couldn't find the roblox username for data for "
                                f"the user you specified."
                )
                confirmation_embed.add_field(
                    name="Resolutions",
                    value="Your DISCORD Username is *clearly* not your Roblox username. Use the `roblox_username` field in the slash command to find yourself/whoever."
                )
                return await interaction.followup.send(embed=confirmation_embed, ephemeral=True)

        current_rank_full_name = user_data['rank']
        total_xp = user_data['total_xp']
        ranks = ["Initiate", "Junior Operative", "Operative", "Specialist", "Senior Agent", "Sergeant", "RL"]

        next_rank_name_bool = True

        if current_rank_full_name not in ranks and current_rank_full_name != "Sergeant":
            next_rank_name = "🔒"
        elif current_rank_full_name == "Sergeant":
            next_rank_name = "🔒*"
        else:
            next_rank_name = next_rank.get(current_rank_full_name)

        quota_req = quota_dict.get(current_rank_full_name)

        # Create the progress bar
        if next_rank_name != '🔒' and next_rank_name != '🔒*':
            xp_to_next_rank = rank_xp_thresholds.get(next_rank_name, 0) - total_xp
            progress_percentage = (total_xp - rank_xp_thresholds[current_rank_full_name]) / (
                    rank_xp_thresholds[next_rank_name] - rank_xp_thresholds[current_rank_full_name])

            filled_slots = int(max(0, min(progress_percentage, 1)) * 10)
            empty_slots = 10 - filled_slots
            progress_bar = '🟥' * filled_slots + '⬛' * empty_slots + f" **{round(progress_percentage * 100, 2)}%**"
            if progress_percentage >= 1:
                promoted = True
                progress_bar = '🟥' * filled_slots + '⬛' * empty_slots + f" **100%** | **Pending Promotion**"

            # Quota Field (they meet quota if they have 8 or more WP)
            if user_data['weekly_xp'] == "IN":
                quota = "**You're marked as on being inactivity notice, so you're exempt from the quota for this week.**"
            elif user_data['weekly_xp'] == "EX":
                quota = "**You're marked as being exempt from quota.**"
            else:
                weekly_xp = user_data['weekly_xp']
                if weekly_xp == "RH":
                    quota = f"✅ You're marked as being a new recruit, so you're exempt from the quota for this week!"
                else:
                    quota = (
                        f"<:8410joshhutchersonwhistle:1189723626266693702> **{weekly_xp}**/{quota_req} WP"
                        if float(weekly_xp) > 20
                        else f"✅ **{weekly_xp}**/{quota_req} WP"
                        if float(weekly_xp) >= quota_req
                        else f"⬛ **{weekly_xp}**/{quota_req} WP"
                    )
        elif next_rank_name == "🔒*":
            progress_bar = '⬛' * 10 + '🔒'
            xp_to_next_rank = 'N/A'
            next_rank_name_bool = False
            next_rank_name = "N/A: **Rank Locked**\n\n**N-1** is the highest non-commissioned rank in the group. Congratulations on reaching the top! Contact an Officer for further instructions."

            weekly_xp = user_data['weekly_xp']
            if weekly_xp == "RH":
                quota = f"✅ You're marked as being a new recruit, so you're exempt from the quota for this week!"
            elif weekly_xp == "EX":
                quota = "**Quota Exempt**"
            elif weekly_xp == "IN":
                quota = "**Inactivity Notice**"
            else:
                quota = (
                    f"<:8410joshhutchersonwhistle:1189723626266693702> **{weekly_xp}**/{quota_req} WP"
                    if float(weekly_xp) > 20
                    else f"✅ **{weekly_xp}**/{quota_req} WP"
                    if float(weekly_xp) >= quota_req
                    else f"⬛ **{weekly_xp}**/{quota_req} WP"
                )
        else:
            progress_bar = '⬛' * 10 + '🔒'
            next_rank_name = 'N/A'
            xp_to_next_rank = 'N/A'

            weekly_xp = user_data['weekly_xp']
            if weekly_xp == "RH":
                quota = f"✅ You're marked as being a new recruit, so you're exempt from the quota for this week!"
            elif weekly_xp == "EX":
                quota = "**Quota Exempt**"
            elif weekly_xp == "IN":
                quota = "**Inactivity Notice**"
            else:
                quota = (
                    f"<:8410joshhutchersonwhistle:1189723626266693702> **{weekly_xp}**/{quota_req} WP"
                    if float(weekly_xp) > 20
                    else f"✅ **{weekly_xp}**/{quota_req} WP"
                    if float(weekly_xp) >= quota_req
                    else f"⬛ **{weekly_xp}**/{quota_req} WP"
                )
        # Build the embed
        if isinstance(target_user, discord.Member) or isinstance(target_user, discord.User):
            target_user = target_user.display_name
        else:
            target_user = target_user

        embed = discord.Embed(
            title=f"{target_user}'s XP Progress",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Rank", value=current_rank_full_name, inline=False)
        embed.add_field(name="Next Rank", value=next_rank_name, inline=False)
        embed.add_field(name="Progress", value=progress_bar, inline=False)
        embed.add_field(name="Met Quota?", value=quota, inline=False)
        if promoted:
            embed.add_field(name="<a:alarm_aegis:1236075080749154345> Promotion FAQ <a:alarm_aegis:1236075080749154345>", value="Congratulations on reaching the next rank's XP threshold! In "
                                                        "order for us to **fully** process your promotion, "
                                                        "you'll need to submit a promotion request in "
                                                        "<#1225898217833496697>.\n\nThe instructions for that can be "
                                                        "found here: "
                                                        "https://discord.com/channels/1143709921326682182/1225898217833496697/1226349662752211004",
                            inline=False)

        # Build base filter:
        base_filter = (
                (database.EventLoggingRecords.host_username == target_user) |
                (database.EventLoggingRecords.attendee_username == target_user)
        )
        if roblox_username:
            possible_id = retrieve_discord_user(roblox_username, self.bot, interaction.guild_id, sheet)
            if isinstance(possible_id, int):
                base_filter |= (
                        (database.EventLoggingRecords.attendee_id == possible_id) |
                        (database.EventLoggingRecords.host_id == possible_id)
                )

        # 2) Query distinct rows and get total count
        base_query = (
            database.EventLoggingRecords
            .select()
            .where(base_filter)
            .distinct()
        )
        total_count = base_query.count()

        # 3) Grab the latest three
        recent_events = (
            base_query
            .order_by(database.EventLoggingRecords.datetime_object.desc())
            .limit(3)
        )

        if recent_events.count() > 0:
            event_list = []
            for event in recent_events:
                # parse string→datetime if necessary
                raw = event.datetime_object
                dt = datetime.fromisoformat(raw) if isinstance(raw, str) else raw

                # format to "m/d/Y at h:mm AM/PM EST"
                date_str = dt.strftime("%-m/%-d %-I:%M %p EST")

                event_list.append(
                    f"+ Received {event.xp_awarded} XP from {event.event_type} at {date_str} ({event.host_username})"
                )

            # if there are more than 3 total, tack on the "... X more events" line
            if total_count - 3 > 0:
                event_list.append(f"... {total_count - 3} more events")

            # pull the join out so the f-string is clean
            joined = "\n".join(event_list)
            embed.add_field(
                name="Recent Events",
                value=f"```diff\n{joined}\n```",
                inline=False
            )
        else:
            embed.add_field(
                name="Recent Events",
                value="No recent events found.",
                inline=False
            )
        embed.set_footer(text=f"Total XP: {total_xp} XP | Weekly XP: {user_data['weekly_xp']} WP")
        if next_rank_name != 'N/A':
            if next_rank_name_bool:
                if not promoted:
                    embed.add_field(name="XP for Next Rank", value=f"{xp_to_next_rank} more XP needed for {next_rank_name}",
                                    inline=False)
                else:
                    embed.add_field(name="XP for Next Rank", value=f"Promotion to {next_rank_name} pending!", inline=False)
            else:
                embed.add_field(name="XP for Next Rank", value=f"🔒 Rank Locked", inline=False)
        else:
            embed.add_field(name="Status", value="🔒 Rank Locked", inline=False)

        # Send the embed as the interaction response
        await interaction.followup.send(embed=embed, ephemeral=False)

    @XP.command(
        name="link",
        description="Link your Discord account with your Roblox account."
    )
    @app_commands.describe(
        roblox_username="Enter your Roblox username to link your Discord account with it."
    )
    async def _link(
            self,
            interaction: discord.Interaction,
            roblox_username: str,
    ):
        await interaction.response.defer(ephemeral=True)
        query = database.DiscordToRoblox.select().where(
            database.DiscordToRoblox.discord_id == interaction.user.id
        )
        if query.exists():
            query = query.get()
            query.roblox_username = roblox_username
            query.save()

            confirmation_embed = discord.Embed(
                color=discord.Color.green(),
                title="Link Updated!",
                description=f"Hey {interaction.user.mention}, your Discord account has been successfully updated with the "
                            f"Roblox account `{roblox_username}`."
            )
            await interaction.followup.send(embed=confirmation_embed, ephemeral=True)

        else:
            query = database.DiscordToRoblox.create(
                discord_id=interaction.user.id,
                roblox_username=roblox_username
            )
            query.save()

            confirmation_embed = discord.Embed(
                color=discord.Color.green(),
                title="Link Successful!",
                description=f"Hey {interaction.user.mention}, your Discord account has been successfully linked with the "
                            f"Roblox account `{roblox_username}`."
            )
            await interaction.followup.send(embed=confirmation_embed, ephemeral=True)

    @XP.command(
        name="force_link",
        description="Forcefully link someones Discord account with their Roblox account."
    )
    @app_commands.describe(
        roblox_username="Enter their Roblox username to link their Discord account with it."
    )
    async def _flink(
            self,
            interaction: discord.Interaction,
            roblox_username: str,
            discord_obj: discord.Member,
    ):
        officer_role = discord.utils.get(interaction.guild.roles, id=officer_role_id)
        high_command = discord.utils.get(interaction.guild.roles, id=1143736740075552860)

        if not officer_role in interaction.user.roles and not high_command in interaction.user.roles:
            if interaction.user.id == 409152798609899530:
                pass
            else:
                return await interaction.response.send_message(
                    "You do not have permission to use this command.",
                    ephemeral=True,
                )

        await interaction.response.defer(ephemeral=False)
        query = database.DiscordToRoblox.select().where(
            database.DiscordToRoblox.discord_id == discord_obj.id
        )
        if query.exists():
            query = query.get()
            query.roblox_username = roblox_username
            query.save()

            confirmation_embed = discord.Embed(
                color=discord.Color.green(),
                title="Link Updated!",
                description=f"Edited Link of {discord_obj.mention}'s Discord account with the Roblox account `{roblox_username}`."
            )
            await interaction.followup.send(embed=confirmation_embed, ephemeral=False)

        else:
            query = database.DiscordToRoblox.create(
                discord_id=discord_obj.id,
                roblox_username=roblox_username
            )
            query.save()

            confirmation_embed = discord.Embed(
                color=discord.Color.green(),
                title="Force Link Successful!",
                description=f"Linked {discord_obj.mention}'s Discord account with the Roblox account `{roblox_username}`."
            )
            await interaction.followup.send(embed=confirmation_embed, ephemeral=False)

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

                    log_channel = self.bot.get_channel(xp_log_ch)
                    log_embed = discord.Embed(
                        title="Rank Change",
                        description=f"Successfully {action}d {confirm_name} to {target_rank}.",
                        color=discord.Colour.green(),
                    )
                    log_embed.add_field(name="Reason", value=reason)
                    log_embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | RANK CHANGE")
                    await log_channel.send(embed=log_embed)
                else:
                    await group.kick_user(r_user.id)

                    confirmation_embed = discord.Embed(
                        title="Rank Change",
                        description=f"Successfully kicked {confirm_name} from the group.",
                        color=discord.Colour.green(),
                    )
                    confirmation_embed.add_field(name="Reason", value=reason)
                    await interaction.followup.send(embed=confirmation_embed)

                    log_channel = self.bot.get_channel(xp_log_ch)
                    log_embed = discord.Embed(
                        title="Rank Change",
                        description=f"Successfully kicked {confirm_name} from the group.",
                        color=discord.Colour.green(),
                    )
                    log_embed.add_field(name="Reason", value=reason)
                    log_embed.set_footer(text=f"Authorized by: {interaction.user.display_name} | GROUP REMOVAL")
                    await log_channel.send(embed=log_embed)
            except Exception as e:
                error_embed = discord.Embed(
                    title="Error",
                    description=f"Failed to {action} {confirm_name} to {target_rank}.",
                    color=discord.Colour.red(),
                )
                error_embed.add_field(name="Error", value=str(e))
                await interaction.followup.send(embed=error_embed)

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
        name="request_rank_change",
        description="Need a rank update in the group? Use this command to request a rank change!"
    )
    #@app_commands.guilds(1223473430410690630, 1143709921326682182)
    async def request_rank_change(
            self,
            interaction: discord.Interaction,
            rank_requesting: str,
    ):
        return await interaction.response.send_message("Not in operation...")
        await interaction.response.defer(ephemeral=True, thinking=True)

        rank_obj = RankHierarchy(self.group_id, sheet)
        group = await self.ROBLOX_client.get_group(self.group_id)
        r_user = rank_obj.discord_to_roblox(interaction.user.id, group)
        regular_user = await self.ROBLOX_client.get_user(r_user.id)
        user_rank = await rank_obj.get_rank(regular_user.name)

        user_data = await get_user_xp_data(regular_user.name, sheet)

        """
        Username:
        Current Rank:
        Current XP: 
        Rank requesting: 
        Proof of your XP: (Must contain the full pillar: Username, WP, TP, etc.) 
        """

        username = regular_user.name
        print(username)
        current_rank = user_rank
        current_xp = user_data['total_xp']
        rank_requesting = rank_requesting
        proof_of_xp = f"Column Readout: {username}, {str(user_data['total_xp'])} TP, {str(user_data['weekly_xp'])} WP"

        xp_needed = rank_xp_thresholds.get(rank_requesting, 0) - current_xp
        if xp_needed > 0:
            xp_field = f"❌ | {xp_needed} more XP needed for {rank_requesting}."
        else:
            xp_field = f"✅ | Met the XP requirement for {rank_requesting}."

        embed = discord.Embed(
            title="Rank Change Request",
            description="Please review the information below and confirm that you would like to submit this request.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Username", value=username)
        embed.add_field(name="Current Rank", value=current_rank)
        embed.add_field(name="Current XP", value=current_xp)
        embed.add_field(name="Rank Requested", value=rank_requesting)
        embed.add_field(name="Proof of XP", value=proof_of_xp)
        embed.add_field(name="XP Requirement", value=xp_field)
        embed.set_footer(text="Please confirm that you would like to submit this request.")

        view = ConfirmationView()
        message: discord.WebhookMessage = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        await view.wait()
        if view.value is None:
            return await message.edit(content="Request cancelled.", view=None, embed=embed)

        if view.value is True:
            log_channel = self.bot.get_channel(1225898217833496697)
            log_embed = discord.Embed(
                title="Rank Change Request",
                description=f"Requested by {interaction.user.mention}",
                color=discord.Color.blue()
            )

            log_embed.add_field(name="Username", value=username)
            log_embed.add_field(name="Current Rank", value=current_rank)
            log_embed.add_field(name="Current XP", value=current_xp)
            log_embed.add_field(name="Rank Requested", value=rank_requesting)
            log_embed.add_field(name="Proof of XP", value=proof_of_xp)
            log_embed.set_footer(text=f"Requested by: {interaction.user.display_name} | RANK CHANGE REQUEST")
            await log_channel.send(embed=log_embed, view=PromotionButtons(self.bot))

            await message.edit(content="Request submitted successfully.", view=None, embed=embed)
        else:
            await message.edit(content="Request cancelled.", view=None, embed=embed)

    @request_rank_change.autocomplete('rank_requesting')
    async def request_rank_change_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> typing.List[app_commands.Choice[str]]:
        raw_ranks = [
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

        return [
            app_commands.Choice(name=rank, value=rank)
            for rank in raw_ranks if current.lower() in rank.lower()
        ]

    @XP.command(
        name="request_inactivity_notice",
        description="Submit an inactivity notice if you'll be temporarily unavailable."
    )
    async def request_inactivity(
            self,
            interaction: discord.Interaction
    ):
        # Creating and sending a modal to collect inactivity details
        modal = InactivityModal(self.bot)
        await interaction.response.send_modal(modal)

    @XP.command(
        name="request_discharge",
        description="Submit a discharge request if you'd like to leave."
    )
    async def request_discharge(
            self,
            interaction: discord.Interaction
    ):
        # Creating and sending a modal to collect discharge details
        modal = DischargeModel(self.bot)
        await interaction.response.send_modal(modal)

    @XP.command(
        name="rank_information",
        description="Get information about all ranks."
    )
    async def rank_information(
            self,
            interaction: discord.Interaction,
            current_xp: int = None
    ):
        embed = discord.Embed(
            title="Arasaka Rank Information",
            color=discord.Color.blue()
        )
        for rank, threshold in rank_xp_thresholds.items():
            if current_xp is not None:
                if current_xp >= threshold:
                    progress_detail = "✅"  # Checkmark if XP is above or equal to threshold
                else:
                    remaining_xp = threshold - current_xp
                    progress_percentage = int((current_xp / threshold) * 10)
                    filled_slots = '🟥' * progress_percentage
                    empty_slots = '⬛' * (10 - progress_percentage)
                    progress_bar = filled_slots + empty_slots
                    progress_detail = f"{progress_bar} | {remaining_xp} XP to reach"
                value = f"*XP Requirement:* {threshold} XP\n*Progress:* {progress_detail}"
            else:
                value = f"*XP Requirement:* {threshold} XP"

            embed.add_field(
                name=rank,
                value=value,
                inline=False
            )

        await interaction.response.send_message(embed=embed)

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

        test_sheet = client.open("Arasaka Corp. Database V2").sheet1
        # okay so for all the members in test_sheet column 2, we need to find their discord ID and update it in the same row but in column 8
        members = test_sheet.col_values(1)
        for member in members[1:]:
            username = member
            member = member.strip()
            member = member.replace(" ", "")
            member = discord.utils.get(interaction.guild.members, display_name=member)
            if member:
                discord_id = member.id
                cell = test_sheet.find(member.display_name)
                test_sheet.update_cell(cell.row, 17, f":{discord_id}")
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
