# Watchful Eye

Tool to aggregate statistics for GPU restocking frequency on Amazon. This is intended to help those trying to buy a GPU on Amazon by providing information about which Amazon products are restocked most often, and when they are restocked. The restocking statistics are collected once a day and dumped to the following spreadsheet:

https://docs.google.com/spreadsheets/d/1hDlVCDmxLbsKevo3kOwfhL4R44rJxwlcy_oY7db53VA/edit?usp=sharing

Good luck with your hardware hunt!

## Implementation Notes
If you want to run the aggregator yourself, there's a couple things you should know.

First of all, this doesn't do any scraping from Amazon directly, since that would require constantly running the system and checking for inventory availability. There would be no way to guarantee that the tool would be able to notice inventory changes while scanning for all products simultaneously. Instead, we just scrape the Twitter feed of a notification bot, namely [@SnailMonitor](https://twitter.com/SnailMonitor). However, because Twitter only gives you limited API access if your project isn't for academic research, we can only get tweets which are from at most 7 days before the API call is made. Because of this, the system has to build up data over time. It's annoying, but it's what we got.

Second, there are a few things you'll need to set up in order to actually run the aggregator. You need to set up API keys with the [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard) and the [Google Drive API](https://developers.google.com/drive) in order to scrape tweets and upload stats to Google Drive. The Twitter/Google credentials are expected to be stored in twitter_credentials.json and drive_credentials.json, respectively, in the root directory of the repo. You should add a field to drive_credentials.json with the key "spreadsheet_id", whose value is the Spreadsheet ID of whatever spreadsheet you want to write to. If you're not sure what this means, check the [Google Drive docs](https://developers.google.com/drive/api/v3/about-sdk)!

The tool is pretty janky right now, but it gets the job done and I may refactor as I go.

## Running the Aggregator
Once you set up your API keys as described above, you only need to install a single external dependency (`gspread`) before you can run the tool. To do this, run:
```
pip install gspread
```
After that, you can run the tool with:
```
python3 main.py
```
If you want to change which products are monitored, you just need to change the values in `PRODUCT_TYPES` in `main.py`. Careful though! You will need to enter the unique hashtag used by [@SnailMonitor](https://twitter.com/SnailMonitor) when they tweet a restock notification. If you look through the current values in `PRODUCT_TYPES` and some tweets from this account, you should get the idea.
