"""
Compute and output statisics for GPU drop frequency according to tweets of
@SnailMonitor.
"""

import os
import argparse
import pickle
import json
import requests
import csv
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import List, Dict, Any

import numpy as np
import gspread


DROP_DATABASE_PATH = "drop_database.pkl"

TWITTER_CREDENTIALS_PATH = "twitter_credentials.json"
TWITTER_USERNAME = "SnailMonitor"
TWITTER_USER_URL = "https://api.twitter.com/2/users/by"
TWITTER_TIMELINE_URL = "https://api.twitter.com/2/users/%s/tweets"
TWITTER_TIME_FORMAT_1 = "%Y-%m-%dT%H:%M:%S.000Z"
TWITTER_TIME_FORMAT_2 = "%Y-%m-%dT%H:%M:%SZ"
PRODUCT_TYPES = ["RTX3070", "RTX3080"]
MAX_RESULTS = 100
SINGLE_PAGE = False

SHORTENED_URL_PREFIX = "https://t.co"
AMAZON_URL_KEYWORD = "amazon.com"
DROP_MESSAGE_1 = " in stock at"
DROP_MESSAGE_2 = " now available on"
BAD_TWEET_THRESHOLD = 0.05
BAD_DROP_THRESHOLD = 0.05
ASIN_LEN = 10
ASIN_PREFIX = "B0"

DRIVE_CREDENTIALS_PATH = "drive_credentials.json"
TEMP_CSV_PATH = ".temp_stats.csv"


class Drop:
    """ Struct to represent a single product drop. """

    def __init__(
        self, asin: str, name: str, product_type: str, drop_time: datetime
    ) -> None:
        """ Init function for Drop. """
        self.asin = asin
        self.name = name
        self.product_type = product_type
        self.time = drop_time

        self.state_vars = ["asin", "name", "product_type", "time"]

    def __repr__(self) -> str:
        """ String representation of `self`. """
        return str(self.state_dict())

    def __eq__(self, other) -> bool:
        """ Comparator for Drop. """
        self_dict = self.state_dict()
        other_dict = other.state_dict()
        return all(
            self_dict[state_var] == other_dict[state_var]
            for state_var in self.state_vars
        )

    def state_dict(self) -> Dict[str, Any]:
        """ Dictionary containing state attribute values. """
        return {state_var: getattr(self, state_var) for state_var in self.state_vars}


class ProductStats:
    """ Struct to store product staistics. """

    def __init__(self, asin: str, product_type: str, drops: List[Drop] = []) -> None:
        """ Init function for Product. """
        self.asin = asin
        self.product_type = product_type
        self.drops = list(drops)

        # Check drops.
        for i, drop in enumerate(self.drops):
            assert drop.asin == self.asin
            assert drop.product_type == self.product_type
            assert drop not in self.drops[:i]

        # Flag to avoid redundant sorting.
        self.sorted = False

    def __repr__(self) -> str:
        """ String representation of `self`. """
        return "ASIN: %s, Type: %s, Num Drops: %d" % (
            self.asin,
            self.product_type,
            self.num_drops,
        )

    def add_drop(self, drop: Drop) -> None:
        """ Add a drop to list of drops over which to compute statistics. """
        assert drop.asin == self.asin
        assert drop.product_type == self.product_type
        assert drop not in self.drops
        self.drops.append(drop)

        self.sorted = False

    @property
    def num_drops(self) -> int:
        """ Total number of drops for product. """
        return len(self.drops)

    @property
    def name(self) -> str:
        """
        Name of product. Note that this isn't a unique identifier and it may even be the
        case that products with the same ASIN have a different name, so you shouldn't
        rely on the name for any consistent information. Also, the name may change as
        more drops are added since we return the name as the majority vote of the names
        of the product in each drop. This should only be used for human readability of
        output.
        """
        if self.drops == []:
            return None
        else:
            names = [drop.name for drop in self.drops]
            return max(set(names), key=names.count)

    @property
    def earliest_drop(self) -> datetime:
        """ Time of earliest drop in list of drops. """
        return min(drop.time for drop in self.drops)

    @property
    def last_drop(self) -> datetime:
        """ Time of last drop in list of drops. """
        return max(drop.time for drop in self.drops)

    @property
    def avg_drop_delta(self) -> timedelta:
        """ Average time between consecutive drops, rounded to the nearest second. """

        # Sort the drops by time, if necessary.
        if not self.sorted:
            self.drops = sorted(self.drops, key=(lambda drop: drop.time))
            self.sorted = True

        # Get average time between drops.
        deltas = [
            self.drops[i + 1].time - self.drops[i].time
            for i in range(len(self.drops) - 1)
        ]
        delta = None
        if len(deltas) > 0:
            delta = timedelta(seconds=int(np.mean(deltas).total_seconds()))
        return delta


