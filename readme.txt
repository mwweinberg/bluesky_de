== What this is ==

A bot that translates posts from a Bluesky list of (mostly German) accounts
and reposts them in English to its own account. Rewritten 7/2026 to use the
Bluesky API directly (getAuthorFeed) instead of scraping profile pages for
RSS feeds - that made the old 403-error handling obsolete and fixed the
silent post drops the RSS version suffered from.

Setup: copy example_secrets.py to secrets.py and fill in the Bluesky
credentials plus the Google and Azure translation keys. The list being
watched is set by LIST_OWNER_DID and LIST_RKEY at the top of bluesky_de.py.


== How a post flows through ==

Every 2 minutes (POLL_SECONDS) the bot:
1. re-reads the list membership (accounts can be added/removed on bluesky;
   existing accounts keep their tracking state)
2. pulls each account's recent feed and picks out anything new - its own
   posts AND its reposts of others - oldest first
3. translates the text (see translation section below)
4. posts the translation with the original post embedded as a quote, which
   carries over images, video, link cards, and quoted posts, and doubles
   as the link back to the original

Post formats:
- own post:      authorhandle: translated text
- repost:        reposter ↻ originalauthor: translated text
  (both names linked to their profiles)
- quote post:    the commentary is the main post; the quoted post's text is
                 translated too and posted as a reply underneath, marked ❝
- too long for 300 chars: split into two posts, (1/2) and (2/2)


== Reliability rules ==

- a post only counts as done AFTER it successfully sends; failures are
  retried next cycle (prefers a rare duplicate over a dropped post)
- backlog capped at BACKLOG_CAP (2) posts per account per cycle; older
  extras are skipped with a warning in the log
- state.json (next to the script) remembers the login session and recently
  posted URIs, so restarts don't drop or duplicate posts. It self-prunes
  (SEEN_URIS_KEPT per account) so it stays small
- the saved session avoids bluesky's strict rate limit on password logins
- accounts that can't be read (blocked the bot, deactivated, suspended)
  are skipped with a single warning and picked back up automatically if
  they recover
- if the same post is reposted by several list members, it only goes out once


== Translation and staying in the free tiers ==

- google first, azure as the fallback; source language is auto-detected
  (reposts are not always german)
- posts that declare themselves english (record.langs) skip translation
  entirely, saving quota on both services
- when google reports its daily quota is used up, the bot stops asking it
  until the reset (midnight US pacific) and goes straight to azure
- character counts per service are tallied daily and appended to usage.csv
  (next to the script) for analysis over time; a journal line each day
  shows the month's running totals against the free allowances

The bot itself never enforces billing limits - that lives in the provider
consoles: google's free tier is 500k chars/month, so the daily quota cap in
the cloud console must stay at or below 16,129 (500,000 / 31 days); azure
must be on the F0 tier (2M chars/month, hard-capped, cannot bill). As long
as both are set, running out of quota just means untranslated posts get
retried, never a charge.


== Running it ==

Dependencies: atproto, requests
(feedparser, beautifulsoup4, pytz, python-dateutil no longer needed)

Runs as a systemd service (long-running loop, logs to stdout for journald).
state.json and usage.csv are written next to bluesky_de.py, so under systemd
sandboxing the script directory must be inside ReadWritePaths.

Watch it with:  journalctl -u bluesky -f


== Reference links ==

firehose with filter:
https://launchdarkly.com/blog/bluesky-custom-feed-llm-feature-flag/

change API daily limits:
https://console.cloud.google.com/iam-admin/quotas?service=translate.googleapis.com&inv=1&invt=AblyQA&project=blueskytranslator

maybe relevant to set up translate environment?
https://cloud.google.com/translate/docs/setup
