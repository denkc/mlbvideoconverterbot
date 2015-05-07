import datetime
import json
import re
import time

from bs4 import BeautifulSoup
import praw
import psycopg2
import requests

r = praw.Reddit(user_agent="mlbvideoconverter")
r.login('MLBVideoConverterBot', '&ai#n^ky86dQ')  # os.environ['REDDIT_USER'], os.environ['REDDIT_PASS'])

MLB_DESKTOP_PATTERN = r'http://mlb.mlb.com/mlb/.*content_id=(?P<content_id>\d+)'
MLB_MOBILE_PATTERN = r'mlb.com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)/'

MLB_MOBILE_META_IMAGE_PATTERN = r'http://mediadownloads.mlb.com/mlbam/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/images/mlb.*\.jpg'
MLB_MOBILE_FEATURED_VIDEOS_PATTERN = r'(?P<team_away>\w{3})mlb_(?P<team_home>\w{3})mlb_1/game_events.plist';

MLB_MOBILE_URL_FORMAT = 'http://m.mlb.com/video/v{content_id}/'
MLB_MP4_FORMAT = 'http://mediadownloads.mlb.com/mlbam/{year}/{month}/{day}/mlbtv_{team_away}{team_home}_{content_id}_1800K.mp4'

# Not currently used but useful
# MLB_HIGHLIGHTS_XML_FORMAT = 'http://gd2.mlb.com/components/game/mlb/year_{year}/month_{month}/day_{day}/gid_{year}_{month}_{day}_{team_away}mlb_{team_home}mlb_1/media/highlights.xml'

# from https://www.reddit.com/user/Meowingtons-PhD/m/baseballmulti
# subreddits = ['mlbvideoconverterbot']
subreddits = ['angelsbaseball', 'astros', 'azdiamondbacks', 'ballparks', 'baseball', 'baseballcards', 'baseballcirclejerk', 'baseballmuseum', 'baseballstats', 'braves', 'brewers', 'buccos', 'cardinals', 'chicubs', 'collegebaseball', 'coloradorockies', 'dodgers', 'expos', 'fantasybaseball', 'kcroyals', 'letsgofish', 'mariners', 'minnesotatwins', 'mlbdraft', 'motorcitykitties', 'nationals', 'newyorkmets', 'nyyankees', 'oaklandathletics', 'orioles', 'padres', 'phillies', 'reds', 'redsox', 'sabermetrics', 'sfgiants', 'sultansofstats', 'tampabayrays', 'texasrangers', 'torontobluejays', 'wahoostipi', 'wbc', 'whitesox']
limit = 26

def convert_mlb_link(text):
    desktop_match = re.search(MLB_DESKTOP_PATTERN, text)
    mobile_match = re.search(MLB_MOBILE_PATTERN, text)

    if desktop_match:
        format_params = desktop_match.groupdict()
    elif mobile_match:
        format_params = mobile_match.groupdict()
    else:
        return None

    url = MLB_MOBILE_URL_FORMAT.format(**format_params)

    # Get data from meta/script
    soup = BeautifulSoup(requests.get(url).content)
    # looking for system date of the game
    for meta in soup.find_all('meta'):
        if meta.get('name') == 'description' and 'condensed game' in meta['content'].lower():
            print "    condensed game link; skipping: {}".format(text)
            return None
        if meta.get('itemprop') == 'image':
            meta_img_match = re.match(MLB_MOBILE_META_IMAGE_PATTERN, meta['content'])  
            format_params.update(meta_img_match.groupdict())
            break
    else:
        print "    matching link but could not find date: {}".format(text)
    # looking for exact home/away team names
    for script in soup.find_all('script'):
        if 'featuredVideoLists' in script.get_text():
            video_match = re.search(MLB_MOBILE_FEATURED_VIDEOS_PATTERN, script.get_text())
            if video_match:
                format_params.update(video_match.groupdict())
                break
    else:
        print "    matching link but could not find team names: {}".format(text)

    print "    match found: {}".format(text) 
   
    return MLB_MP4_FORMAT.format(**format_params)

conn = psycopg2.connect(
    host=localhost,  # os.environ['DB_HOST'],
    dbname='mlb',
    user='postgres',  # os.environ['DB_USER'],
    password="Don't1stop2me3now"  # os.environ['DB_PASSWORD']
)
cursor = conn.cursor()
cursor.execute("CREATE DATABASE IF NOT EXISTS mlb")
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
    for subreddit in subreddits:
        print "  Checking {}".format(subreddit)
        try:
            submissions = r.get_subreddit(subreddit).get_hot(limit=limit)
        except:
            print "error encountered getting submissions for {}.".format(subreddit)
            continue

        for submission in submissions:
            if check_hash_exists('submissions', submission.id):
                continue

            if submission.is_self:
                mlb_link = convert_mlb_link(submission.selftext)
            else:
                mlb_link = convert_mlb_link(submission.url)

            if not mlb_link:
                continue

            submission.add_comment(comment_text(mlb_link))
            cursor.execute("INSERT INTO submissions (hash_id) VALUES ('{}');".format(submission.id))
            conn.commit()

            for comment in submission.comments:
                if check_hash_exists('comments', comment.id):
                    continue

                mlb_link = convert_mlb_link(comment.body)
                if mlb_link:
                    comment.reply(comment_text(mlb_link))
                    cursor.execute("INSERT INTO comments (hash_id) VALUES ('{}');".format(comment.id))
                    conn.commit()

    print "Done with iteration"
    time.sleep(300)
