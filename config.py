import os
import urlparse

REDDIT_USERAGENT = 'mlbvideoconverter'
REDDIT_USER='MLBVideoConverterBot'
REDDIT_PASS='&ai#n^ky86dQ'

url = urlparse.urlparse(os.environ["DATABASE_URL"])

DB = {
    'database': url.path[1:],
    'user': url.username,
    'password': url.password,
    'host': url.hostname,
    'port': url.port
}

