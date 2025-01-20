import requests 
from bs4 import BeautifulSoup
import feedparser
import json
from atproto import Client, client_utils
import re 

#this is the local secrets file
import secrets

#translation variables
language_to_translate_to = 'de'
translation_api_key = secrets.translation_api_key

####GET THE RSS LINK########

#username being targeted
target_username = 'michaelweinberg.org'

#construct the profile page url
target_profile_url = 'https://bsky.app/profile/' + target_username

#get the profile page
target_profile_page_content = requests.get(target_profile_url)

#parse the contents of the profile page
soup = BeautifulSoup(target_profile_page_content.text, 'html.parser')

#find the relevant link in the profile page contents
target_rss_url_full = soup.find('link', rel='alternate', type='application/rss+xml')

#strip out the html around the url itself
target_rss_url = target_rss_url_full['href']
print('target_rss_url = ' + target_rss_url)

# to get the DID, strip out the rest of the URL (probably a better way to do this...)
target_DID_almost = target_rss_url.replace("https://bsky.app/profile/", "")
target_DID = target_DID_almost.replace("/rss", "")
print(target_DID)



######GET THE FEED CONTENT#########

#use the rss url to get the rss feed
target_feed = feedparser.parse(target_rss_url)

#get the most recent entry
#author of the tweet
print(target_username)
#link to the tweet
print(target_feed.entries[0].link)
#tweet text
print(target_feed.entries[0].summary)
#tweet post time
print(target_feed.entries[0].published)

target_tweet_link = target_feed.entries[0].link
target_tweet_text = target_feed.entries[0].summary

###############SEND THE FEED.SUMMARY TO GET TRANSLATED#######
#https://codelabs.developers.google.com/codelabs/cloud-translation-python3#0


#build the translation url
translation_payload_url = 'https://translation.googleapis.com/language/translate/v2?q=' + target_tweet_text + '&target=' + language_to_translate_to + '&key=' + translation_api_key

#get the translation response from google
translation_payload = requests.get(translation_payload_url)

#parse the json
translation_payload_text_json = json.loads(translation_payload.text)

#pull out the translated text string
translated_text = translation_payload_text_json['data']['translations'][0]['translatedText']

#print(translated_text)



######RE-BUILD THE TWEET WITH THE TRANSLATED CONTENT########

#log in to bluesky
client = Client()
user_name = secrets.user_name
password = secrets.password
client.login(user_name, password)

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
tweet_components = extract_components(translated_text)

#create the object that you will fill with the contents of the tweet
text_builder = client_utils.TextBuilder()

#create the start of the tweet identifying the tweeter
text_builder.link(target_username, target_profile_url)
text_builder.text(': ')

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

#send tweet
post = client.send_post(text_builder)