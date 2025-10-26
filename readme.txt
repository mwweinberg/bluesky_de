there were problems with some of the account rss feeds thowing 403 errors.  In 10/25 you addressed this by not creating objects for those accounts (search for `elif feedparser.parse(rss_url).status == 403:`).  You don't know why some accounts do not have working RSS feeds, or if those problems change over time.  If you start getting new problems, it might be worth building in a check during each loop to see if a new RSS 403 error is popping up. 


firehose with filter:
https://launchdarkly.com/blog/bluesky-custom-feed-llm-feature-flag/


change API daily limits:

https://console.cloud.google.com/iam-admin/quotas?service=translate.googleapis.com&inv=1&invt=AblyQA&project=blueskytranslator

maybe relevant to set up translate environment?
https://cloud.google.com/translate/docs/setup