def get_tweets(start_time: datetime = None) -> List[Dict[str, Any]]:
    """
    Retrieve list of tweets from Twitter API.

    Parameters
    ----------
    start_time : datetime
        If provided, this function will only retrieve tweets after `start_time`.

    Returns
    -------
    tweets : List[str]
        List of tweets in string format.
    """

    # Read in API credentials.
    with open(TWITTER_CREDENTIALS_PATH, "r") as credentials_file:
        credentials = json.load(credentials_file)

    # Define URL construction function.
    def get_url(prefix: str, kwargs: Dict[str, Any]) -> str:
        url = prefix
        for i, (key, value) in enumerate(kwargs.items()):
            url += "?" if i == 0 else "&"
            url += "%s=%s" % (key, value)
        return url

    # Construct request URL to get user ID.
    headers = {"Authorization": "Bearer {}".format(credentials["bearer_token"])}
    kwargs = {"usernames": TWITTER_USERNAME, "user.fields": "id"}
    url = get_url(TWITTER_USER_URL, kwargs)

    # Make API request to get user ID.
    response = requests.request("GET", url, headers=headers)
    if response.status_code != 200:
        raise Exception(response.status_code, response.text)
    response = response.json()
    user_id = response["data"][0]["id"]

    # Construct request URL to get user tweets.
    kwargs = {
        "tweet.fields": "created_at",
        "max_results": MAX_RESULTS,
    }
    if start_time is not None:
        kwargs["start_time"] = start_time.strftime(TWITTER_TIME_FORMAT_2)
    twitter_timeline_prefix = TWITTER_TIMELINE_URL % user_id
    url = get_url(twitter_timeline_prefix, kwargs)

    # Make API requests.
    tweets = []
    next_token = None
    num_requests = 0
    while num_requests == 0 or next_token is not None:

        # Add pagination token to URL if necessary.
        if next_token is not None:
            kwargs["pagination_token"] = next_token
        url = get_url(twitter_timeline_prefix, kwargs)

        # Make request.
        response = requests.request("GET", url, headers=headers)
        if response.status_code != 200:
            raise Exception(response.status_code, response.text)
        response = response.json()
        num_requests += 1

        # Check whether response is empty.
        if response["meta"]["result_count"] == 0:
            next_token = None
            break

        # Parse response into list of tweets and add to running list.
        tweets += [
            {"text": tweet["text"], "time": tweet["created_at"]}
            for tweet in response["data"]
        ]

        # Get next pagination token.
        if SINGLE_PAGE or "next_token" not in response["meta"]:
            next_token = None
        else:
            next_token = response["meta"]["next_token"]

    return tweets


def get_drops() -> List[Drop]:
    """
    Retrieve list of drops for all products of interest.

    Returns
    -------
    drops : List[Drop]
        List of drops for all products of interest.
    """

    # Load drops from saved database, if it exists.
    drops = []
    most_recent_drop_time = None
    if os.path.isfile(DROP_DATABASE_PATH):
        with open(DROP_DATABASE_PATH, "rb") as drop_database_file:
            drops = pickle.load(drop_database_file)

        # Get time of most recent drop, so we can only pull tweets from after that.
        most_recent_drop_time = max([drop.time for drop in drops])

    # Get notification bot tweets from Twitter API. Note that we only pull tweets from 1
    # second after the most recent drop in the saved database, since the `start_time`
    # parameter is inclusive.
    start_time = (
        None
        if most_recent_drop_time is None
        else most_recent_drop_time + timedelta(seconds=1)
    )
    tweets = get_tweets(start_time=start_time)
    print("total tweets retrieved: %d" % len(tweets))

    # Create requests session to unshorten URLs with.
    session = requests.Session()

    # Track number of tweets violating assumptions (only one product hashtag per tweet,
    # only one link per tweet). If this number is too high, we crash.
    num_bad_tweets = 0

    is_link = lambda x: x.startswith(SHORTENED_URL_PREFIX)
    is_amazon_link = lambda x: AMAZON_URL_KEYWORD in x
    for tweet in tweets:

        tweet_text = tweet["text"]
        tweet_time = tweet["time"]

        # Get Amazon link from tweet, if one exists. There should not be more than one.
        words = tweet_text.split()
        links = [word for word in words if is_link(word)]
        if len(links) > 1:
            num_bad_tweets += 1
            continue
        if len(links) == 0:
            continue
        link = links[0]

        # Get product type from hashtags. There should only be one hashtag in the tweet
        # matching a hashtag describing product type.
        tweet_hashtags = [
            hashtag for hashtag in PRODUCT_TYPES if ("#%s" % hashtag) in words
        ]
        if len(tweet_hashtags) > 1:
            num_bad_tweets += 1
            continue
        if len(tweet_hashtags) == 0:
            continue
        product_type = tweet_hashtags[0]

        # Get full URL and check that it is from Amazon.
        response = session.head(link, allow_redirects=True)
        full_url = response.url
        if not is_amazon_link(full_url):
            continue

        # Get ASIN from full URL.
        phrases = re.split("\?|/", full_url)
        possible_asins = [
            phrase
            for phrase in phrases
            if len(phrase) == ASIN_LEN and phrase.startswith(ASIN_PREFIX)
        ]
        if len(possible_asins) != 1:
            print("Couldn't parse url `%s' for ASIN." % full_url)
        asin = possible_asins[0]

        # Get time of tweet.
        drop_time = datetime.strptime(tweet_time, TWITTER_TIME_FORMAT_1)

        # Get name of product.
        name_end = "N/A"
        for drop_message in [DROP_MESSAGE_1, DROP_MESSAGE_2]:
            if drop_message in tweet_text:
                name_end = tweet_text.find(drop_message)
                product_name = tweet_text[:name_end]
                break

        # Add drop to total list of drops.
        drops.append(Drop(asin, product_name, product_type, drop_time))

    # Check if the number of bad tweets is too high.
    bad_tweet_ratio = num_bad_tweets / max(len(tweets), 1)
    if bad_tweet_ratio > BAD_TWEET_THRESHOLD:
        raise ValueError(
            "Proportion of tweets that violated assumptions is %f, over the acceptable threshold of %f."
            % (bad_tweet_ratio, BAD_TWEET_THRESHOLD)
        )
    else:
        print("bad tweet ratio: %f" % bad_tweet_ratio)

    # Store drops in drop database.
    print("total drops: %d" % len(drops))
    with open(DROP_DATABASE_PATH, "wb") as drop_database_file:
        pickle.dump(drops, drop_database_file)

    return drops


