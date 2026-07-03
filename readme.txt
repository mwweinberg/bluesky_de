== Current architecture (rewritten 7/2026) ==

The script polls the Bluesky API directly (getAuthorFeed) instead of scraping
profile pages for RSS feeds. That made the old 403-error handling obsolete:
there are no RSS feeds anymore, so no accounts get skipped for feed problems.

Key behaviors:
- checks every account on the list every 2 minutes (POLL_SECONDS)
- processes ALL new posts per account, oldest first, not just the newest one
- includes reposts, shown as "reposter ↻ originalauthor: ..." with both
  names linked to their profiles
- every translation embeds the original post as a quote, which carries over
  images, video, link cards, and quoted posts (and links back to the original)
- if a post quotes another post ("repost with commentary"), the quoted post's
  text is translated too and posted as a reply underneath, marked with ❝
- translation: google first (free tier), azure fallback, source language
  auto-detected (reposts are not always german)
- a post only counts as done AFTER it successfully sends; failures are
  retried next cycle (prefers a rare duplicate over a dropped post)
- backlog capped at BACKLOG_CAP (2) posts per account per cycle; older
  extras are skipped with a warning in the log
- state.json (next to the script) remembers the login session and recently
  posted URIs, so restarts don't drop or duplicate posts. It self-prunes
  (SEEN_URIS_KEPT per account) so it stays small.
- the saved session avoids bluesky's strict rate limit on password logins

Dependencies are now just: atproto, requests
(feedparser, beautifulsoup4, pytz, python-dateutil no longer needed)

Deployment note: state.json is written next to bluesky_de.py, so under
systemd sandboxing the script directory must be inside ReadWritePaths
(it is: ReadWritePaths=/srv/bluesky-de covers bin/).


== Reference links ==

firehose with filter:
https://launchdarkly.com/blog/bluesky-custom-feed-llm-feature-flag/

change API daily limits:
https://console.cloud.google.com/iam-admin/quotas?service=translate.googleapis.com&inv=1&invt=AblyQA&project=blueskytranslator

maybe relevant to set up translate environment?
https://cloud.google.com/translate/docs/setup
