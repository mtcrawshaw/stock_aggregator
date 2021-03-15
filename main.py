"""
Compute and print out statisics for GPU restocking frequency according to tweets of
@SnailMonitor.
"""

import os
import argparse
import json
import requests
import csv
from urllib.parse import quote
from typing import List, Dict

import gspread


TWITTER_CREDENTIALS_PATH = "twitter_credentials.json"

TWITTER_USERNAME = "SnailMonitor"
TWITTER_URL_PREFIX = "https://api.twitter.com/2/tweets/search/recent"
PRODUCT_TYPES = ["RTX3070", "RTX3080"]
MAX_RESULTS = 100

SHORTENED_URL_PREFIX = "https://t.co"
ASID_LENGTH = 10

DRIVE_CREDENTIALS_PATH = "drive_credentials.json"
TEMP_CSV_PATH = ".temp_stats.csv"


class Product:
    """ Struct to store product staistics. """

    def __init__(self, asin: str, product_type: str, num_restocks: int = 0) -> None:
        """ Init function for Product. """
        self.asin = asin
        self.product_type = product_type
        self.num_restocks = num_restocks

    def __repr__(self) -> str:
        """ String representation of `self`. """
        return "ASID: %s, Type: %s, Num Restocks: %d" % (
            self.asin,
            self.product_type,
            self.num_restocks,
        )


def get_tweets() -> List[str]:
    """
    Retrieve list of tweets from Twitter API.

    Returns
    -------
    tweets : List[str]
        List of tweets in string format.
    """

    # Read in API credentials.
    with open(TWITTER_CREDENTIALS_PATH, "r") as credentials_file:
        credentials = json.load(credentials_file)

    # Construct API query.
    hashtag_subquery = "#%s" % PRODUCT_TYPES[0]
    for i in range(1, len(PRODUCT_TYPES)):
        hashtag_subquery += " OR #%s" % PRODUCT_TYPES[i]
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


def count_restocks(tweets: List[str]) -> List[Product]:
    """
    Count number of restocks for each product based on tweet notifications.

    Parameters
    ----------
    tweets : List[str]
        List of tweets notifying product restocks.

    Returns
    -------
    restock_stats : List[Product]
        List of product restock stats as described by tweets.
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
        link = links[0]

        # Get product type from hashtags. There should only be one hashtag in the tweet
        # matching a hashtag describing product type.
        tweet_hashtags = [
            hashtag for hashtag in PRODUCT_TYPES if ("#%s" % hashtag) in words
        ]
        if len(tweet_hashtags) > 1:
            raise ValueError(
                "The following tweet contains more than one product hashtag: %s" % tweet
            )
        if len(tweet_hashtags) == 0:
            continue
        product_type = tweet_hashtags[0]

        # Get full URL.
        response = session.head(link, allow_redirects=True)
        full_url = response.url

        # Get ASID from full URL.
        asin_end = full_url.find("?")
        asin_start = asin_end - 10
        asin = full_url[asin_start:asin_end]

        # Add count to running stats.
        if asin not in restock_stats:
            restock_stats[asin] = Product(asin, product_type, num_restocks=0)
        restock_stats[asin].num_restocks += 1

    return list(restock_stats.values())


def dump_stats(restock_stats: List[Product]) -> None:
    """
    Dump product restock statistics to Google Sheets.

    Parameters
    ----------
    restock_stats : List[Product]
        List of product restock stats.
    """

    # Partition products by type.
    partitioned_products = {
        product_type: [
            product for product in restock_stats if product.product_type == product_type
        ]
        for product_type in PRODUCT_TYPES
    }

    # Sort products within each hashtag by number of restocks.
    product_key = lambda p: p.num_restocks
    for product_type in PRODUCT_TYPES:
        partitioned_products[product_type] = sorted(
            partitioned_products[product_type], key=product_key, reverse=True
        )

    # Dump stats.
    try:

        # Write out stats to temporary CSV file.
        with open(TEMP_CSV_PATH, "w") as temp_csv_file:
            csv_writer = csv.writer(temp_csv_file)

            # Write out column names.
            num_cols = 2
            csv_writer.writerow(["Product Type", "ASIN", "Restocks"])
            csv_writer.writerow([""])

            # Write out stats for each product.
            for product_type in PRODUCT_TYPES:
                for product in partitioned_products[product_type]:
                    csv_writer.writerow(
                        [product_type, product.asin, str(product.num_restocks)]
                    )
                csv_writer.writerow([""])

        # Dump file to Google Sheets.
        gc = gspread.service_account(filename=DRIVE_CREDENTIALS_PATH)
        content = open(TEMP_CSV_PATH, "r").read()
        drive_credentials = json.load(open(DRIVE_CREDENTIALS_PATH, "r"))
        gc.import_csv(drive_credentials["spreadsheet_id"], content)

        # Clean up temporary CSV file.
        os.remove(TEMP_CSV_PATH)

    except:

        # Clean up our dumped CSV file if it's still there, then re-raise error.
        if os.path.isfile(TEMP_CSV_PATH):
            os.remove(TEMP_CSV_PATH)
        raise


def main() -> None:
    """
    Main function for restock statistics aggregator.
    """

    # Get tweets from Twitter API.
    tweets = get_tweets()

    # Parse tweets and aggregate stats.
    restock_stats = count_restocks(tweets)

    # Output statistics to Google Sheets.
    dump_stats(restock_stats)


if __name__ == "__main__":
    main()
