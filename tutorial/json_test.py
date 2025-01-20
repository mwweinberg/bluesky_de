import json

test_json = '''{
  "data": {
    "translations": [
      {
        "translatedText": "German is very complicated to translate",
        "detectedSourceLanguage": "de"
      }
    ]
  }
}'''

parsed_json = json.loads(test_json)

print(parsed_json['data']['translations'][0]['translatedText'])