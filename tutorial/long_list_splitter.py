
input_string = "Next Wednesday, the collective bargaining negotiations between the #Berliner Verkehrsbetriebe and -h-Verdi will start. The union is demanding 750 euros more per month - if the #BVG does not meet the Verdi union&#39;s demands, the latter is threatening #strikes"

#take a tweet, find a space in the middle, and break it in two
def one_tweet_to_two_tweets(original_tweet_text):
    #you are looking for spaces
    split_char = ' '
    #count how many spaces there are
    space_count = input_string.count(split_char)
    #pick a space in the middle
    halfway = round(space_count/2)
    #break the tweet up into a bunch of pieces that do not include the spaces
    all_of_the_pieces_holder = input_string.split(split_char)
    #create a list of the two halves by putting the pieces from one into one bucket, and the rest into the other
    split_string_list = split_char.join(all_of_the_pieces_holder[:halfway]), split_char.join(all_of_the_pieces_holder[halfway:])

    return split_string_list

split_tweets = one_tweet_to_two_tweets(input_string)

print(split_tweets[0])
print('***')
print(split_tweets[1])