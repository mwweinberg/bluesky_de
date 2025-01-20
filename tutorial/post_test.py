from atproto import Client, client_utils
import re 
#this is the local secrets file
import secrets

client = Client()

user_name = secrets.user_name
password = secrets.password

client.login(user_name, password)

#client.send_post(text='Hello World2!')

target_username = 'michaelweinberg.org'
target_profile_url = 'https://bsky.app/profile/' + target_username
target_DID = 'did:plc:mm6nvvtqh2dqq7bd5q62nwxq'
target_tweet_link = 'https://bsky.app/profile/michaelweinberg.org/post/3leonr57gos2i'
target_tweet_text = 'First day of 2025 in Berlin, with opinions. https://michaelweinberg.org/blog/2024/11/21/what-does-company-owe-oshw/. What next? @michael.org https://www.nytimes.com/2025/01/03/health/alcohol-surgeon-general-warning.html, more text. @mention followed by more text.' 


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
tweet_components = extract_components(target_tweet_text)

#tweet_components = extract_components(target_tweet_text)


text_builder = client_utils.TextBuilder()
# for i in tweet_components:
#     #print(next(iter(i)))
#     for key, value in i.items():
#         print(key)
#         print(value)

#create the start of the tweet identifying the tweeter
text_builder.link(target_username, target_profile_url)
text_builder.text(': ')

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

print(text_builder)


###################

#text = client_utils.TextBuilder().text('Hello World from ').link('Python SDK', 'https://atproto.blue')

# text_builder = client_utils.TextBuilder()
# text_builder.tag('This is a rich message. ', 'atproto')
# text_builder.text('I can mention ')
# text_builder.mention('account', 'did:plc:kvwvcn5iqfooopmyzvb4qzba')
# text_builder.text(' and add clickable ')
# text_builder.link('link', 'https://atproto.blue/')

post = client.send_post(text_builder)

#post = client.send_post(target_tweet_text)