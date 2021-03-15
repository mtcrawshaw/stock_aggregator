"""
Compute and print out statisics for GPU restocking frequency according to tweets of
@SnailMonitor.
"""

import argparse
import json
import requests
from urllib.parse import quote
from typing import List, Dict


CREDENTIALS_PATH = "credentials.json"

TWITTER_USERNAME = "SnailMonitor"
TWITTER_URL_PREFIX = "https://api.twitter.com/2/tweets/search/recent"
PRODUCT_HASHTAGS = ["RTX3070", "RTX3080"]
MAX_RESULTS = 100

SHORTENED_URL_PREFIX = "https://t.co"
ASID_LENGTH = 10


def get_tweets() -> List[str]:
    """
    Retrieve list of tweets from Twitter API.

    Returns
    -------
    tweets : List[str]
        List of tweets in string format.
    """

    # Read in API credentials.
    with open(CREDENTIALS_PATH, "r") as credentials_file:
        credentials = json.load(credentials_file)

    # Construct API query.
    hashtag_subquery = "#%s" % PRODUCT_HASHTAGS[0]
    for i in range(1, len(PRODUCT_HASHTAGS)):
        hashtag_subquery += " OR #%s" % PRODUCT_HASHTAGS[i]
    query = "from:%s has:links (%s)" % (TWITTER_USERNAME, hashtag_subquery)

    # Construct request URL and headers.
    kwargs = {"query": quote(query), "max_results": MAX_RESULTS}
    url = TWITTER_URL_PREFIX
    for i, (key, value) in enumerate(kwargs.items()):
        url += "?" if i == 0 else "&"
        url += "%s=%s" % (key, value)
    headers = {"Authorization": "Bearer {}".format(credentials["bearer_token"])}

    # Make API request.
    response = requests.request("GET", url, headers=headers)
    if response.status_code != 200:
        raise Exception(response.status_code, response.text)
    response = response.json()

    # Parse request response into a list of tweets in string format.
    tweets = [tweet["text"] for tweet in response["data"]]

    return tweets


def count_restocks(tweets: List[str]) -> Dict[str, int]:
    """
    Count number of restocks for each product based on tweet notifications.

    Parameters
    ----------
    tweets : List[str]
        List of tweets notifying product restocks.

    Returns
    -------
    restock_stats : Dict[str, int]
        Dictionary mapping Amazon ASIN to number of restocks as described by tweets.
    """

    # Create requests session to full URLs with.
    session = requests.Session()

    restock_stats = {}
    is_link = lambda x: x.startswith(SHORTENED_URL_PREFIX)
    for tweet in tweets:

        # Get Amazon link from tweet, if one exists. There should not be more than one.
        words = tweet.split()
        links = [word for word in words if is_link(word)]
        if len(links) > 1:
            raise ValueError(
                "The following tweet contains more than one link: %s" % tweet
            )
        if len(links) == 0:
            continue

        # Get full URL.
        link = links[0]
        response = session.head(link, allow_redirects=True)
        full_url = response.url

        # Get ASID from full URL.
        asid_end = full_url.find("?")
        asid_start = asid_end - 10
        asid = full_url[asid_start:asid_end]

        # Add count to running stats.
        if asid not in restock_stats:
            restock_stats[asid] = 0
        restock_stats[asid] += 1

    return restock_stats


def main() -> None:
    """
    Main function for restock statistics aggregator.
    """

    # Get tweets from Twitter API.
    tweets = get_tweets()

    # Parse tweets and aggregate stats.
    restock_stats = count_restocks(tweets)

    # Output statistics to Google Sheets.
    # START HERE


if __name__ == "__main__":
    main()
