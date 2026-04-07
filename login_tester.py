
from atproto import Client, client_utils
#this is the local secrets file
import secrets

#bluesky credentials
#create the object
client = Client()
#credential variables are used below
user_name = secrets.user_name
password = secrets.password



#login to bluesky
client.login(user_name, password)