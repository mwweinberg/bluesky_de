import requests 
from bs4 import BeautifulSoup
import feedparser
import json
from atproto import Client, client_utils
import re 
from datetime import datetime
import pytz
import time
import traceback
import uuid

#this is the local secrets file
import secrets

#translation variables
language_to_translate_to = 'en'
translation_api_key = secrets.translation_api_key

#bluesky credentials
#create the object
client = Client()
#credential variables are used below
user_name = secrets.user_name
password = secrets.password

###variables for the list of users you will pull from 
#DID is in the middle of the list URL
list_owner_DID = 'ijife7e4twbh2bnrybnsgpwb'
#rkey is at the end of the list url
list_rkey = '3lg424mfsl42l'


#######AZURE TRANSLATE SETUP STUFF######

azure_key = secrets.azure_key
azure_endpoint = secrets.azure_endpoint

azure_path = '/translate'
azure_constructed_url = azure_endpoint + azure_path

azure_params = {
    'api-version': '3.0',
    'from': 'de',
    'to': 'en'
}

azure_headers = {
    'Ocp-Apim-Subscription-Key': azure_key,
    'Ocp-Apim-Subscription-Region': secrets.azure_location,
    'Content-type': 'application/json',
    'X-ClientTraceId': str(uuid.uuid4())
}

########################################



#######GET ALL OF THE USERS###########

#(python) list to hold the users from the (bluesky) list
users_list = []
number_of_accounts = 0


def get_usernames():
    global number_of_accounts
    #build the list url
    list_url = 'at://did:plc:' + list_owner_DID + '/app.bsky.graph.list/' + list_rkey
    #build the query url, which includes the list URL
    full_api_request_url = 'https://public.api.bsky.app/xrpc/app.bsky.graph.getList?list=' + list_url

    #print(full_api_request_url)

    #get the json about the list
    list_payload = requests.get(full_api_request_url)

    #parse the json 
    list_json = json.loads(list_payload.text)

    if len(list_json['items']) != number_of_accounts:
        #reset users_list
        global users_list 
        users_list = []
        print('*new accounts in the list - rebuilding*')
        #grab all of the usernames and put them in users_list
        for i in list_json['items']:
            print(f"getting {i['subject']['handle']}")
            users_list.append(i['subject']['handle'])
        #create the objects
        populate_user_holder()
        #update number_of_accounts
        number_of_accounts = len(list_json['items'])
    else:
        print("no new accounts in list")



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
    try:
        target_rss_url = target_rss_url_full['href']
    #for unknown reasons, some pages do not have the rss feed
    #this exception throws an error that is then used to skip creating the object in the populate_user_holder() function
    except:
        target_rss_url = 'error'
        print("error getting rss from url")
    return(target_rss_url)

def get_target_profile_url(username):
    output = 'https://bsky.app/profile/' + username
    return(output)

def get_DID_from_target_rss_url(url):
    target_DID_almost = url.replace("https://bsky.app/profile/", "")
    target_DID = target_DID_almost.replace("/rss", "")
    return(target_DID)


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
def populate_user_holder():
    #reset the holder every time you run this so you don't get doubles
    global user_holder
    user_holder = []
    for i in users_list:
        #last_post_time = datetime.now()
        last_post_time = datetime.now(pytz.UTC)

        rss_url = get_rss_link_from_username(i)
        target_profile_url = get_target_profile_url(i)
        user_DID = get_DID_from_target_rss_url(rss_url)

        #some pages don't have RSS links (don't know why). If that's the case, get_rss_link_from_username() will return 'error' as the rss_url. This if/else statement uses that error message to skip creating an object for that account
        if rss_url == 'error':
            print("did not create object for " +i)
        else:

            user_holder.append(User(i, last_post_time, rss_url, target_profile_url, user_DID))
            #this is just a better way to confirm things are working at startup
            print(f'created object for {i}')

get_usernames()
#populate_user_holder()

######GET THE FEED CONTENT, TRANSLATE, AND SEND#########

