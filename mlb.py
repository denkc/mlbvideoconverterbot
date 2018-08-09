import re
from xml.etree import ElementTree

import requests

MLB_PATTERNS = [
    r'(?P<domain>mi?lb).com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*content_id=(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*/v(?P<content_id>\d+)',
    r'(?P<domain>mi?lb).com/.*/c-(?P<content_id>\d+)',
]

MLB_SKIP_PATTERNS = [
    r'mlb.com/news'
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

def skip_match(text):
    for skip_pattern in MLB_SKIP_PATTERNS:
        skip_match = re.search(skip_pattern, text)
        if skip_match:
            return True
    return False


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
            if skip_match(match.string):
                continue
            print "    match {} found: {}".format(match.groupdict(), text)
            re_matches.append(match)

    return format_comments(re_matches)


def format_comments(regex_matches):
    unique_content_id = set()
    formatted_comments = []

    for match in regex_matches:
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
        print "    error parsing/receiving XML from url {}: {}".format(url, e)
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