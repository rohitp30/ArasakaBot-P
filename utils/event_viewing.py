from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from sentry_sdk import start_transaction

from core import database
from core.common import (
    ArasakaRanks, SheetsClient
)
from core.logging_module import get_log

_log = get_log(__name__)
sheet = SheetsClient().sheet

class EventViewing(commands.Cog):
    def __init__(self, bot: "ArasakaCorpBot"):
        self.bot: "ArasakaCorpBot" = bot
        self.group_id = 33764698
        self.interaction = []

    XP = app_commands.Group(
        name="xp_view",
        description="View XP and rank information.",
        guild_ids=[1223473430410690630, 1143709921326682182],
    )

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

            # Create a RobloxDiscordLinker instance
            from core.common import RobloxDiscordLinker
            linker = RobloxDiscordLinker(self.bot, interaction.guild_id, sheet)

            # Determine the target user
            if roblox_username:
                target_name = roblox_username
            elif target_user:
                # Try to get the Roblox username for the Discord user
                roblox_name = await linker.discord_id_to_roblox_username(target_user.id)
                target_name = roblox_name if roblox_name else target_user.display_name
            else:
                # Try to get the Roblox username for the interaction user
                roblox_name = await linker.discord_id_to_roblox_username(interaction.user.id)
                target_name = roblox_name if roblox_name else interaction.user.display_name

            promoted = False

            # Get user data using the linker
            user_data = await linker.get_user_xp_data(target_name)

            # If not found and target is a Discord member, try with their display name
            if not user_data and isinstance(target_user, (discord.Member, discord.User)):
                user_data = await linker.get_user_xp_data(target_user.display_name)

            # If still not found, try with the interaction user's display name
            if not user_data and not target_user and not roblox_username:
                user_data = await linker.get_user_xp_data(interaction.user.display_name)

            # If still not found, return an error message
            if not user_data:
                confirmation_embed = discord.Embed(
                    color=discord.Color.brand_red(),
                    title="User Not Found",
                    description=f"Hey {interaction.user.mention}, I couldn't find data for the user you specified."
                )
                confirmation_embed.add_field(
                    name="Resolutions",
                    value="1. Make sure the username is correct.\n"
                          "2. If you're looking for yourself, try using the `roblox_username` field with your Roblox username.\n"
                          "3. If you're looking for someone else, try mentioning them or using their Roblox username."
                )
                return await interaction.followup.send(embed=confirmation_embed, ephemeral=True)

            # For display purposes, determine the name to show
            if isinstance(target_user, (discord.Member, discord.User)):
                display_name = target_user.display_name
            elif roblox_username:
                display_name = roblox_username
            else:
                display_name = interaction.user.display_name

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
            embed = discord.Embed(
                title=f"{display_name}'s XP Progress",
                color=discord.Color.blue()
            )
            embed.add_field(name="Current Rank", value=current_rank_full_name, inline=False)
            embed.add_field(name="Next Rank", value=next_rank_name, inline=True)
            if user_data["division"] != "N/A":
                embed.add_field(name="Division", value=f"**{user_data['division']}**", inline=True)
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

            # Build base filter using both display_name and target_name
            base_filter = (
                    (database.EventLoggingRecords.host_username == display_name) |
                    (database.EventLoggingRecords.attendee_username == display_name)
            )

            # If target_name is different from display_name, include it in the filter
            if target_name != display_name:
                base_filter |= (
                    (database.EventLoggingRecords.host_username == target_name) |
                    (database.EventLoggingRecords.attendee_username == target_name)
                )

            # Include Discord ID in the filter if available
            discord_id = None
            if isinstance(target_user, (discord.Member, discord.User)):
                discord_id = target_user.id
            elif not target_user and not roblox_username:
                discord_id = interaction.user.id

            if discord_id:
                base_filter |= (
                    (database.EventLoggingRecords.attendee_id == discord_id) |
                    (database.EventLoggingRecords.host_id == discord_id)
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
        description="Information about linking your Discord account with your Roblox account."
    )
    @app_commands.describe(
        roblox_username="This parameter is no longer used. Please read the information provided."
    )
    async def _link(
            self,
            interaction: discord.Interaction,
            roblox_username: str = None,
    ):
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            await interaction.response.defer(ephemeral=True)

            # Create an informative embed about Blox.link
            info_embed = discord.Embed(
                color=discord.Color.blue(),
                title="Discord ↔ Roblox Account Linking",
                description=f"Hey {interaction.user.mention}, we now use Blox.link for Discord to Roblox account linking."
            )

            info_embed.add_field(
                name="How to Link Your Accounts",
                value="1. Join the Blox.link Discord server: https://discord.gg/bloxlink\n"
                      "2. Follow their instructions to link your Discord and Roblox accounts\n"
                      "3. Once linked, your Roblox account will be automatically recognized by our bot",
                inline=False
            )

            info_embed.add_field(
                name="Benefits of Using Blox.link",
                value="- More secure and reliable linking\n"
                      "- Works across multiple Discord servers\n"
                      "- Automatic verification of Roblox account ownership",
                inline=False
            )

            info_embed.add_field(
                name="Need Help?",
                value="If you're having trouble with Blox.link, please contact a server administrator for assistance.",
                inline=False
            )

            await interaction.followup.send(embed=info_embed, ephemeral=True)

    @XP.command(
        name="rank_information",
        description="Get information about all ranks."
    )
    async def rank_information(
            self,
            interaction: discord.Interaction,
            current_xp: int = None
    ):
        with start_transaction(op="command", name=f"cmd/{interaction.command.name}"):
            embed = discord.Embed(
                title="Arasaka Rank Information",
                color=discord.Color.blue()
            )
            for rank, threshold in ArasakaRanks.rank_xp_thresholds.items():
                if current_xp is not None:
                    if current_xp >= threshold:
                        progress_detail = "✅"  # Checkmark if XP is above or equal to a threshold
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
