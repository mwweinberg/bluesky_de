import re 

input_tweets = ["Wie prägte die Teilung das Reiseverhalten der Deutschen? Simone Schmollack und Andreas Rüttenauer im Gespräch über Ferien, Fernweh und Freiheit. https://taz.de/!6104365", "Sherrie Levine, Large Check: 7, 1987 #artbots #moma https://botfrens.com/collections/14377/contents/1136976"]

def extract_components(input_string):
    # Define regex patterns for URL and @mention
    #this is the chatGPT one that did not work
    #url_pattern = r'https?://[^\s]+(?:[^\w\s]|$)'  # Match URL, but stop before punctuation like ".", ",", etc.
    #this is the stack overflow one that did
    #url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'
    #url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-!])'
    url_pattern = r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:/~+#\-!]*[\w@?^=%&/~+#\-!])'

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


for i in input_tweets:
    output_tweet = extract_components(i)
    print(output_tweet)
