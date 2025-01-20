from datetime import datetime

# this will eventually be the list of accounts you want to follow
users_list = ['bbcnews-uk-rss.bsky.social', 'newsycombinator.bsky.social', 'apnews.com', 'cnn.com']

# list to hold all of the Users objects you create
user_holder = []

#defines User class
class User:
    def __init__(self, user_name, last_post_time):
        self.user_name = user_name
        self.last_post_time = last_post_time
        self.rss_url = None

#populates the user_holder
for i in users_list:
    last_post_time = datetime.now()
    user_holder.append(User(i, last_post_time))

#just a way to verify that it worked
for i in user_holder:
    print(i.user_name)
    print(i.last_post_time)