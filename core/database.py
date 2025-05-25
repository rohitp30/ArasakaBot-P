import os
import time
from datetime import datetime

import pytz
from dotenv import load_dotenv
from peewee import (
    AutoField,
    BigIntegerField,
    BooleanField,
    DateTimeField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
    FloatField
)

from core.logging_module import get_log

load_dotenv()
_log = get_log(__name__)
"""
Change to a SqliteDatabase if you don't have any MySQL Credentials.
If you do switch, comment/remove the MySQLDatabase variable and uncomment/remove the # from the SqliteDatabase instance. 
"""

if os.getenv("DATABASE_IP") is None:
    db = SqliteDatabase("data.db")
    _log.info("No Database IP found in .env file, using SQLite!")

elif os.getenv("DATABASE_IP") is not None:
    # useDB = bool(input(f"{bcolors.WARNING}Do you want to use MySQL? (y/n)\n    > This option should be avoided if you are testing new database structures, do not use MySQL Production if you are testing table modifications.{bcolors.ENDC}"))
    db = SqliteDatabase("data.db")
    if not os.getenv("PyTestMODE"):
        _log.info(f"Successfully connected to the SQLite Database")
    else:
        _log.info(f"Testing environment detected, using SQLite Database")


def iter_table(model_dict: dict):
    """Iterates through a dictionary of tables, confirming they exist and creating them if necessary."""
    for key in model_dict:
        if not db.table_exists(key):
            db.connect(reuse_if_open=True)
            db.create_tables([model_dict[key]])
            db.close()
        else:
            db.connect(reuse_if_open=True)
            for column in model_dict[key]._meta.sorted_fields:
                if not db.column_exists(key, column.name):
                    db.create_column(key, column.name)
            db.close()


"""
DATABASE FILES

This file represents every database table and the model they follow. When fetching information from the tables, consult the typehints for possible methods!

"""


class BaseModel(Model):
    """Base Model class used for creating new tables."""

    class Meta:
        database = db


class Administrators(BaseModel):
    """
    Administrators:
    List of users who are whitelisted on the bot.

    `id`: AutoField()
    Database Entry

    `discordID`: BigIntegerField()
    Discord ID

    `TierLevel`: IntegerField()
    TIER LEVEL

    1 - Bot Manager\n
    2 - Admin\n
    3 - Sudo Admin\n
    4 - Owner
    """

    id = AutoField()
    discordID = BigIntegerField(unique=True)
    TierLevel = IntegerField(default=1)


class AdminLogging(BaseModel):
    """
    # AdminLogging:
    List of users who are whitelisted on the bot.

    `id`: AutoField()
    Database Entry

    `discordID`: BigIntegerField()
    Discord ID

    `action`: TextField()
    Command Name

    `content`: TextField()
    `*args` passed in

    `datetime`: DateTimeField()
    DateTime Object when the command was executed.
    """

    id = AutoField()
    discordID = BigIntegerField()
    action = TextField()
    content = TextField(default="N/A")
    datetime = DateTimeField(default=datetime.now())


class Blacklist(BaseModel):
    """
    # Blacklist:
    List of users who are blacklisted on the bot.

    `id`: AutoField()
    Database Entry

    `discordID`: BigIntegerField()
    Discord ID
    """

    id = AutoField()
    discordID = BigIntegerField(unique=True)


class CommandAnalytics(BaseModel):
    """
    #CommandAnalytics
    `id`: AutoField()
    Database Entry ID
    `command`: TextField()
    The command that was used.
    `user`: IntegerField()
    The user that used the command.
    `date`: DateTimeField()
    The date when the command was used.
    `command_type`: TextField()
    The type of command that was used.
    `guild_id`: BigIntegerField()
    The guild ID of the guild that the command was used in.
    """

    id = AutoField()
    command = TextField()
    date = DateTimeField()
    command_type = TextField()
    guild_id = BigIntegerField()
    user = BigIntegerField()


