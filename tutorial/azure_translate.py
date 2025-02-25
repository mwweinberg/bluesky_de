import secrets 
import requests, uuid, json 

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

text_to_translate = 'Alice #Weidel wollte Björn #Höcke einst aus der #AfD werfen. Damals ging es um das „Denkmal der Schande“.'

def azure_translate(input_text):

    body = [{}]



    body[0]['text'] = input_text


    request = requests.post(azure_constructed_url, params=azure_params, headers=azure_headers, json=body)
    response = request.json()

    #print(json.dumps(response, sort_keys=True, ensure_ascii=False, indent=4, separators=(',', ': ')))

    translated_text = response[0]['translations'][0]['text']

    #print(translated_text)

    return(translated_text)

print(azure_translate(text_to_translate))
