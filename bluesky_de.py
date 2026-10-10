"""Translate posts from a Bluesky list of German-language accounts and repost them in English.

The big picture, once per cycle (every POLL_SECONDS):
  1. read the members of the bluesky list (sync_accounts)
  2. for each member, pull their recent feed with getAuthorFeed (process_account)
  3. anything new (posts AND reposts) gets translated - google first, azure as
     the fallback, source language auto-detected
  4. the translation is posted to this account, with the original post embedded
     as a quote so images, video, link cards, and quoted posts all carry over

State (the login session plus recently-posted URIs per account) persists in
state.json next to this file, so a restart neither drops nor duplicates posts.
A post is only marked as done after it successfully sends: if anything fails
mid-process, the post is retried on the next cycle. In other words, when
something goes wrong the bot prefers a rare duplicate over a silent drop.
"""

import json
import logging
import re
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from atproto import Client, client_utils, models
from atproto_client.exceptions import BadRequestError, UnauthorizedError
from zoneinfo import ZoneInfo

#this is the local secrets file
import secrets

#---------------- configuration ----------------

#the language everything gets translated INTO. the source language is
#auto-detected per post, because reposts are not always german
TARGET_LANGUAGE = 'en'

###variables for the list of users you will pull from
#DID is in the middle of the list URL
LIST_OWNER_DID = 'did:plc:ijife7e4twbh2bnrybnsgpwb'
#rkey is at the end of the list url
LIST_RKEY = '3lg424mfsl42l'

#how long to wait between cycles
POLL_SECONDS = 120
#max posts per account per cycle; anything older than that is skipped so an
#outage can't flood the account with a big backlog
BACKLOG_CAP = 2
#how many already-posted URIs to remember per account. this is the rolling
#dedupe window, and it also keeps the state file from growing forever
SEEN_URIS_KEPT = 25
#posts pulled per account per cycle (must be comfortably > BACKLOG_CAP)
FEED_FETCH_LIMIT = 10
#bluesky hard limit on post length
MAX_POST_CHARS = 300
#timeout for the translation API calls so a network hang can't freeze the bot
REQUEST_TIMEOUT = 30
#goes between the reposter and the original author in the header,
#e.g. "zeit.de ↻ tagesschau.de: ..."
REPOST_MARKER = ' ↻ '
#marks the translation of a quoted post, e.g. "❝ tagesschau.de: ..."
#(sent as a reply underneath the main translation)
QUOTE_MARKER = '❝ '

#the state file lives next to this script, wherever the script is
STATE_FILE = Path(__file__).resolve().parent / 'state.json'

#the permanent usage log: one line per (UTC) day gets appended here, so
#translation usage can be analyzed over time. format:
#  date,google_chars,azure_chars,english_skipped_chars
USAGE_FILE = Path(__file__).resolve().parent / 'usage.csv'

#the free monthly character allowances, used only for the daily journal
#line that shows where the month stands (the real enforcement lives in the
#google cloud console quota cap and the azure F0 tier)
GOOGLE_FREE_CHARS_PER_MONTH = 500_000
AZURE_FREE_CHARS_PER_MONTH = 2_000_000

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
#the atproto library logs every HTTP request at INFO, which drowns out the journal
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger('bluesky_de')


#---------------- persistent state ----------------
#state is one dict, saved to state.json, shaped like this:
#{
#  "session": "<the bluesky login session, so restarts don't need a password login>",
#  "accounts": {
#    "did:plc:xyz...": {
#      "handle": "tagesschau.de",
#      "floor": "2026-07-02T12:00:00+00:00",   <- only activity newer than this counts
#      "seen_uris": ["at://.../post/abc", ...] <- recently posted, for dedupe
#    },
#    ...one entry per member of the bluesky list
#  }
#}

def load_state():
    #read state.json if it exists; if it's missing or unreadable, start fresh
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning('could not read state file, starting fresh: %s', e)
    return {'session': None, 'accounts': {}}


def save_state():
    #write-then-rename so a crash mid-write can't corrupt the file
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_FILE)


state = load_state()
#state files from before usage tracking existed need the counters added
state.setdefault('usage', {'date': datetime.now(timezone.utc).date().isoformat(),
                           'google': 0, 'azure': 0, 'skipped': 0})


def add_usage(service, characters):
    #tally translated characters for the current (UTC) day.
    #service is 'google', 'azure', or 'skipped' (already-english posts)
    state['usage'][service] += characters


