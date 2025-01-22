import requests 
import json


###variables for the list of users you will pull from 
#DID is in the middle of the list URL
list_owner_DID = 'ijife7e4twbh2bnrybnsgpwb'
#rkey is at the end of the list url
list_rkey = '3lg424mfsl42l'



#######GET ALL OF THE USERS###########

#(python) list to hold the users from the (bluesky) list
users_list = []

#build the list url
list_url = 'at://did:plc:' + list_owner_DID + '/app.bsky.graph.list/' + list_rkey
#build the query url, which includes the list URL
full_api_request_url = 'https://public.api.bsky.app/xrpc/app.bsky.graph.getList?list=' + list_url

print(full_api_request_url)

#get the json about the list
list_payload = requests.get(full_api_request_url)

#parse the json 
list_json = json.loads(list_payload.text)

#grab all of the usernames and put them in users_list
for i in list_json['items']:
    print(f"getting {i['subject']['handle']}")
    users_list.append(i['subject']['handle'])

print(len(list_json['items']))