class CheckInformation(BaseModel):
    """
    # CheckInformation:
    List of users who are whitelisted on the bot.
    `id`: AutoField()
    Database Entry
    `MasterMaintenance`: BooleanField()
    Ultimate Check; If this is enabled no one except Permit 4+ users are allowed to use the bot.\n
    '>>> **NOTE:** This attribute must always have a bypass to prevent lockouts, otherwise this check will ALWAYS return False.
    `guildNone`: BooleanField()
    If commands executed outside of guilds (DMs) are allowed.
    `externalGuild`: BooleanField()
    If commands executed outside of the main guild (Staff Servers, etc) are allowed.
    `ModRoleBypass`: BooleanField()
    If commands executed inside of a public/general channel by a mod+ is allowed.
    `ruleBypass`: BooleanField()
    If the command *rule* is executed in public/general channels is allowed.
    `publicCategories`: BooleanField()
    If any command (except rule) inside of a public/general channel is allowed.
    `elseSituation`: BooleanField()
    Other situations will be defaulted to/as ...
    `PersistantChange`: BooleanField()
    If the discord bot has added its persistant buttons/views.
    """

    id = AutoField()

    MasterMaintenance = BooleanField()
    guildNone = BooleanField()
    externalGuild = BooleanField()
    publicCategories = BooleanField()
    elseSituation = BooleanField()
    PersistantChange = BooleanField()


# DiscordToRoblox table has been removed as it's no longer used
# Discord to Roblox linking is now handled by Blox.link API


class EventLoggingRecords(BaseModel):
    """
    # EventLoggingRecords
    A table to store event logging records. (For /xp view)

    `id`: AutoField()
    Database Entry ID

    `host_id`: BigIntegerField()
    The user ID of the host.

    `attendee`: TextField()
    Specific attendee.

    `event_type`: TextField()
    The type of event hosted.

    `xp_awarded`: FloatField()
    The amount of XP awarded.

    `datetime`: DateTimeField()
    The date and time the event was hosted.
    """
    id = AutoField()
    host_username = TextField()
    host_id = BigIntegerField()
    attendee_username = TextField()
    attendee_id = BigIntegerField(default=0)
    event_type = TextField()
    xp_awarded = FloatField()
    datetime_object = DateTimeField(default=datetime.now(tz=pytz.timezone("America/New_York")), null=False)


class EventQuota(BaseModel):
    """
    # EventQuota
    A table to store event quotas. (For /xp view)

    `id`: AutoField()
    Database Entry ID

    `host_id`: BigIntegerField()
    The user ID of the host.

    `event_type`: TextField()
    The type of event hosted.

    `datetime_object`: DateTimeField()
    The date and time the event was hosted.
    """

    id = AutoField()
    host_id = BigIntegerField()
    event_type = TextField()
    datetime_object = DateTimeField(default=datetime.now(tz=pytz.timezone("America/New_York")), null=False)


class MaintenanceMode(BaseModel):
    """
    # Maintenance
    A table to store maintenance records.

    `id`: AutoField()
    Database Entry ID

    `enabled`: BooleanField()
    Indicates if the maintenance mode is enabled or not.

    `start_time`: DateTimeField()
    The start time of the maintenance.

    `reason`: TextField()
    The reason for the maintenance.
    """

    id = AutoField()
    enabled = BooleanField(default=False)
    start_time = DateTimeField(default=datetime.now(tz=pytz.timezone("America/New_York")), null=False)
    reason = TextField(null=True)


tables = {
    "Administrators": Administrators,
    "AdminLogging": AdminLogging,
    "Blacklist": Blacklist,
    "CommandAnalytics": CommandAnalytics,
    "CheckInformation": CheckInformation,
    "EventLoggingRecords": EventLoggingRecords,
    "EventQuota": EventQuota,
    "MaintenanceMode": MaintenanceMode,
}

"""
This function automatically adds tables to the database if they do not exist,
however it does take a significant amount of time to run so the env variable 'PyTestMODE' should be 'False'
in development. 
"""

iter_table(tables)
