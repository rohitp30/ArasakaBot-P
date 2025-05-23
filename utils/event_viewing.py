import os
import typing
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from roblox import Client
from sentry_sdk import start_transaction

from core import database
from core.common import (
    get_user_xp_data, RankHierarchy, ConfirmationView,
    PromotionButtons, InactivityModal, DischargeModel, retrieve_discord_user,
    ArasakaRanks, SheetsClient
)
from core.logging_module import get_log
from utils.event_logging import XP

_log = get_log(__name__)
sheet = SheetsClient().sheet



class EventViewing(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.ROBLOX_client = Client(os.getenv("ROBLOX_SECURITY"))
        self.group_id = 33764698
        self.interaction = []


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
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
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
                next_rank_name = ArasakaRanks.next_rank.get(current_rank_full_name)

            quota_req = ArasakaRanks.quota_dict.get(current_rank_full_name)

            # Create the progress bar
            if next_rank_name != '🔒' and next_rank_name != '🔒*':
                xp_to_next_rank = ArasakaRanks.rank_xp_thresholds.get(next_rank_name, 0) - total_xp
                progress_percentage = (total_xp - ArasakaRanks.rank_xp_thresholds[current_rank_full_name]) / (
                        ArasakaRanks.rank_xp_thresholds[next_rank_name] - ArasakaRanks.rank_xp_thresholds[current_rank_full_name])

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
                embed.add_field(
                    name="<a:alarm_aegis:1236075080749154345> Promotion FAQ <a:alarm_aegis:1236075080749154345>",
                    value="Congratulations on reaching the next rank's XP threshold! In "
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
                        embed.add_field(name="XP for Next Rank",
                                        value=f"{xp_to_next_rank} more XP needed for {next_rank_name}",
                                        inline=False)
                    else:
                        embed.add_field(name="XP for Next Rank", value=f"Promotion to {next_rank_name} pending!",
                                        inline=False)
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
        name="request_rank_change",
        description="Need a rank update in the group? Use this command to request a rank change!"
    )
    # @app_commands.guilds(1223473430410690630, 1143709921326682182)
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
        for rank, threshold in ArasakaRanks.rank_xp_thresholds.items():
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


async def setup(bot: commands.Bot):
    await bot.add_cog(EventViewing(bot))
