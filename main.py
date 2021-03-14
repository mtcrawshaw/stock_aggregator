"""
Compute and print out statisics for GPU restocking frequency according to tweets of
@SnailMonitor.
"""

import argparse


def main(history_days: int, product_keywords: List[str]) -> None:
    """
    Main function for restock statistics aggregator.

    Parameters
    ----------
    history_days : int
        Number of days to look back in tweet history.
    product_keywords : List[str]
        List of keywords to qualify a tweet. If a keyword appears in a tweet, the ASIN
        of the product listed in the tweet will be added to the list of products for
        which statistics are computed.
    """

    # Get tweets from Twitter API.

    # Parse tweets and aggregate stats.

    # Output statistics to Google sheets.


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("history_days", type=int, help="Number of days to look back in tweet history.")
    parser.add_argument("product_keywords", type=str, help="Comma-separated list of keywords to qualify a tweet.")
    args = parser.parse_args()

    main(args.history_days, args.product_keywords.split(","))