def month_usage(month):
    #sum the usage.csv rows for one month ('YYYY-MM') so the daily journal
    #line can show where the month stands
    totals = {'google': 0, 'azure': 0, 'skipped': 0}
    if USAGE_FILE.exists():
        for line in USAGE_FILE.read_text().splitlines()[1:]:
            date, google_chars, azure_chars, skipped_chars = line.split(',')
            if date.startswith(month):
                totals['google'] += int(google_chars)
                totals['azure'] += int(azure_chars)
                totals['skipped'] += int(skipped_chars)
    return totals


def roll_usage():
    #called every cycle, but only does something when the (UTC) date has
    #changed: append the finished day's counts to usage.csv, log a summary,
    #and start counting the new day from zero
    usage = state['usage']
    today = datetime.now(timezone.utc).date().isoformat()
    if usage['date'] == today:
        return
    is_new_file = not USAGE_FILE.exists()
    with USAGE_FILE.open('a') as f:
        if is_new_file:
            f.write('date,google_chars,azure_chars,english_skipped_chars\n')
        f.write(f"{usage['date']},{usage['google']},{usage['azure']},{usage['skipped']}\n")
    month = today[:7]
    totals = month_usage(month)
    log.info('usage on %s: google %d, azure %d, skipped %d chars. %s so far: google %d/%d, azure %d/%d',
             usage['date'], usage['google'], usage['azure'], usage['skipped'],
             month, totals['google'], GOOGLE_FREE_CHARS_PER_MONTH,
             totals['azure'], AZURE_FREE_CHARS_PER_MONTH)
    state['usage'] = {'date': today, 'google': 0, 'azure': 0, 'skipped': 0}


def uri_already_posted(uri):
    #global check so the same post reposted by several list members only goes out once
    return any(uri in account['seen_uris'] for account in state['accounts'].values())


def mark_done(account, uri, event_time):
    #record that this post has been handled, so it never gets posted twice.
    #called after a successful send, OR when a post is deliberately skipped
    #by the backlog cap
    account['seen_uris'].append(uri)
    #keep the dedupe window (and the state file) small by dropping the oldest
    del account['seen_uris'][:-SEEN_URIS_KEPT]
    #move the account's floor forward so old posts age out of consideration
    #even after their URIs rotate out of seen_uris
    if event_time > parse_timestamp(account['floor']):
        account['floor'] = event_time.isoformat()


#---------------- bluesky login ----------------

client = Client()


def persist_session(event, session):
    #called automatically by the client whenever the session is created or
    #refreshed, so state.json always holds a session that still works
    state['session'] = session.export()
    save_state()


client.on_session_change(persist_session)


def bsky_login():
    #reusing a saved session avoids bluesky's strict rate limit on password
    #logins (roughly 300 per day - easy to hit if you logged in per post)
    if state.get('session'):
        try:
            client.login(session_string=state['session'])
            log.info('logged in with saved session')
            return
        except Exception as e:
            #the saved session can expire or be revoked; fall through to a
            #normal password login and a fresh session gets saved after it
            log.warning('saved session rejected (%s), doing a fresh login', e)
            state['session'] = None
    client.login(secrets.user_name, secrets.password)
    log.info('logged in with a fresh session')


#---------------- list membership ----------------

def sync_accounts():
    """Fetch list membership and add/remove accounts without touching the state of existing ones."""
    #build the at:// uri of the list, then page through its members
    #(the API returns at most 100 per request, the cursor gets the next page)
    list_uri = f'at://{LIST_OWNER_DID}/app.bsky.graph.list/{LIST_RKEY}'
    members = {}
    cursor = None
    while True:
        response = client.app.bsky.graph.get_list({'list': list_uri, 'limit': 100, 'cursor': cursor})
        for item in response.items:
            members[item.subject.did] = item.subject.handle
        cursor = response.cursor
        if not cursor:
            break

    accounts = state['accounts']
    #anyone on the list who isn't being tracked yet gets added.
    #existing accounts are left alone - this is what makes adding one account
    #to the list NOT reset the tracking state of all the others
    for did, handle in members.items():
        if did not in accounts:
            log.info('list added %s, watching from now on', handle)
            accounts[did] = {
                'handle': handle,
                #only activity newer than this is considered, so adding an
                #account doesn't dump its whole recent history onto the feed
                'floor': utcnow_iso(),
                'seen_uris': [],
            }
        else:
            #handles can change; the DID is the stable identity
            accounts[did]['handle'] = handle
    #anyone tracked who is no longer on the list gets dropped
    for did in list(accounts):
        if did not in members:
            log.info('list removed %s, dropping its state', accounts[did]['handle'])
            del accounts[did]


