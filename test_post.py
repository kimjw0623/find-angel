import os
from dotenv import load_dotenv
import requests
import json

# .env 파일에서 환경 변수를 로드합니다
load_dotenv()

# 환경 변수를 가져옵니다
api_token = "bearer " + os.getenv('API_TOKEN')

url = "https://developer-lostark.game.onstove.com/auctions/items"
headers = {
    'accept': 'application/json',
    'authorization': api_token,
    'content-Type': 'application/json'
}
data = {
  "ItemLevelMin": 0,
  "ItemLevelMax": 1800,
  "ItemGradeQuality": 70,
  "SkillOptions": [
    {
      "FirstOption": None,
      "SecondOption": None,
      "MinValue": None,
      "MaxValue": None
    }
  ],
  "EtcOptions": [
    {
      "FirstOption": 7,
      "SecondOption": 45,
      "MinValue": None,
      "MaxValue": None
    }
  ],
  "Sort": "BIDSTART_PRICE",
  "CategoryCode": 200020,
  "CharacterClass": "",
  "ItemTier": None,
  "ItemGrade": "고대",
  "ItemName": "",
  "PageNo": 0,
  "SortCondition": "ASC"
}

response = requests.post(url, headers=headers, json=data)

print(response.status_code)
# print(response.json())
print(json.dumps(response.json(), indent=4, ensure_ascii=False))