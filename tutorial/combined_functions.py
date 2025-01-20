import requests 
from bs4 import BeautifulSoup
import feedparser
import json
from atproto import Client, client_utils
import re 
from datetime import datetime
import pytz
import time

#this is the local secrets file
import secrets

#translation variables
language_to_translate_to = 'de'
translation_api_key = secrets.translation_api_key

#bluesky credentials
#create the object
client = Client()
#credential variables are used below
user_name = secrets.user_name
password = secrets.password

#this is just for the initial testin/building and should be deleted once the class objects work 
target_username = 'michaelweinberg.org'

# this will eventually be the list of accounts you want to follow
users_list = ['bbcnews-uk-rss.bsky.social', 'newsycombinator.bsky.social', 'apnews.com', 'cnn.com']

####GET THE RSS LINK########

def get_rss_link_from_username(username):
    #construct the profile page url
    #target_profile_url = 'https://bsky.app/profile/' + username
    target_profile_url = get_target_profile_url(username)

    #get the profile page
    target_profile_page_content = requests.get(target_profile_url)

    #parse the contents of the profile page
    soup = BeautifulSoup(target_profile_page_content.text, 'html.parser')

    #find the relevant link in the profile page contents
    target_rss_url_full = soup.find('link', rel='alternate', type='application/rss+xml')

    #strip out the html around the url itself
    target_rss_url = target_rss_url_full['href']
    return(target_rss_url)

def get_target_profile_url(username):
    output = 'https://bsky.app/profile/' + username
    return(output)

def get_DID_from_target_rss_url(url):
    target_DID_almost = url.replace("https://bsky.app/profile/", "")
    target_DID = target_DID_almost.replace("/rss", "")
    return(target_DID)


target_rss_url = get_rss_link_from_username(target_username)
target_DID = get_DID_from_target_rss_url(target_rss_url)

####CREATE THE USER OBJECTS##############   

# list to hold all of the Users objects you create
user_holder = []

#defines User class
class User:
    def __init__(self, user_name, last_post_time, rss_url, target_profile_url, DID):
        self.user_name = user_name
        self.last_post_time = last_post_time
        self.rss_url = rss_url
        self.target_profile_url = target_profile_url
        self.DID = DID


#populates the user_holder, setting last_post_time as the moment you started the script
for i in users_list:
    #last_post_time = datetime.now()
    last_post_time = datetime.now(pytz.UTC)
    rss_url = get_rss_link_from_username(i)
    target_profile_url = get_target_profile_url(i)
    user_DID = get_DID_from_target_rss_url(rss_url)

    user_holder.append(User(i, last_post_time, rss_url, target_profile_url, user_DID))

#just to verify that the Users were created
# for i in user_holder:
#     print(i.user_name)
#     print(i.last_post_time)
#     print(i.rss_url)
#     print(i.target_profile_url)
#     print(i.DID)


######GET THE FEED CONTENT, TRANSLATE, AND SEND#########

def translate_tweet_text(tweet_text):
    #build the translation url
    translation_payload_url = 'https://translation.googleapis.com/language/translate/v2?q=' + tweet_text + '&target=' + language_to_translate_to + '&key=' + translation_api_key

    #get the translation response from google
    translation_payload = requests.get(translation_payload_url)

    #parse the json
    translation_payload_text_json = json.loads(translation_payload.text)

    #pull out the translated text string
    translated_text = translation_payload_text_json['data']['translations'][0]['translatedText']

    return(translated_text)

