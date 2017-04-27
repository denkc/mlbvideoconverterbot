import itertools
import re
import time
from xml.etree import ElementTree

import praw
import praw.helpers
import requests

import config
import db

r = praw.Reddit(user_agent=config.REDDIT_USERAGENT)
#r.set_oauth_app_info(client_id=config.CLIENT_ID, client_secret=config.CLIENT_SECRET, redirect_uri=config.REDIRECT_URI)
r.login(config.REDDIT_USER, config.REDDIT_PASS)

MLB_PATTERNS = [
    r'(?P<domain>mi?lb).com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*content_id=(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*/v(?P<content_id>\d+)'
]

SHORTURL_PATTERNS = [
    r'(?:https?://)?(?P<url>atmlb.com\S+)'
]

# Used to find true URL instead of inferring date
MLB_VIDEO_XML_FORMAT = 'http://www.{domain}.com/gen/multimedia/detail/{first}/{second}/{third}/{content_id}.xml'

MLB_XML_IGNORED_SUBJECTS = [
    'MLBCOM_CONDENSED_GAME',
    'LIVE_EVENT_COVERAGE'
]

# from https://www.reddit.com/user/Meowingtons-PhD/m/baseballmulti
primary_subreddits = ['baseball', 'fantasybaseball', 'mlbvideoconverterbot']
secondary_subreddits = ['angelsbaseball', 'astros', 'azdiamondbacks', 'braves', 'brewers', 'buccos', 'cardinals', 'chicubs', 'coloradorockies', 'dodgers', 'expos', 'kcroyals', 'letsgofish', 'mariners', 'minnesotatwins', 'motorcitykitties', 'nationals', 'newyorkmets', 'nyyankees', 'oaklandathletics', 'orioles', 'padres', 'phillies', 'reds', 'redsox', 'sfgiants', 'tampabayrays', 'texasrangers', 'torontobluejays', 'wahoostipi', 'whitesox']
# ['ballparks', 'baseballcards', 'baseballcirclejerk', 'baseballmuseum', 'baseballstats', 'collegebaseball', 'mlbdraft', 'sabermetrics', 'sultansofstats', 'wbc']

primary_domains = ['mlb.com', 'atmlb.com']

# testing override
# primary_subreddits = ['mlbvideoconverterbot']; secondary_subreddits = []; primary_domains = []

primary_limit = 26
group_size = 16
group_limit = 100

def find_mlb_links(text):
    text = text.encode('utf-8')

    shorturl_text = ''
    for shorturl_pattern in SHORTURL_PATTERNS:
        matches = re.finditer(shorturl_pattern, text)
        for match in matches:
            shorturl_headers = requests.head('http://{}'.format(match.group('url')))
            if shorturl_headers.status_code == 301:
                shorturl_text += '{} '.format(shorturl_headers.headers['location'])

    text += ' {}'.format(shorturl_text)

    re_matches = []

    for mlb_pattern in MLB_PATTERNS:
        matches = re.finditer(mlb_pattern, text)
        for match in matches:
            print "    match {} found: {}".format(match.groupdict(), text)
            re_matches.append(match)

    unique_content_id = set()

    formatted_comments = []
    for match in re_matches:
        if match.group('content_id') in unique_content_id:
            continue
        unique_content_id.add(match.group('content_id'))
        media_links = get_media_for_content_id(match)
        if not media_links:
            print "    no media link found for {}".format(match.group('content_id'))
            continue
        title = media_links['title']
        video_text_block = []
        video_text_block.append("Video: {}".format(title))
        for media_link, link_text in media_links['media']:
            size_mb = round(float(requests.head(media_link).headers['content-length'])/(1024**2), 2)
            video_text_block.append("[{}]({}) ({} MB)".format(link_text, media_link, size_mb))
        video_text_block.append("___________")
        formatted_comments.append(video_text_block)

    return formatted_comments

