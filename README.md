# MLB Video Converter Bot

Reddit PRAW bot set to run as a longrunning python script with fast response times by reading the comment and
submission streams.

## Running the bot

Set the values in config.py to your [Reddit App](https://www.reddit.com/prefs/apps/) and account login values.
For more information, see the [PRAW docs](https://praw.readthedocs.io/en/stable/getting_started/quick_start.html).

Run with virtualenv and pip as follows:
```
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
python reddit_bot.py
```

## Testing a single URL

If you have a single MLB.com link you'd like to test out, use
```
python mlb.py <link>
```

Note that the output will be formatted for Reddit markdown.