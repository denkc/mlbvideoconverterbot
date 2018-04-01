import re
from xml.etree import ElementTree

import praw
from praw.models import Comment
import requests

import config
import db

reddit = praw.Reddit(
    user_agent=config.REDDIT_USERAGENT,
    client_id=config.REDDIT_CLIENT_ID,
    client_secret=config.REDDIT_CLIENT_SECRET,
    username=config.REDDIT_USER,
    password=config.REDDIT_PASS
)

MLB_PATTERNS = [
    r'(?P<domain>mi?lb).com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*content_id=(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*/v(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*/c-(?P<content_id>\d+)',
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
subreddits = [
    'baseball', 'fantasybaseball', 'mlbvideoconverterbot',
    'angelsbaseball', 'astros', 'azdiamondbacks', 'braves', 'brewers', 'buccos', 'cardinals', 'chicubs',
    'coloradorockies', 'dodgers', 'expos', 'kcroyals', 'letsgofish', 'mariners', 'minnesotatwins', 'motorcitykitties',
    'nationals', 'newyorkmets', 'nyyankees', 'oaklandathletics', 'orioles', 'padres', 'phillies', 'reds', 'redsox',
    'sfgiants', 'tampabayrays', 'texasrangers', 'torontobluejays', 'wahoostipi', 'whitesox'
]
# ['ballparks', 'baseballcards', 'baseballcirclejerk', 'baseballmuseum', 'baseballstats', 'collegebaseball', 'mlbdraft', 'sabermetrics', 'sultansofstats', 'wbc']

domains = ['mlb.com', 'atmlb.com']

# testing override
# primary_subreddits = ['mlbvideoconverterbot']; secondary_subreddits = []; primary_domains = []

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
        if not media_tag.text:
            continue
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

def reply(mlb_links, comment_or_submission):
    if not mlb_links:
        return False

    for split_mlb_links in chunks(mlb_links, 20):
        comment_string = ''
        for video_block_text in split_mlb_links:
            comment_string += "\n\n".join(video_block_text) + "\n\n"
        try:
            comment_or_submission.reply(comment_text(comment_string))
        except Exception, e:
            import sys, traceback;
            ex_type, ex, tb = sys.exc_info();
            traceback.print_tb(tb)
            print "Error: {}".format(e)
            pass

def check_comment(comment):
    conn, cursor = db.connect_to_db()

    try:
        if db.check_hash_exists('comments', comment.id, cursor):
            return False
        if comment.__class__.__name__ == 'MoreComments':
            return False

        mlb_links = find_mlb_links(comment.body)
        if reply(mlb_links, comment=comment):
            cursor.execute("INSERT INTO comments (hash_id) VALUES ('{}');".format(comment.id))
            conn.commit()
            return True

        return False
    finally:
        conn.close()

def check_submission(submission):
    conn, cursor = db.connect_to_db()

    try:
        if db.check_hash_exists('submissions', submission.id, cursor):
            return False

        if submission.is_self:
            mlb_links = find_mlb_links(submission.selftext)
        else:
            mlb_links = find_mlb_links(submission.url)

        if reply(mlb_links, submission=submission):
            cursor.execute("INSERT INTO submissions (hash_id) VALUES ('{}');".format(submission.id))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def comment_text(comment):
    return '''{}

[More Info](/r/MLBVideoConverterBot)'''.format(comment)

def domain_submissions(domains):
    for domain in domains:
        try:
            print "  Checking {}".format(domain)
            for submission in reddit.domain(domain).hot():
                yield submission
        except:
            print "error encountered getting submissions for domain {}.".format(domain)
            continue

# http://stackoverflow.com/a/312464/190597 (Ned Batchelder)
def chunks(seq, n):
    """ Yield successive n-sized chunks from seq."""
    for i in xrange(0, len(seq), n):
        yield seq[i:i + n]

def main():
    subreddit = reddit.subreddit('+'.join(subreddits))
    comment_stream = subreddit.stream.comments(pause_after=0)
    submission_stream = subreddit.stream.submissions(pause_after=0)

    for comment in comment_stream:
        if comment is None:
            break
        check_comment(comment)

    for submission in submission_stream:
        if submission is None:
            break
        check_submission(submission)

    for comment in reddit.inbox.unread(mark_read=True, limit=None):
        if isinstance(comment, Comment):
            check_comment(comment)

    #  No domain stream exists yet; check submissions the old fashioned way
    for submission in domain_submissions(domains):
        check_submission(submission)

        try:
            comments = submission.comments.list()
        except:
            print "error encountered getting comments for http://redd.it/{}".format(submission.id)
            continue

        for comment in comments:
            check_comment(comment)

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception, e:
            import sys, traceback; ex_type, ex, tb = sys.exc_info(); traceback.print_tb(tb)
            print "Error: {}".format(e)