def send_tweet(tweeter_username, translated_tweet_text):

    #function to break up the contents of the tweet
    def extract_components(input_string):
        # Define regex patterns for URL and @mention
        #this is the chatGPT one that did not work
        #url_pattern = r'https?://[^\s]+(?:[^\w\s]|$)'  # Match URL, but stop before punctuation like ".", ",", etc.
        #this is the stack overflow one that did
        url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'
        mention_pattern = r'@\w+(\.\w+)*'
        
        
        # Initialize the list to store the components
        tweet_components = []
        
        # Current position in the string
        pos = 0
        
        while pos < len(input_string):
            # Find the next URL or mention
            url_match = re.search(url_pattern, input_string[pos:])
            mention_match = re.search(mention_pattern, input_string[pos:])
            
            # If we found both a URL and a mention, choose the one that comes first
            if url_match and mention_match:
                if url_match.start() < mention_match.start():
                    match = url_match
                else:
                    match = mention_match
            elif url_match:
                match = url_match
            elif mention_match:
                match = mention_match
            else:
                # If no match is found, the rest is text
                tweet_components.append({'text': input_string[pos:]})
                break
            
            # Extract the text before the match
            before_match = input_string[pos:pos + match.start()]
            if before_match:
                tweet_components.append({'text': before_match})
            
            # Extract the URL or mention
            if match == url_match:
                # Extract the clean URL (without trailing punctuation)
                url = match.group(0)
                tweet_components.append({'url': url})
                
                # Check if there's punctuation following the URL (e.g., a period or comma)
                next_char = input_string[pos + match.end():pos + match.end() + 1]
                if next_char in '.!?,':
                    # If punctuation follows, treat it as part of the next text and add it
                    tweet_components.append({'text': next_char})
                    pos += 1  # Move past the punctuation
            elif match == mention_match:
                tweet_components.append({'mention': match.group(0)})
            
            # Move position forward by the length of the matched part
            pos += match.end()
        
        return tweet_components

    #run the function to get the tweet components
    tweet_components = extract_components(translated_tweet_text)
    print('components extracted')

    #create the object that you will fill with the contents of the tweet
    text_builder = client_utils.TextBuilder()

    #create the start of the tweet identifying the tweeter
    text_builder.link(tweeter_username, get_target_profile_url(tweeter_username))
    text_builder.text(': ')
    print('tweet header built')

    #build the body of the tweets from the components
    for i in tweet_components:
        for key, value in i.items():
            if key == 'text':
                text_builder.text(value)
            elif key == 'mention':
                handle = value.replace("@","")
                text_builder.tag(value, handle)
            elif key == 'url':
                #print(value)
                text_builder.link(value, value)
            else:
                print("error building rich tweet: " + key + " " + value)
    #this is new
    text_builder.link(' Orig.', target_feed.entries[0].link)
    print('tweet body built')

    #send tweet
    post = client.send_post(text_builder)
    print('tweet sent')


#loop_counter is just for testing and can be deleted
loop_counter = 0
change_counter = 0
while True:
    for i in user_holder:
        #get the feed url
        target_feed = feedparser.parse(i.rss_url)
        #load last_post_time from the object
        last_post_time = i.last_post_time
        #load time_of_last_tweet from the first object in the RSS feed
        time_of_last_tweet = target_feed.entries[0].published
        #converted from string to datetime object
        time_of_last_tweet_dt = datetime.strptime(time_of_last_tweet, "%d %b %Y %H:%M %z")

        #see if the latest tweet is newer than last_post_time
        if time_of_last_tweet_dt > last_post_time:
            print(f'New post by {i.user_name} is NEW')
            print(time_of_last_tweet_dt)
            print(last_post_time)
            time_diff = time_of_last_tweet_dt - last_post_time
            minutes_diff = time_diff.total_seconds() / 60
            print(f'time between times is {minutes_diff}')
            #if it is, update the last post time (you'll also trigger a bunch of other stuff)

            #This is the stuff
            
            #send the text of the new tweet to be translated
            translated_tweet_text = translate_tweet_text(target_feed.entries[0].summary)

            #build the tweet
            #BUT add a link to the tweet builder at the end that links to the original text (you've added but not tested this below)
            #   text_builder.link(' Orig.', target_feed.entries[0].link)

            #login to bluesky
            client.login(user_name, password)

            #send the tweet
            send_tweet(i.user_name, translated_tweet_text)


            #reset things
            i.last_post_time = time_of_last_tweet_dt
            print('updated last_post_time!')
            change_counter += 1

        else:
            print(f'New post by {i.user_name} is OLD')
            print(f'last_post_time is {last_post_time}')
            print(f'time_of_last_tweet_dt is {time_of_last_tweet_dt}')
        
        print('********')
    loop_counter += 1
    print('+++++++++')
    print(f'loop_counter is now {loop_counter}')
    print(f'change_counter is now {change_counter}')
    print('+++++++++')
    time.sleep(120)



#use the rss url to get the rss feed
target_feed = feedparser.parse(target_rss_url)

