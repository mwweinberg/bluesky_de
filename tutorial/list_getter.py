import requests
import json 


#(python) list to hold the users from the (bluesky) list
users_list = []

#DID is part of the profile rss url (profile page -> inspect source -> find '/rss')
list_owner_DID = '4yanjqr7p3j5asadjbzemqnr'
#rkey is at the end of the list url
list_rkey = '3lcnvps475z2h'

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






