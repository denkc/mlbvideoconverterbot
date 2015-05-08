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

# Used to find true URL instead of inferring date
MLB_VIDEO_XML_FORMAT = 'http://mlb.com/gen/multimedia/detail/{first}/{second}/{third}/{content_id}.xml'

# from https://www.reddit.com/user/Meowingtons-PhD/m/baseballmulti
primary_subreddits = ['baseball', 'fantasybaseball']
secondary_subreddits = ['angelsbaseball', 'astros', 'azdiamondbacks', 'braves', 'brewers', 'buccos', 'cardinals', 'chicubs', 'coloradorockies', 'dodgers', 'expos', 'kcroyals', 'letsgofish', 'mariners', 'minnesotatwins', 'motorcitykitties', 'nationals', 'newyorkmets', 'nyyankees', 'oaklandathletics', 'orioles', 'padres', 'phillies', 'reds', 'redsox', 'sfgiants', 'tampabayrays', 'texasrangers', 'torontobluejays', 'wahoostipi', 'whitesox']
# ['ballparks', 'baseballcards', 'baseballcirclejerk', 'baseballmuseum', 'baseballstats', 'collegebaseball', 'mlbdraft', 'sabermetrics', 'sultansofstats', 'wbc']

primary_domains = ['mlb.com']

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

def subreddit_submissions(subreddits):
    for subreddit, limit in subreddits:
        try:
            print "  Checking {}".format(subreddit)
            yield r.get_subreddit(subreddit).get_hot(limit=limit)
        except:
            print "error encountered getting submissions for {}.".format(subreddit)
            continue

def domain_submissions():
    for domain, limit in domains:
        try:
            print "  Checking {}".format(domain)
            yield r.get_domain_listing(domain, limit=limit)
        except:
            print "error encountered getting submissions for domain {}.".format(domain)
            continue

def find_mlb_links():
    subreddits = [(subreddit, primary_limit) for subreddit in primary_subreddits]
    subreddits += [("+".join(secondary_subreddits[i:i+group_size]), group_limit) for i in range(0, len(secondary_subreddits), group_size)]
    domains = [(domain, primary_limit) for domain in primary_domains]
    for submission in itertools.chain(subreddit_submissions(subreddits), domain_submissions(domains)):
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

iteration = 0
while True:
    start_time = time.time() 
    print "Iteration: {}".format(iteration)
    iteration += 1
    try:
        find_mlb_links()
        print "Done with iteration.  Time to run: {}".format(time.time()-start_time)
    except Exception, e:
        print "Error: {}".format(e)
        pass
    time.sleep(300)