def translate_tweet_text(tweet_text):

    #sending hashtags to google translate via the url throws an error, so clean them out (you can replace it below)
    cleaned_tweet_text = tweet_text.replace('#','-h-')

    #build the translation url
    translation_payload_url = 'https://translation.googleapis.com/language/translate/v2?q=' + cleaned_tweet_text + '&target=' + language_to_translate_to + '&key=' + translation_api_key

    print(f'translation_payload_url = {translation_payload_url}')

    #get the translation response from google
    translation_payload = requests.get(translation_payload_url)

    #parse the json
    translation_payload_text_json = json.loads(translation_payload.text)

    #pull out the translated text string
    try:
        translated_text = translation_payload_text_json['data']['translations'][0]['translatedText']
        #re-insert the hashtag
        #uncleaned_translated_text = translated_text.replace('-h-', "#")
        #'uncleaned' in the sense that you cleaned it to send to translation, and you are undoing that process here. So 'uncleaned' not 'unclean'
        uncleaned_translated_text = (
            translated_text
                .replace('-h-', '#')
                .replace('&#39;', "'")
                .replace('&quot;', '"')
        )
        print('translated with google')
    except:
        try:
            def azure_translate(input_text):
                #empty json to hold the text to be translated
                body = [{}]
                #put the input text in the json
                body[0]['text'] = input_text
                #send the payload to be translated
                request = requests.post(azure_constructed_url, params=azure_params, headers=azure_headers, json=body)
                #get the response
                response = request.json()
                #parse the response
                translated_text = response[0]['translations'][0]['text']
                #return the response
                return(translated_text)
            #run the function to get the translated text from azure
            translated_text = azure_translate(cleaned_tweet_text)
            #'un'clean it by fixing the characters 
            uncleaned_translated_text = (
                translated_text
                    .replace('-h-', '#')
                    .replace('&#39;', "'")
                    .replace('&quot;', '"')
            )
            print('translated with azure')

        
        
        except:
            print(f'problem with translating text from {translation_payload_text_json}')
            # error_post_text = "error: problem translating text"
            # client.login(user_name, password)
            # post = client.send_post(error_post_text)
            uncleaned_translated_text = 'translation error'


    return(uncleaned_translated_text)

