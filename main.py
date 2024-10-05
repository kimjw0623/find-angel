import os
from dotenv import load_dotenv
import requests
import json

# .env 파일에서 환경 변수를 로드합니다
load_dotenv()

# 환경 변수를 가져옵니다
api_token = "bearer " + os.getenv('API_TOKEN')

headers = {
    'accept': 'application/json',
    'authorization': api_token,
    'content-Type': 'application/json'
}

auction_option_url = "https://developer-lostark.game.onstove.com/auctions/options"

auction_option = requests.get(auction_option_url, headers=headers)
auction_option_dict = json.loads(auction_option.text)
# if not os.path.exists('auction_option.json'):
    # with open('auction_option.json', 'w') as json_file:
    #     json.dump(json.loads(auction_option.text), json_file, indent=4, ensure_ascii=False)  # indent는 보기 좋게 들여쓰기 설정

def get_action_options(auction_option_dict):
    GRINDING_OPTIONS = auction_option_dict.get("EtcOptions")[6]
    pass


# get_action_options(auction_option)


auction_item_url = "https://developer-lostark.game.onstove.com/auctions/items"

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
  "CategoryCode": 200000,
  "CharacterClass": "",
  "ItemTier": 4,
  "ItemGrade": "고대",
  "ItemName": "",
  "PageNo": 0,
  "SortCondition": "ASC"
}

response = requests.post(auction_item_url, headers=headers, json=data)
auction_item_dict = json.loads(response.text)