def compute_drop_stats(drops: List[Drop]) -> List[ProductStats]:
    """
    Compute drop statistics for each product from total list of drops.

    Parameters
    ----------
    drops : List[Drop]
        List of drops for all products of interest.

    Returns
    -------
    drop_stats : List[ProductStats]
        List of product drop stats as described by list of drops.
    """

    # Get the most common product type for each ASIN. We do this as a way to robustify
    # the computation. Since there is some noise in older drops, we just vote on the
    # most common product type for each ASIN and discard the violating drops.
    asins = list(set([drop.asin for drop in drops]))
    asin_product_types = {asin: [] for asin in asins}
    for drop in drops:
        asin_product_types[drop.asin].append(drop.product_type)
    asin_best_ptypes = {}
    for asin, ptypes in asin_product_types.items():
        asin_best_ptypes[asin] = max(set(ptypes), key=ptypes.count)

    # Add each drop to running stats.
    bad_drops = 0
    drop_stats = {}
    for drop in drops:
        if drop.asin not in drop_stats:
            drop_stats[drop.asin] = ProductStats(drop.asin, asin_best_ptypes[drop.asin])

        # This is a bit gross, but it's what we have to do with noisy data.
        if drop.product_type == asin_best_ptypes[drop.asin]:
            drop_stats[drop.asin].add_drop(drop)
        else:
            bad_drops += 1

    # Check that not too many drops were violating.
    bad_drop_ratio = bad_drops / max(len(drops), 1)
    if bad_drop_ratio > BAD_DROP_THRESHOLD:
        raise ValueError(
            "Too many drops (%f) where the same ASIN led to different product type."
            % bad_drop_ratio
        )
    else:
        print("bad drop ratio: %f" % bad_drop_ratio)

    return list(drop_stats.values())


def dump_stats(drop_stats: List[ProductStats]) -> None:
    """
    Dump product drop statistics to Google Sheets.

    Parameters
    ----------
    drop_stats : List[ProductStats]
        List of product drop stats.
    """

    # Get earliest drop time.
    start_time = min(product_stat.earliest_drop for product_stat in drop_stats)

    # Partition products by type.
    partitioned_products = {
        product_type: [
            product for product in drop_stats if product.product_type == product_type
        ]
        for product_type in PRODUCT_TYPES
    }

    # Sort products within each product type by number of drops.
    product_key = lambda p: p.num_drops
    for product_type in PRODUCT_TYPES:
        partitioned_products[product_type] = sorted(
            partitioned_products[product_type], key=product_key, reverse=True
        )

    # Dump stats.
    try:

        # Write out stats to temporary CSV file.
        with open(TEMP_CSV_PATH, "w") as temp_csv_file:
            csv_writer = csv.writer(temp_csv_file)

            # Write out header with start date.
            csv_writer.writerow(["Tracking drops since:", start_time.isoformat(" ")])
            csv_writer.writerow(["Last update:", datetime.now().isoformat(" ")])
            csv_writer.writerow([""])

            # Write out column names.
            csv_writer.writerow(
                [
                    "Product Type",
                    "Product Name",
                    "ASIN",
                    "Drops",
                    "",
                    "First Drop",
                    "Last Drop",
                    "Avg Drop Delta",
                ]
            )
            csv_writer.writerow([""])

            # Write out stats for each product.
            for product_type in PRODUCT_TYPES:
                for product in partitioned_products[product_type]:
                    csv_writer.writerow(
                        [
                            product_type,
                            product.name,
                            product.asin,
                            str(product.num_drops),
                            "",
                            product.earliest_drop,
                            product.last_drop,
                            str(product.avg_drop_delta),
                        ]
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
    Main function for drop statistics aggregator.
    """

    # Get history of drops.
    drops = get_drops()

    # Parse tweets and aggregate stats.
    drop_stats = compute_drop_stats(drops)

    # Output statistics to Google Sheets.
    dump_stats(drop_stats)


if __name__ == "__main__":
    main()
