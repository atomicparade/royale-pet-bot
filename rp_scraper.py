import urllib
import re
import sys

from bs4 import BeautifulSoup

class PlayerData:
    def __init__(self, name, avatar_url = None):
        self.name = name
        self.avatar_url = avatar_url
        self.stats = {}

class Statistic:
    def __init__(self, value, rank = None):
        self.value = value
        self.rank = rank

    def __str__(self):
        if self.rank is None:
            try:
                return f"{self.value:,}"
            except ValueError:
                return f"{self.value}"
        else:
            try:
                return f"{self.value:,} (#{self.rank})"
            except ValueError:
                return f"{self.value} (#{self.rank})"

class FetchError(Exception):
    pass

def fetch_page(player_name_or_id):
    """
    Retrieves the contents of the Royale.pet page for the specified player.

    Returns the HTML response, or None if there was an error retrieving the
    data. Note that a nonexistent player name or ID results in a 200 OK
    response.

    Raises FetchError if the HTTP request fails or the page returns a status
    other than 200 OK.
    """
    url = "https://royale.pet/lookup"
    data = urllib.parse.urlencode({"input": player_name_or_id}).encode("ascii")

    try:
        response = urllib.request.urlopen(url, data)
    except urllib.error.URLError as e:
        raise FetchError(repr(e))

    if response.status != 200:
        raise FetchError(f"Status {response.status}")

    return response.read(), response.geturl()

def parse_html_into_stats(html):
    """
    Attempts to extract player data from Royale.pet HTML.

    Returns a dictionary containing the player data, or None if the HTML does
    not appear to contain player data.
    """
    if html is None:
        return None

    soup = BeautifulSoup(html, features="html5lib")

    player_data = {}

    player_name = None
    avatar_url = None
    for profile in soup.find_all("div", class_="profile"):

        for el in profile.find_all("div", class_="name"):
            player_name = el.string

        for el in profile.find_all("a", class_="avatar"):
            try:
                avatar_url = el["style"]

                match = re.match(r"^background-image:url\((.+)\);$", avatar_url)
                if match:
                    avatar_url = match[1]
            except KeyError:
                pass

    if player_name is None:
        return None

    player_data = PlayerData(player_name, avatar_url)

    for stats_group in soup.find_all("div", class_="stats-group"):
        title = None

        for stats_group_title in stats_group.find_all("div", class_="stats-group-title"):
            title = stats_group_title.string
            break

        if title is None:
            continue

        stats_section = {}

        for stat_pair in stats_group.find_all("li", class_="stat-pair"):
            key = None
            value = None
            rank = None

            for el in stat_pair.find_all("a", class_="field"):
                key = el.string
                break

            for el in stat_pair.find_all("span", class_="value"):
                value = el.string

                try:
                    value = int(value.replace(",", ""))
                except ValueError:
                    pass

                break

            for el in stat_pair.find_all("div", "ranking"):
                rank = el.string

                try:
                    rank = int(rank.replace(",", ""))
                except ValueError:
                    pass

                break

            if key is not None and value is not None:
                stats_section[key] = Statistic(value, rank)

        player_data.stats[title] = stats_section

    return player_data

def fetch_player_data(player_name_or_id):
    """
    Returns player data from Royale.pet for the specified player, along with the
    page URL.

    Returns None, url if the Royale.pet page does not appear to contain player
    data.

    Raises FetchError if the HTTP request fails or the page returns a status
    other than 200 OK.
    """
    page_data, url = fetch_page(player_name_or_id)

    if page_data is None:
        return None, url

    return parse_html_into_stats(page_data), url
