"""
Compute and print out statisics for GPU restocking frequency according to tweets of
@SnailMonitor.
"""

import json
import argparse
import requests
from urllib.parse import quote
from typing import List


CREDENTIALS_PATH = "credentials.json"
TWITTER_USERNAME = "SnailMonitor"
MAX_RESULTS = 100


def get_tweets(product_hashtags: List[str]) -> List[str]:
    """
    Retrieve list of tweets from Twitter API.

    Parameters
    ----------
    product_hashtags : List[str]
        List of hashtags to qualify a tweet. If a hashtag appears in a tweet, the ASIN
        of the product listed in the tweet will be added to the list of products for
        which statistics are computed.

    Returns
    -------
    tweets : List[str]
        List of tweets in string format.
    """

    # Read in API credentials.
    with open(CREDENTIALS_PATH, "r") as credentials_file:
        credentials = json.load(credentials_file)

    # Construct API query.
    hashtag_subquery = "#%s" % product_hashtags[0]
    for i in range(1, len(product_hashtags)):
        hashtag_subquery += " OR #%s" % product_hashtags[i]
    query = "from:%s has:links (%s)" % (TWITTER_USERNAME, hashtag_subquery)

    # Construct request URL and headers.
    kwargs = {"query": quote(query), "max_results": MAX_RESULTS}
    url = "https://api.twitter.com/2/tweets/search/recent"
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


def main(product_hashtags: List[str]) -> None:
    """
    Main function for restock statistics aggregator.

    Parameters
    ----------
    product_hashtags : List[str]
        List of hashtags to qualify a tweet. If a hashtag appears in a tweet, the ASIN
        of the product listed in the tweet will be added to the list of products for
        which statistics are computed.
    """

    # Get tweets from Twitter API.
    tweets = get_tweets(product_hashtags)

    # Parse tweets and aggregate stats.

    # Output statistics to Google Sheets.


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "product_hashtags",
        type=str,
        help="Comma-separated list of hashtags to qualify a tweet.",
    )
    args = parser.parse_args()

    main(args.product_hashtags.split(","))
