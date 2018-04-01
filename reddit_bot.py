import praw
from praw.models import Comment

from mlb import find_mlb_links
import config
import db

reddit = praw.Reddit(
    user_agent=config.REDDIT_USERAGENT,
    client_id=config.REDDIT_CLIENT_ID,
    client_secret=config.REDDIT_CLIENT_SECRET,
    username=config.REDDIT_USER,
    password=config.REDDIT_PASS
)

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
# subreddits = ['mlbvideoconverterbot']; domains = []

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

    return True

def check_comment(comment):
    conn, cursor = db.connect_to_db()

    try:
        if db.check_hash_exists('comments', comment.id, cursor):
            return False
        if comment.__class__.__name__ == 'MoreComments':
            return False

        mlb_links = find_mlb_links(comment.body)
        if reply(mlb_links, comment):
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

        if reply(mlb_links, submission):
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
    # Even though main is already wrapped in a while True below, this maintains the
    #   stream settings so it doesn't load any historical info
    iteration = 0
    while True:
        print "Iteration: {}".format(iteration)
        iteration += 1

        subreddit = reddit.subreddit('+'.join(subreddits))
        comment_stream = subreddit.stream.comments(pause_after=5)
        submission_stream = subreddit.stream.submissions(pause_after=5)

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

        #  Skip domain checks as they take too long
        '''
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
        '''

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception, e:
            import sys, traceback; ex_type, ex, tb = sys.exc_info(); traceback.print_tb(tb)
            print "Error: {}".format(e)