#---------------- time helpers ----------------

def utcnow_iso():
    #current UTC time as a string like '2026-07-02T12:00:00+00:00'
    #(strings are what goes into state.json, since json has no datetime type)
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(raw):
    #turn a timestamp string back into a datetime object for comparisons.
    #createdAt is set by whatever app made the post, so be tolerant: normalize
    #the Z suffix and trim sub-microsecond digits that fromisoformat rejects
    cleaned = re.sub(r'\.(\d{6})\d+', r'.\1', raw.replace('Z', '+00:00'))
    return datetime.fromisoformat(cleaned)


#---------------- translation ----------------

class TranslationError(Exception):
    #raised only when BOTH translation services fail. the caller treats this
    #as "try again next cycle" rather than posting broken content
    pass


class GoogleQuotaError(Exception):
    #google's daily quota is used up. gets its own class so translate() can
    #pause google until the reset instead of retrying it on every post
    pass


def translate_with_google(text):
    #google translate v2, called with proper URL parameters (the params dict)
    #so characters like &, #, and newlines in the post can't break the request
    response = requests.get(
        'https://translation.googleapis.com/language/translate/v2',
        params={
            'q': text,
            #no 'source': let google detect it, since reposts are not always german
            'target': TARGET_LANGUAGE,
            #plain-text mode: no HTML entities like &#39; in the response
            'format': 'text',
            'key': secrets.translation_api_key,
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = response.json()
    #google puts errors (like a used-up daily quota) in the json instead of
    #the translation - surface that as an exception so azure gets a turn
    if 'data' not in payload:
        message = payload.get('error', {}).get('message', f'HTTP {response.status_code}')
        #quota problems come back as 403/429 - report those separately so
        #google gets paused until the daily reset
        if response.status_code in (403, 429) or 'quota' in message.lower() or 'limit' in message.lower():
            raise GoogleQuotaError(message)
        raise RuntimeError(message)
    return payload['data']['translations'][0]['translatedText']


def translate_with_azure(text):
    #azure translator, same idea as google but the text travels in the json
    #body of a POST instead of the URL
    response = requests.post(
        secrets.azure_endpoint + '/translate',
        #no 'from': azure auto-detects the source language
        params={'api-version': '3.0', 'to': TARGET_LANGUAGE},
        headers={
            'Ocp-Apim-Subscription-Key': secrets.azure_key,
            'Ocp-Apim-Subscription-Region': secrets.azure_location,
            'Content-type': 'application/json',
            'X-ClientTraceId': str(uuid.uuid4()),
        },
        json=[{'text': text}],
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()[0]['translations'][0]['text']


#while google's daily quota is used up, skip it until this time. kept in
#memory only: after a restart the bot tries google once and re-pauses
google_paused_until = None


def next_pacific_midnight():
    #google's daily quota resets at midnight US pacific time
    now_pacific = datetime.now(ZoneInfo('America/Los_Angeles'))
    return (now_pacific + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def translate(text, langs=None):
    #langs is the language declaration from the post record (set by the app
    #the author posted with), like ['de'] or ['en-US']
    global google_paused_until

    #posts that declare themselves english need no translation at all -
    #skipping them costs nothing and saves quota on both services
    if langs and all(lang.split('-')[0].lower() == 'en' for lang in langs):
        add_usage('skipped', len(text))
        log.info('already english, skipped translation')
        return text

    #google first (free tier), unless its daily quota is known to be used up
    if google_paused_until is None or datetime.now(timezone.utc) >= google_paused_until:
        if google_paused_until is not None:
            log.info('google quota should have reset, trying google again')
            google_paused_until = None
        try:
            translated = translate_with_google(text)
            add_usage('google', len(text))
            log.info('translated with google')
            return translated
        except GoogleQuotaError as e:
            #stop asking google until the quota resets, instead of sending a
            #doomed request (and logging a warning) for every post
            google_paused_until = next_pacific_midnight()
            log.warning('google quota exhausted (%s), using azure until %s',
                        e, google_paused_until.strftime('%Y-%m-%d %H:%M %Z'))
        except Exception as e:
            log.warning('google translate failed (%s), trying azure', e)
    try:
        translated = translate_with_azure(text)
        add_usage('azure', len(text))
        log.info('translated with azure')
        return translated
    except Exception as e:
        raise TranslationError(f'both translation services failed: {e}') from e


#---------------- building and sending posts ----------------

#one pattern with three alternatives, used to find the pieces of a post that
#need to become rich-text facets instead of plain text:
#  url      - http(s):// up to the next whitespace
#  mention  - @ followed by a handle like @dwd.bsky.social
#  hashtag  - # followed by a word
TOKEN_RE = re.compile(
    r'(?P<url>https?://\S+)'
    r'|(?P<mention>@\w+(?:\.\w+)*)'
    r'|(?P<hashtag>#\w+)'
)


def extract_components(text):
    """Split text into ('text'|'url'|'mention'|'hashtag', value) pieces."""
    #walks through the text finding urls/mentions/hashtags, and keeps the
    #plain text between them as its own pieces, in order. example:
    #  'Neu: https://taz.de siehe #Wetter'
    #becomes
    #  [('text', 'Neu: '), ('url', 'https://taz.de'), ('text', ' siehe '), ('hashtag', '#Wetter')]
    components = []
    pos = 0
    for match in TOKEN_RE.finditer(text):
        #everything between the previous match and this one is plain text
        if match.start() > pos:
            components.append(('text', text[pos:match.start()]))
        if match.group('url'):
            #trailing sentence punctuation belongs to the text, not the URL
            url = match.group('url').rstrip('.,!?;:')
            components.append(('url', url))
            trailing = match.group('url')[len(url):]
            if trailing:
                components.append(('text', trailing))
        elif match.group('mention'):
            components.append(('mention', match.group('mention')))
        else:
            components.append(('hashtag', match.group('hashtag')))
        pos = match.end()
    #whatever is left after the last match is plain text too
    if pos < len(text):
        components.append(('text', text[pos:]))
    return components


def add_mention(builder, mention_text):
    #a real clickable mention facet needs the DID behind the handle,
    #so ask bluesky to resolve it
    try:
        did = client.resolve_handle(mention_text.lstrip('@')).did
        builder.mention(mention_text, did)
    except Exception:
        #not a resolvable handle (maybe a twitter-style @name), leave it as plain text
        builder.text(mention_text)


def add_components(builder, components):
    #feed the pieces from extract_components into the TextBuilder, which
    #assembles the post text plus the facets (the clickable parts)
    for kind, value in components:
        if kind == 'text':
            builder.text(value)
        elif kind == 'url':
            #show the word 'link' instead of the (long) URL to save characters
            builder.link('link', value)
        elif kind == 'mention':
            add_mention(builder, value)
        elif kind == 'hashtag':
            builder.tag(value, value.lstrip('#'))


def get_profile_url(handle):
    return 'https://bsky.app/profile/' + handle


def split_in_half(text):
    #find a space in the middle and break the text in two, for translations
    #that don't fit in one 300-character post
    words = text.split(' ')
    halfway = round(len(words) / 2)
    return [' '.join(words[:halfway]), ' '.join(words[halfway:])]


def send_parts(header_pieces, text, embed=None, reply_to=None):
    #assembles and sends one finished bluesky post (or two, if the text is
    #too long for one). header_pieces describes the header as a list of
    #('text', value) and ('handle', value) pairs - handles become links to
    #their profiles. examples:
    #  [('handle', 'tagesschau.de')]
    #      -> "tagesschau.de: ..."
    #  [('handle', 'zeit.de'), ('text', ' ↻ '), ('handle', 'tagesschau.de')]
    #      -> "zeit.de ↻ tagesschau.de: ..."
    #returns the API response of the post carrying the embed (the last part),
    #so a reply can be attached underneath it

    header_length = sum(len(value) for kind, value in header_pieces)

    #does everything fit in one post? if not, break the text in half
    if header_length + len(': ') + len(text) <= MAX_POST_CHARS:
        parts = [text]
    else:
        parts = split_in_half(text)

    total = len(parts)
    #split posts go out last part first, so that in the feed (newest on top)
    #the (1/2) post sits above the (2/2) post and reads top to bottom
    for n, part in reversed(list(enumerate(parts, 1))):
        #split posts get a counter in the header: "handle (1/2): ..."
        counter = f' ({n}/{total})' if total > 1 else ''
        header_tail = f'{counter}: '
        #hard ceiling so a send can never fail on length: if a part is still
        #too long, cut it off and end it with an ellipsis
        allowed = MAX_POST_CHARS - header_length - len(header_tail)
        if len(part) > allowed:
            part = part[:allowed - 1] + '…'

        #build the post: the header pieces, the counter, then the text
        #with its facets
        builder = client_utils.TextBuilder()
        for kind, value in header_pieces:
            if kind == 'handle':
                builder.link(value, get_profile_url(value))
            else:
                builder.text(value)
        builder.text(header_tail)
        add_components(builder, extract_components(part))

        #the embed goes on the last part of a split post
        last_embed = embed if n == total else None
        sent = client.send_post(builder, embed=last_embed, reply_to=reply_to)
        if n == total:
            response = sent

    return response


def get_quoted_record(post):
    #if this post quotes another post ('repost with commentary'), dig the
    #quoted post out of the embed view and return it (it carries the quoted
    #text and author). returns None when there is nothing translatable.
    embed = post.embed
    if embed is None:
        return None
    #a quote with media attached wraps the record one level deeper
    if isinstance(embed, models.AppBskyEmbedRecordWithMedia.View):
        embed = embed.record
    if not isinstance(embed, models.AppBskyEmbedRecord.View):
        return None
    record = embed.record
    #the quoted post can be deleted, blocked, or detached - nothing to show then
    if not isinstance(record, models.AppBskyEmbedRecord.ViewRecord):
        return None
    text = getattr(record.value, 'text', '') or ''
    if not text.strip():
        return None
    return record


def send_translated_post(post, translated_text, reposter_handle):
    #sends the translation of one post:
    #  authorhandle: translated text                  <- the account's own post
    #  reposter ↻ authorhandle: translated text       <- repost by a list member
    #with the original post embedded underneath as a quote, and - if the
    #original itself quoted another post - a reply with that translation too.
    #reposter_handle is None for an account's own posts

    #embedding the original as a quote carries over images, video, link
    #cards, and quoted posts, and doubles as the link back to the original
    quote_embed = models.AppBskyEmbedRecord.Main(
        record=models.ComAtprotoRepoStrongRef.Main(uri=post.uri, cid=post.cid)
    )

    #the header identifies who is involved: for a repost, both the list
    #member who reposted it and the original author, linked to their profiles
    if reposter_handle:
        header = [('handle', reposter_handle), ('text', REPOST_MARKER), ('handle', post.author.handle)]
    else:
        header = [('handle', post.author.handle)]
    response = send_parts(header, translated_text, embed=quote_embed)
    log.info('posted translation of %s', post.uri)

    #if the post quoted another post, translate the quoted text as well and
    #hang it underneath the main translation as a reply:
    #  ❝ quotedauthor: translated quoted text
    quoted = get_quoted_record(post)
    if quoted is not None:
        try:
            translated_quote = translate(quoted.value.text, getattr(quoted.value, 'langs', None))
            our_post_ref = models.ComAtprotoRepoStrongRef.Main(uri=response.uri, cid=response.cid)
            reply_ref = models.AppBskyFeedPost.ReplyRef(parent=our_post_ref, root=our_post_ref)
            quote_header = [('text', QUOTE_MARKER), ('handle', quoted.author.handle)]
            send_parts(quote_header, translated_quote, reply_to=reply_ref)
            log.info('added translation of the quoted post by %s', quoted.author.handle)
        except Exception as e:
            #the main post already went out, so failing here must not raise:
            #that would re-send the main post next cycle as a duplicate.
            #the quoted original is still visible in the embed, just untranslated
            log.warning('could not add quoted-post translation under %s: %s', post.uri, e)


#---------------- the per-account check ----------------

#XRPC errors that mean an account can't be read right now (blocked the bot,
#deactivated, suspended...): expected conditions, not bugs worth a traceback
UNREACHABLE_ERRORS = ('BlockedByActor', 'AccountDeactivated', 'AccountTakedown', 'AccountSuspended')


def process_account(did, account):
    #this runs once per account per cycle: fetch their recent feed, figure
    #out what's new, translate and send it, oldest first

    feed = client.get_author_feed(actor=did, filter='posts_no_replies', limit=FEED_FETCH_LIMIT)
    #getting here means the fetch worked - if the account was marked
    #unreachable (see the main loop), it has recovered
    if account.pop('unreachable', None):
        log.info('%s is reachable again', account['handle'])
    floor = parse_timestamp(account['floor'])

    #-------- step 1: decide which feed items are new --------
    new_posts = []
    for item in feed.feed:
        post = item.post
        if item.reason is not None:
            #a reason means the list member reposted someone else's post;
            #the relevant time is when they reposted it, not when it was written
            raw_time = getattr(item.reason, 'indexed_at', None)
            if raw_time is None:
                #a reason without a timestamp is something else (like a pin) - skip it
                continue
            is_repost = True
        else:
            #no reason = the account's own post. defensive check that the
            #author really is the account we asked about
            if post.author.did != did:
                continue
            raw_time = post.record.created_at
            is_repost = False
        try:
            event_time = parse_timestamp(raw_time)
        except ValueError:
            log.warning('unparseable timestamp %r on %s, skipping', raw_time, post.uri)
            continue
        #skip anything older than the account's floor, and anything any list
        #member already got posted (dedupe)
        if event_time <= floor or uri_already_posted(post.uri):
            continue
        new_posts.append((event_time, post, is_repost))

    if not new_posts:
        return

    #-------- step 2: oldest first, and apply the backlog cap --------
    #oldest first, so translations appear in the order they were posted
    new_posts.sort(key=lambda entry: entry[0])

    if len(new_posts) > BACKLOG_CAP:
        #too many piled up (probably downtime) - mark the oldest ones as done
        #WITHOUT sending them, so the account doesn't get flooded
        skipped = new_posts[:-BACKLOG_CAP]
        log.warning('%s has %d new posts, skipping the oldest %d (backlog cap)',
                    account['handle'], len(new_posts), len(skipped))
        for event_time, post, is_repost in skipped:
            mark_done(account, post.uri, event_time)
        new_posts = new_posts[-BACKLOG_CAP:]

    #-------- step 3: translate and send --------
    for event_time, post, is_repost in new_posts:
        log.info('new %s by %s: %s', 'repost' if is_repost else 'post', account['handle'], post.uri)
        if post.record.text.strip():
            #a TranslationError here aborts the account for this cycle;
            #the post is not marked done, so it will be retried
            translated = translate(post.record.text, post.record.langs)
        else:
            #media-only post: nothing to translate, the quote embed carries the content
            translated = ''
        #for a repost, the list member (whose feed this is) is the reposter
        send_translated_post(post, translated, account['handle'] if is_repost else None)
        #only AFTER the send succeeded does the post count as done - and the
        #state file is saved right away, so even a crash one second later
        #can't cause a re-post
        mark_done(account, post.uri, event_time)
        save_state()


#---------------- main loop ----------------

def main():
    bsky_login()
    log.info('watching list %s with a %ds poll', LIST_RKEY, POLL_SECONDS)
    while True:
        #when a new (UTC) day has started, write yesterday's translation
        #counts to usage.csv and log the month's running totals
        roll_usage()

        #refresh the list membership first, in case accounts were added/removed
        try:
            sync_accounts()
        except Exception as e:
            log.error('could not sync list membership: %s', e)

        #check every account. each one gets its own try/except so one broken
        #account can't stop the others from being checked
        for did, account in list(state['accounts'].items()):
            try:
                process_account(did, account)
            except UnauthorizedError:
                #the login session died mid-cycle - get a new one and move on
                log.warning('session expired, logging in again')
                state['session'] = None
                bsky_login()
            except BadRequestError as e:
                error_name = getattr(e.response.content, 'error', '')
                if error_name in UNREACHABLE_ERRORS:
                    #warn once, then stay quiet until the account recovers
                    if not account.get('unreachable'):
                        log.warning('cannot read %s (%s), skipping until it recovers',
                                    account['handle'], error_name)
                        account['unreachable'] = True
                else:
                    log.error('error processing %s: %s\n%s', account['handle'], e, traceback.format_exc())
            except TranslationError as e:
                #both translators failed - the post was NOT marked done, so
                #it gets picked up again next cycle
                log.error('translation failed for %s, will retry next cycle: %s', account['handle'], e)
            except Exception as e:
                log.error('error processing %s: %s\n%s', account['handle'], e, traceback.format_exc())

        save_state()
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()
