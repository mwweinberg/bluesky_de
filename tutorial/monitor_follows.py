from atproto import Client
#this is the local secrets file
import secrets

# The username whose followers you want to monitor
my_handle = secrets.user_name

# Your Bluesky API Access Token
my_password = secrets.password


client = Client()
client.login(my_handle, my_password)

print('Home (Following):\n')

# Get "Home" page. Use pagination (cursor + limit) to fetch all posts
timeline = client.get_timeline(algorithm='reverse-chronological')
for feed_view in timeline.feed:
    action = 'New Post'
    if feed_view.reason:
        action_by = feed_view.reason.by.handle
        action = f'Reposted by @{action_by}'

    post = feed_view.post.record
    author = feed_view.post.author

    print(f'[{action}] {author.display_name}: {post.text}')
