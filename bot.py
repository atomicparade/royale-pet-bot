#!/usr/bin/python

import asyncio
import logging
import os
import re
import sys

import discord
from discord import DMChannel, Embed, Member
from dotenv import load_dotenv

from rp_scraper import FetchError, fetch_player_data
from adminlist import AdminList

logger = logging.getLogger("rpb")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s"))
logger.addHandler(handler)

def extract_command(bot_id, message):
    """
    Attempts to extract a command and any arguments from message_content.

    A message is determined to be a command if it begins with a mention of
    bot_id or was sent in a DM. If it's not a command, this function returns
    None, None.

    If the message is a command without any arguments, this function returns
    "command", None.

    If the message is a command with one or more arguments, this function
    returns "command", args where args is a list of the unmodified argument
    string, followed by the arguments (split on whitespace).
    """
    match = re.match(fr"^<@!?{bot_id}>(.+)$", message.content)

    if match is not None:
        command_str = match[1]
    else:
        if isinstance(message.channel, DMChannel):
            command_str = message.content
        else:
            return None, None

    # Check whether this is a command followed by arguments
    args_match = re.match(r"(.+?)\s+(.+)", command_str)

    if args_match is None:
        # No arguments
        command = command_str
        args = None
    else:
        command = args_match[1]
        args = [args_match[2]]
        args.extend(args_match[2].split())

    command = command.strip().lower()
    return command, args

def get_user_str(user):
    return f"{user.name}#{user.discriminator} (ID: {user.id})"

def get_user_name(user):
    if isinstance(user, Member):
        return user.nick or user.name
    else:
        return user.name

class Bot(discord.Client):
    def __init__(self):
        super(Bot, self).__init__()
        self.admin = AdminList()

    async def on_ready(self):
        logger.info(f"Connected as {get_user_str(self.user)})")

    async def on_message(self, message):
        user = message.author
        user_str = get_user_str(user)
        user_name = get_user_name(user)
        greeting = f"**{user_name}:**"

        command, args = extract_command(self.user.id, message)

        if command is None:
            return

        if command == "auth":
            if args is None:
                # No password supplied
                return

            if not isinstance(message.channel, DMChannel):
                await self.respond(message, f"{greeting} You may only use this command in a DM.")
                return

            if self.admin.is_authorized(user):
                await self.respond(message, "You have already authenticated.")
                return

            if self.admin.authenticate(user, args[0]):
                logger.info(f"Successful admin authentication by {user_str}")
                await self.notify_admins(f"Successful admin authentication by {user_str}.", user)
            else:
                logger.info(f"Failed admin authentication attempt by {user_str}")
                self.notify_admins(f"Failed admin authentication attempt by {user_str}.", user)
        elif command == "quit":
            if not self.admin.is_authorized(user):
                return

            logger.info(f"Quitting per {user_str}")
            await self.notify_admins(f"Quitting per {user_str}.", user)
            await self.close()
        elif command == "help":
            await self.respond(message, f"To get stats for a player, use <@{self.user.id}> stats [Player's Steam Community URL]")
        elif command == "stats":
            if args is None:
                await self.respond(message, f"{greeting} Please specify a Steam Community name or Steam User ID.")
                return

            try:
                player_data, player_url = fetch_player_data(args[1])
            except FetchError:
                logger.warn(f"Failed to retrieve stats for \"{args[1]}\": {repr(e)}")
                # TODO: Consider setting a threshold for bailing (5 consecutive failures in 10 minutes)
                await self.respond(message, f"{greeting} Sorry, I couldn't get the stats. The admins have been notified.")
                await notify_admins(f"Failed to retrieve stats for \"{args[1]}\": {repr(e)}")
                return

            if player_data is None:
                await self.respond(message, f"{greeting} Unable to find a player with the name or ID \"{args[1]}\".")
                return

            response = Embed(title=player_data.name, url=player_url)

            if player_data.avatar_url is not None:
                response.set_thumbnail(url=player_data.avatar_url)

            # For inline formatting
            num_mode_sections = len([mode for mode in ["Solo", "Duos", "Squads"] if mode in player_data.stats])

            for stats_group in ["Solo", "Duos", "Squads", "Combat", "Miscellaneous"]:
                if stats_group in player_data.stats:
                    stats_content = ""

                    for key in player_data.stats[stats_group]:
                        if len(stats_content) > 0:
                            stats_content += "\n"
                        stats_content += f"**{key}:** {player_data.stats[stats_group][key]}"

                        if key == "Wins":
                            try:
                                win_percent = player_data.stats[stats_group]["Wins"].value / player_data.stats[stats_group]["Games Played"].value
                                stats_content += f" ({win_percent:0.1%})"
                            except:
                                pass

                        if key == "Kills":
                            try:
                                kdr = player_data.stats[stats_group]["Kills"].value / player_data.stats[stats_group]["Deaths"].value
                                stats_content += f" (K/D: {kdr:0.1f})"
                            except:
                                pass

                        if key in ["Top 5", "Top 3", "Top 2"]:
                            try:
                                top_percent = player_data.stats[stats_group][key].value / player_data.stats[stats_group]["Games Played"].value
                                stats_content += f" ({top_percent:0.1%})"
                            except:
                                pass

                    # Adjust inlining based on the number of mode sections
                    # because the Combat and Miscellaneous sections are longer
                    #
                    # If there are exactly any two of (Solo, Duos, Squads), then
                    # there is no need to adjust
                    #
                    # If there's exactly one, it needs to NOT be inline
                    #
                    # If all three are present, only Squads should NOT be inline
                    if num_mode_sections == 1 and stats_group in ["Solo", "Duos", "Squads"]:
                        make_inline = False
                    elif num_mode_sections == 3 and stats_group == "Squads":
                        make_inline = False
                    else:
                        make_inline = True

                    response.add_field(name=stats_group, value=stats_content, inline=make_inline)

            response.set_footer(
                text=f"{get_user_name(message.author)} - Stats obtained from Royale.pet",
                icon_url=user.avatar_url)

            await self.respond(message, response)

    def notify_admins(self, content, about_user=None):
        if not isinstance(content, Embed) and about_user is not None:
            content = Embed(description=content)
            content.set_thumbnail(url=about_user.avatar_url)

        if isinstance(content, Embed):
            return asyncio.gather(*[user.send(embed=content) for user in self.admin.list])
        else:
            return asyncio.gather(*[user.send(content) for user in self.admin.list])

    def respond(self, message, response, put_author_in_footer=False):
        if put_author_in_footer:
            if not isinstance(response, Embed):
                response = Embed(description=response)

            response.set_footer(
                text=get_user_name(message.author),
                icon_url=message.author.avatar_url)

        if isinstance(response, Embed):
            return message.channel.send(embed=response)
        else:
            return message.channel.send(response)

if __name__ == "__main__":
    load_dotenv()
    bot = Bot()

    try:
        bot.run(os.getenv("DISCORD_BOT_TOKEN"))
    except Exception as e:
        logger.error(f"Failed to connect: {repr(e)}")
        raise e