target_tweet_link = target_feed.entries[0].link
target_tweet_text = target_feed.entries[0].summary
target_tweet_time = target_feed.entries[0].published

###############SEND THE FEED.SUMMARY TO GET TRANSLATED#######


# def translate_tweet_text(tweet_text):
#     #build the translation url
#     translation_payload_url = 'https://translation.googleapis.com/language/translate/v2?q=' + tweet_text + '&target=' + language_to_translate_to + '&key=' + translation_api_key

#     #get the translation response from google
#     translation_payload = requests.get(translation_payload_url)

#     #parse the json
#     translation_payload_text_json = json.loads(translation_payload.text)

#     #pull out the translated text string
#     translated_text = translation_payload_text_json['data']['translations'][0]['translatedText']

#     return(translated_text)

#translated_tweet_text = translate_tweet_text(target_tweet_text)



######RE-BUILD THE TWEET WITH THE TRANSLATED CONTENT########

#log in to bluesky
# client = Client()
# user_name = secrets.user_name
# password = secrets.password
# client.login(user_name, password)


# def send_tweet(tweeter_username, translated_tweet_text):

#     #function to break up the contents of the tweet
#     def extract_components(input_string):
#         # Define regex patterns for URL and @mention
#         #this is the chatGPT one that did not work
#         #url_pattern = r'https?://[^\s]+(?:[^\w\s]|$)'  # Match URL, but stop before punctuation like ".", ",", etc.
#         #this is the stack overflow one that did
#         url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'
#         mention_pattern = r'@\w+(\.\w+)*'
        
        
#         # Initialize the list to store the components
#         tweet_components = []
        
#         # Current position in the string
#         pos = 0
        
#         while pos < len(input_string):
#             # Find the next URL or mention
#             url_match = re.search(url_pattern, input_string[pos:])
#             mention_match = re.search(mention_pattern, input_string[pos:])
            
#             # If we found both a URL and a mention, choose the one that comes first
#             if url_match and mention_match:
#                 if url_match.start() < mention_match.start():
#                     match = url_match
#                 else:
#                     match = mention_match
#             elif url_match:
#                 match = url_match
#             elif mention_match:
#                 match = mention_match
#             else:
#                 # If no match is found, the rest is text
#                 tweet_components.append({'text': input_string[pos:]})
#                 break
            
#             # Extract the text before the match
#             before_match = input_string[pos:pos + match.start()]
#             if before_match:
#                 tweet_components.append({'text': before_match})
            
#             # Extract the URL or mention
#             if match == url_match:
#                 # Extract the clean URL (without trailing punctuation)
#                 url = match.group(0)
#                 tweet_components.append({'url': url})
                
#                 # Check if there's punctuation following the URL (e.g., a period or comma)
#                 next_char = input_string[pos + match.end():pos + match.end() + 1]
#                 if next_char in '.!?,':
#                     # If punctuation follows, treat it as part of the next text and add it
#                     tweet_components.append({'text': next_char})
#                     pos += 1  # Move past the punctuation
#             elif match == mention_match:
#                 tweet_components.append({'mention': match.group(0)})
            
#             # Move position forward by the length of the matched part
#             pos += match.end()
        
#         return tweet_components

#     #run the function to get the tweet components
#     tweet_components = extract_components(translated_tweet_text)
#     print('components extracted')

#     #create the object that you will fill with the contents of the tweet
#     text_builder = client_utils.TextBuilder()

#     #create the start of the tweet identifying the tweeter
#     text_builder.link(tweeter_username, get_target_profile_url(tweeter_username))
#     text_builder.text(': ')
#     print('tweet header built')

#     #build the body of the tweets from the components
#     for i in tweet_components:
#         for key, value in i.items():
#             if key == 'text':
#                 text_builder.text(value)
#             elif key == 'mention':
#                 handle = value.replace("@","")
#                 text_builder.tag(value, handle)
#             elif key == 'url':
#                 #print(value)
#                 text_builder.link(value, value)
#             else:
#                 print("error building rich tweet: " + key + " " + value)
#     #this is new
#     text_builder.link(' Orig.', target_feed.entries[0].link)
#     print('tweet body built')

#     #send tweet
#     post = client.send_post(text_builder)
#     print('tweet sent')

#send_tweet(target_username, translated_tweet_text)