def get_media_for_content_id(match):
    content_id = match.group('content_id')
    url = MLB_VIDEO_XML_FORMAT.format(**{
        "domain": match.group('domain'),
        "first": content_id[-3],
        "second": content_id[-2],
        "third": content_id[-1],
        "content_id": content_id
    })
    try:
        tree = ElementTree.fromstring(requests.get(url).content)
    except Exception, e:
        print "    error parsing/receiving XML from url {}".format(url)
        return {}

    keyword = tree.find('keywords').find('keyword[@type="subject"]')
    if keyword.get('value') in MLB_XML_IGNORED_SUBJECTS:
        return {}

    title = tree.find('blurb').text
    media_tags = tree.findall('url[@playback_scenario]')


    small_mp4_size = 0
    small_mp4_threshold = 640
    small_mp4_url = None

    largest_mp4_size = 0
    largest_mp4_url = None

    for media_tag in media_tags:
        mp4_size_match = re.search('_(?P<mp4_size>\d+)K\.mp4', media_tag.text)
        if mp4_size_match is not None:
            mp4_size = int(mp4_size_match.group('mp4_size'))
            if mp4_size > largest_mp4_size:
                largest_mp4_size = mp4_size
                largest_mp4_url = media_tag.text
            if small_mp4_threshold > mp4_size > small_mp4_size:
                small_mp4_size = mp4_size
                small_mp4_url = media_tag.text

    # Need to match at least one else return nothing
    if largest_mp4_url is None:
        return {}

    if small_mp4_size == largest_mp4_size or small_mp4_url is None:
        largest_mp4_text = "MP4 Video"
    else:
        largest_mp4_text = "Larger Version"

    media = {"title": title, "media": [(largest_mp4_url, largest_mp4_text)]}
    if small_mp4_size != largest_mp4_size and small_mp4_url is not None:
        media['media'].append((small_mp4_url, 'Smaller Version'))
 
    return media

def comment_text(comment):
    return '''{}

[More Info](/r/MLBVideoConverterBot)'''.format(comment)

def subreddit_submissions(subreddits):
    for subreddit, limit in subreddits:
        try:
            print "  Checking {}".format(subreddit)
            for submission in r.get_subreddit(subreddit).get_hot(limit=limit):
                yield submission
        except:
            print "error encountered getting submissions for {}.".format(subreddit)
            continue

def domain_submissions(domains):
    for domain, limit in domains:
        try:
            print "  Checking {}".format(domain)
            for submission in r.get_domain_listing(domain, limit=limit):
                yield submission
        except:
            print "error encountered getting submissions for domain {}.".format(domain)
            continue

# http://stackoverflow.com/a/312464/190597 (Ned Batchelder)
def chunks(seq, n):
    """ Yield successive n-sized chunks from seq."""
    for i in xrange(0, len(seq), n):
        yield seq[i:i + n]

def bot():
    conn, cursor = db.connect_to_db()
    subreddits = [(subreddit, primary_limit) for subreddit in primary_subreddits]
    subreddits += [("+".join(secondary_subreddits[i:i+group_size]), group_limit) for i in range(0, len(secondary_subreddits), group_size)]
    domains = [(domain, primary_limit) for domain in primary_domains]

    for submission in itertools.chain(subreddit_submissions(subreddits), domain_submissions(domains)):
        if not db.check_hash_exists('submissions', submission.id, cursor):
            if submission.is_self:
                mlb_links = find_mlb_links(submission.selftext)
            else:
                mlb_links = find_mlb_links(submission.url)

            if mlb_links:
                for split_mlb_links in chunks(mlb_links, 20):
                    comment_string = ''
                    for video_block_text in split_mlb_links:
                        comment_string += "\n\n".join(video_block_text) + "\n\n"
                    try:
                        submission.add_comment(comment_text(comment_string))
                    except Exception, e:
                        import sys, traceback;
                        ex_type, ex, tb = sys.exc_info();
                        traceback.print_tb(tb)
                        print "Error: {}".format(e)
                        pass
                cursor.execute("INSERT INTO submissions (hash_id) VALUES ('{}');".format(submission.id))
                conn.commit()

        # submission.replace_more_comments(limit=None, threshold=0)
        try:
            comments = praw.helpers.flatten_tree(submission.comments)
        except:
            print "error encountered getting comments for http://redd.it/{}".format(submission.id)
            continue
        for comment in praw.helpers.flatten_tree(submission.comments):
            if db.check_hash_exists('comments', comment.id, cursor):
                continue

            if comment.__class__.__name__ == 'MoreComments':
                continue

            mlb_links = find_mlb_links(comment.body)
            if mlb_links:
                for split_mlb_links in chunks(mlb_links, 20):
                    comment_string = ''
                    for video_block_text in split_mlb_links:     
                        comment_string += "\n\n".join(video_block_text) + "\n\n"
                    comment.reply(comment_text(comment_string))
                cursor.execute("INSERT INTO comments (hash_id) VALUES ('{}');".format(comment.id))
                conn.commit()
    conn.close()

iteration = 0
while True:
    start_time = time.time() 
    print "Iteration: {}".format(iteration)
    iteration += 1
    try:
        bot()
        print "Done with iteration.  Time to run: {}".format(time.time()-start_time)
    except Exception, e:
        import sys, traceback; ex_type, ex, tb = sys.exc_info(); traceback.print_tb(tb)
        print "Error: {}".format(e)
        pass
    time.sleep(30)