def send_tweet(tweeter_username, translated_tweet_text):

    #function to break up the contents of the tweet
    def extract_components(input_string):
        # Define regex patterns for URL and @mention
        #this is the chatGPT one that did not work
        #url_pattern = r'https?://[^\s]+(?:[^\w\s]|$)'  # Match URL, but stop before punctuation like ".", ",", etc.
        #this is the stack overflow one that did
        #url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'
        url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-!])'

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
    ###YOU REPLACED 'text_builder' with 'target_text_builder'
    def build_the_tweet(parsed_tweet, target_text_builder):
        for i in parsed_tweet:
        #for i in tweet_components:
            for key, value in i.items():
                if key == 'text':
                    target_text_builder.text(value)
                elif key == 'mention':
                    handle = value.replace("@","")
                    target_text_builder.tag(value, handle)
                elif key == 'url':
                    #print(value)
                    #target_text_builder.link(value, value)
                    target_text_builder.link('link', value)
                else:
                    print("error building rich tweet: " + key + " " + value)
  
    #build_the_tweet(tweet_components)
    build_the_tweet(tweet_components, text_builder)
    #this is new
    text_builder.link(' Orig.', target_feed.entries[0].link)
    print('tweet body built')

    #send tweet
    try:
        post = client.send_post(text_builder)
        print('tweet sent')
    except: 
        
        
        try:
            #create text_builder first half
            text_builder_first_half = client_utils.TextBuilder()#create the start of the tweet identifying the tweeter
            text_builder_first_half.link(tweeter_username, get_target_profile_url(tweeter_username))
            text_builder_first_half.text(' (1/2): ')
            #create text_builder second half
            text_builder_second_half = client_utils.TextBuilder()
            text_builder_second_half.link(tweeter_username, get_target_profile_url(tweeter_username))
            text_builder_second_half.text(' (2/2): ')
            text_builder_second_half.link(' Orig.', target_feed.entries[0].link)
            print('*text_builder first and second half exist')
            #cut translated_tweet_text in half
            #take a tweet, find a space in the middle, and break it in two
            def one_tweet_to_two_tweets(original_tweet_text):
                print(f'**original_tweet_text is: {original_tweet_text}')
                #you are looking for spaces
                split_char = ' '
                #count how many spaces there are
                space_count = original_tweet_text.count(split_char)
                #pick a space in the middle
                halfway = round(space_count/2)
                #break the tweet up into a bunch of pieces that do not include the spaces
                all_of_the_pieces_holder = original_tweet_text.split(split_char)
                #create a list of the two halves by putting the pieces from one into one bucket, and the rest into the other
                split_string_list = split_char.join(all_of_the_pieces_holder[:halfway]), split_char.join(all_of_the_pieces_holder[halfway:])

                return split_string_list
            split_tweets = one_tweet_to_two_tweets(translated_tweet_text)
            print('-long tweet split')
            tweet_first_half = split_tweets[0]
            tweet_second_half = split_tweets[1]
            tweet_first_half_components = extract_components(tweet_first_half)
            tweet_second_half_components = extract_components(tweet_second_half)
            print('-halves broken up in to parts')
            build_the_tweet(tweet_first_half_components, text_builder_first_half)
            build_the_tweet(tweet_second_half_components, text_builder_second_half)
            print('-split tweets built')
            post_first_half = client.send_post(text_builder_first_half)
            post_second_half = client.send_post(text_builder_second_half)
            print('-tweeted split tweet!')
            

        except Exception as e:
            print(e)
            print('~~~~~~~~~~~~~~~~~~~~~~~')
            print(traceback.format_exc())
            print(f'error in sending. translated tweet text is from {tweeter_username} and translated tweet text is: {translated_tweet_text}')


            ##first_half_of_tweet_components = extract_components(first_half_of_translated_tweet_tet
            ##build_the_tweet(first_half_of_tweet_components)

        
            error_post_text = "error: tried to send a long post from: " + tweeter_username
            post = client.send_post(error_post_text)
        


#loop_counter is just for testing and can be deleted
loop_counter = 0
change_counter = 0


while True:
    for i in user_holder:
        #IF YOU ARE STILL GETTING ERRORS, TRY 'IF FEED PARSER FAILS, REMOVE ACCOUNT FROM OBJECT LIST'?
        #get the feed url
        target_feed = feedparser.parse(i.rss_url)
        #load last_post_time from the object
        last_post_time = i.last_post_time
        #load time_of_last_tweet from the first object in the RSS feed
        try:
            time_of_last_tweet = target_feed.entries[0].published
            #converted from string to datetime object
            time_of_last_tweet_dt = datetime.strptime(time_of_last_tweet, "%d %b %Y %H:%M %z")
        except:
            print(f'error with time of last tweet from {target_feed}')
            time_of_last_tweet_dt = datetime.now(pytz.UTC)

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
            try:
                translated_tweet_text = translate_tweet_text(target_feed.entries[0].summary)
            except:
                #translate_tweet_text = "error translating tweet"
                translated_tweet_text = "error translating tweet"

            #build the tweet

            try:
                #login to bluesky
                client.login(user_name, password)

                #send the tweet
                send_tweet(i.user_name, translated_tweet_text)


                #reset things
                i.last_post_time = time_of_last_tweet_dt
                print('updated last_post_time!')
                change_counter += 1
            except Exception as e:
                print('problem logging in to bluesky')
                print(e)
                change_counter += 1

        else:
            #print(f'New post by {i.user_name} is OLD')
            #print(f'last_post_time is {last_post_time}')
            #print(f'time_of_last_tweet_dt is {time_of_last_tweet_dt}')
            pass


        
    loop_counter += 1
    print('+++++++++')
    print(f'loop_counter is now {loop_counter}')
    print(f'change_counter is now {change_counter}')
    print('+++++++++')
    #check to see if the list has changed
    get_usernames()
    time.sleep(120)

