from __future__ import absolute_import
from __future__ import print_function
import json
import re
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

OLD_MLB_PATTERNS = [
    '(?P<domain>mi?lb).com/(?:\w{2,3}/)?video/(?:topic/\d+/)?v(?P<content_id>\d+)',
    '(?P<domain>mi?lb).com/.*content_id=(?P<content_id>\d+)',
    '(?P<domain>mi?lb).com/.*/v(?P<content_id>\d+)',
    '(?P<domain>mi?lb).com/.*/c-(?P<content_id>\d+)',
]

MLB_PATTERNS = [
    '\S*mi?lb.com/video/(?P<content_id>[\w\-]*)'
]

MLB_SKIP_PATTERNS = [
    'mlb.com/news'
]

SHORTURL_PATTERNS = [
    '(?:https?://)?(?P<url>atmlb.com\S+)'
]

MLB_VIDEO_JSON_FORMAT = 'https://www.mlb.com/data-service/en/videos/{content_id}'
# Used to find true URL instead of inferring date
MLB_OLD_VIDEO_XML_FORMAT = 'http://www.{domain}.com/gen/multimedia/detail/{first}/{second}/{third}/{content_id}.xml'

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
    shorturl_text = ''
    for shorturl_pattern in SHORTURL_PATTERNS:
        matches = re.finditer(shorturl_pattern, text)
        for match in matches:
            shorturl_headers = requests.head('http://{}'.format(match.group('url')))
            if shorturl_headers.status_code == 301:
                shorturl_text += '{} '.format(shorturl_headers.headers['location'])

    text += ' {}'.format(shorturl_text)

    old_re_matches = []

    for mlb_pattern in OLD_MLB_PATTERNS:
        matches = re.finditer(mlb_pattern, text)
        for match in matches:
            if skip_match(match.string):
                continue
            print("    old match {} found: {}".format(match.groupdict(), text))
            old_re_matches.append(match)

    old_matches, old_matched_content_ids = format_old_comments(old_re_matches)

    re_matches = []

    for mlb_pattern in MLB_PATTERNS:
        matches = re.finditer(mlb_pattern, text)
        for match in matches:
            # need to not duplicate old links
            if match.group() in old_matched_content_ids:
                break
            else:
                print("    match {} found: {}".format(match.group(), text))
                re_matches.append(match)

    return old_matches + format_comments(re_matches)


def format_comments(regex_matches):
    unique_content_id = set()
    formatted_comments = []

    for match in regex_matches:
        if match.group('content_id') in unique_content_id:
            continue
        unique_content_id.add(match.group('content_id'))
        media_links = get_media_for_content_id(match)
        if not media_links:
            print("    no media link found for {}".format(match.group('content_id')))
            continue
        formatted_comments.append(format_link(media_links))

    return formatted_comments


def get_media_for_content_id(match):

    def get_media_from_json(match_):
        content_id = match_.group('content_id')
        url = MLB_VIDEO_JSON_FORMAT.format(**{
            "content_id": content_id
        })
        video_data = json.loads(requests.get(url).content)
        if 'playbacks' not in video_data:
            return {}

        media = []

        for playback in video_data['playbacks']:
            if playback['name'] not in ('mp4Avc', 'highBit'):
                continue
            media.append((playback['url'], 'Direct Link'))

        return {'title': video_data['blurb'], 'media': media}

    def get_media_from_html(match_):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        }
        resp = requests.get(parse_reddit_formatted_link(match_.group()), headers=headers)
        page_content = BeautifulSoup(resp.content, 'html.parser')

        script_contents = page_content.find("script", type="application/ld+json")
        video_info = json.loads(script_contents.encode_contents())

        title = video_info['name']

        # MLB now providing streamable links, which is nice.
        media = []
        if video_info['embedUrl']:
            media.append((video_info['embedUrl'], "Streamable Link"))
        if video_info['contentUrl'] and not video_info['contentUrl'].endswith('m3u8'):
            media.append((video_info['contentUrl'], "Direct Link"))

        return {'title': title, 'media': media}

    json_media = get_media_from_json(match)
    html_media = get_media_from_html(match)

    unique_links = set()

    # dedupe across json/html
    media = []
    for media_link, link_text in json_media['media'] + html_media['media']:
        if media_link in unique_links:
            continue
        media.append((media_link, link_text))

    return {'title': html_media['title'], 'media': media}

# Reddit links can either be linked directly
# - https://www.mlb.com/video/edwin-rios-called-out-on-strikes
# Or they can be formatted
# - [https://www.mlb.com/video/encarnacion-gets-yanks-on-board](https://www.mlb.com/video/encarnacion-gets-yanks-on-board)
# This method extracts the link from the second format, or returns if unformatted
def parse_reddit_formatted_link(link):
    return link.split('](').pop().rstrip(')')


# Expects media_links with keys:
# - title: string
# - media: list of tuples of (link, text for link)
def format_link(media_links):
    title = media_links['title']
    video_text_block = []
    video_text_block.append("Video: {}".format(title))
    for media_link, link_text in media_links['media']:
        # Hack to skip getting content size if it's on Streamable
        if link_text == "Streamable Link":
            video_text_block.append("[{}]({})".format(link_text, media_link))
            continue

        headers = requests.head(media_link)
        # Can be a redirect if it's a fastball-clips URL
        if headers.status_code == 200:
            size_mb = round(float(headers.headers['content-length']) / (1024 ** 2), 2)
            video_text_block.append("[{}]({}) ({} MB)".format(link_text, media_link, size_mb))
    video_text_block.append("___________")
    return video_text_block


def format_old_comments(regex_matches):
    unique_content_id = set()
    formatted_comments = []
    matched_content_ids = set()

    for match in regex_matches:
        if match.group('content_id') in unique_content_id:
            continue
        unique_content_id.add(match.group('content_id'))
        media_links = get_media_for_old_content_id(match)
        if not media_links:
            print("    no media link found for {}".format(match.group('content_id')))
            continue
        formatted_comments.append(format_link(media_links))
        matched_content_ids.add(match.group('content_id'))

    return formatted_comments, matched_content_ids


def get_media_for_old_content_id(match):
    content_id = match.group('content_id')
    url = MLB_OLD_VIDEO_XML_FORMAT.format(**{
        "domain": match.group('domain'),
        "first": content_id[-3],
        "second": content_id[-2],
        "third": content_id[-1],
        "content_id": content_id
    })
    try:
        tree = ElementTree.fromstring(requests.get(url).content)
    except Exception as e:
        print("    error parsing/receiving XML from url {}: {}".format(url, e))
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
            vid_url = media_tag.text.replace('http:', 'https:')
            mp4_size = int(mp4_size_match.group('mp4_size'))
            if mp4_size > largest_mp4_size:
                largest_mp4_size = mp4_size
                largest_mp4_url = vid_url
            if small_mp4_threshold > mp4_size > small_mp4_size:
                small_mp4_size = mp4_size
                small_mp4_url = vid_url

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