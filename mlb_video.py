import datetime
import itertools
import json
import re
import time
from xml.etree import ElementTree

from bs4 import BeautifulSoup
import praw
import praw.helpers
import psycopg2
import requests

r = praw.Reddit(user_agent="mlbvideoconverter")
r.login('MLBVideoConverterBot', '&ai#n^ky86dQ')  # os.environ['REDDIT_USER'], os.environ['REDDIT_PASS'])

MLB_PATTERNS = [
    r'mlb.mlb.com/mlb/.*content_id=(?P<content_id>\d+)',
    r'mlb.com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)/',
    r'www.mlb.com/r/video\?.*content_id=(?P<content_id>\d+)'
]

MLB_MOBILE_FEATURED_VIDEOS_PATTERN = r'"keyword":"(?P<xml_base_path>http://gdx.mlb.com/components/game/mlb/year_\d{4}/month_\d{2}/day_\d{2}/gid_\d{4}_\d{2}_\d{2}_\w{3}mlb_\w{3}mlb_1/)game_events.plist"'
# (?P<team_away>\w{3})mlb_(?P<team_home>\w{3})mlb_1/game_events.plist';

MLB_MP4_FORMAT = 'http://mediadownloads.mlb.com/mlbam/{year}/{month}/{day}/mlbtv_{team_away}{team_home}_{content_id}_1800K.mp4'

# Used to find true URL instead of inferring date
# MLB_HIGHLIGHTS_XML_FORMAT = 'http://gd2.mlb.com/components/game/mlb/year_{year}/month_{month}/day_{day}/gid_{year}_{month}_{day}_{team_away}mlb_{team_home}mlb_1/media/highlights.xml'
MLB_VIDEO_XML_FORMAT = 'http://mlb.com/gen/multimedia/detail/{first}/{second}/{third}/{content_id}.xml'

# from https://www.reddit.com/user/Meowingtons-PhD/m/baseballmulti
primary_subreddits = ['baseball', 'fantasybaseball']
secondary_subreddits = ['angelsbaseball', 'astros', 'azdiamondbacks', 'braves', 'brewers', 'buccos', 'cardinals', 'chicubs', 'coloradorockies', 'dodgers', 'expos', 'kcroyals', 'letsgofish', 'mariners', 'minnesotatwins', 'motorcitykitties', 'nationals', 'newyorkmets', 'nyyankees', 'oaklandathletics', 'orioles', 'padres', 'phillies', 'reds', 'redsox', 'sfgiants', 'tampabayrays', 'texasrangers', 'torontobluejays', 'wahoostipi', 'whitesox']
# ['ballparks', 'baseballcards', 'baseballcirclejerk', 'baseballmuseum', 'baseballstats', 'collegebaseball', 'mlbdraft', 'sabermetrics', 'sultansofstats', 'wbc']

# testing override
# primary_subreddits = ['mlbvideoconverterbot']; secondary_subreddits = []

primary_limit = 26
group_size = 16
group_limit = 100

def convert_mlb_link(text):
    text = text.encode('utf-8')

    for mlb_pattern in MLB_PATTERNS:
        match = re.search(mlb_pattern, text)
        if match:
            content_id = match.group('content_id')
            break
    else:
        return None

    url = MLB_VIDEO_XML_FORMAT.format(**{
        "first": content_id[-3],
        "second": content_id[-2],
        "third": content_id[-1],
        "content_id": content_id
    })
    tree = ElementTree.fromstring(requests.get(url).content)
    media_tags = tree.findall('url[@playback_scenario]')

    largest_mp4_size = 0
    largest_mp4_url = None

    for media_tag in media_tags:
        mp4_size_match = re.search('_(?P<mp4_size>\d+)K\.mp4', media_tag.text)
        if mp4_size_match is not None:
            mp4_size = int(mp4_size_match.group('mp4_size'))
            if mp4_size > largest_mp4_size:
                largest_mp4_size = mp4_size
                largest_mp4_url = media_tag.text

    return largest_mp4_url

conn = psycopg2.connect(
    host='localhost',  # os.environ['DB_HOST'],
    dbname='mlb',
    user='postgres',  # os.environ['DB_USER'],
    password="Don't1stop2me3now"  # os.environ['DB_PASSWORD']
)
cursor = conn.cursor()
#cursor.execute("CREATE DATABASE IF NOT EXISTS mlb")
cursor.execute("CREATE TABLE IF NOT EXISTS submissions (hash_id varchar PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS comments (hash_id varchar PRIMARY KEY)")
conn.commit()

def check_hash_exists(table_name, hash_id):
    cursor.execute("SELECT hash_id FROM {} WHERE hash_id = '{}';".format(table_name, hash_id))
    match = cursor.fetchone()
    return match

def comment_text(comment):
    return '''{}
_____________
[Report broken link](https://www.reddit.com/message/compose/?to=MLBVideoConverterBot)

[More Info](https://www.reddit.com/r/MLBVideoConverterBot)'''.format(comment)

iteration = 0
while True:
    print "Iteration: {}".format(iteration)
    iteration += 1
    subreddits = [(subreddit, primary_limit) for subreddit in primary_subreddits]
    subreddits += [("+".join(secondary_subreddits[i:i+group_size]), group_limit) for i in range(0, len(secondary_subreddits), group_size)]
    for subreddit, limit in subreddits:
        print "  Checking {}".format(subreddit)
        try:
            submissions = r.get_subreddit(subreddit).get_hot(limit=limit)
        except:
            print "error encountered getting submissions for {}.".format(subreddit)
            continue

        for submission in submissions:
            if not check_hash_exists('submissions', submission.id):
                if submission.is_self:
                    mlb_link = convert_mlb_link(submission.selftext)
                else:
                    mlb_link = convert_mlb_link(submission.url)

                if mlb_link:
                    submission.add_comment(comment_text(mlb_link))
                    cursor.execute("INSERT INTO submissions (hash_id) VALUES ('{}');".format(submission.id))
                    conn.commit()

            # submission.replace_more_comments(limit=None, threshold=0)
            try:
                comments = praw.helpers.flatten_tree(submission.comments)
            except:
                print "error encountered getting comments for {}.{}".format(subreddit, submission.id)
                continue
            for comment in praw.helpers.flatten_tree(submission.comments):
                if check_hash_exists('comments', comment.id):
                    continue

                if comment.__class__.__name__ == 'MoreComments':
                    continue

                mlb_link = convert_mlb_link(comment.body)
                if mlb_link:
                    comment.reply(comment_text(mlb_link))
                    cursor.execute("INSERT INTO comments (hash_id) VALUES ('{}');".format(comment.id))
                    conn.commit()

    print "Done with iteration"
    time.sleep(300)
