import os
from dotenv import load_dotenv
import requests
import json
import concurrent.futures

# .env 파일에서 환경 변수를 로드합니다
load_dotenv()

# 환경 변수를 가져옵니다
api_token = "bearer " + os.getenv("API_TOKEN")

headers = {
    "accept": "application/json",
    "authorization": api_token,
    "content-Type": "application/json",
}

AUCTION_ITEM_URL = "https://developer-lostark.game.onstove.com/auctions/items"

CATEGORYCODE_DICT = {
    "목걸이": 200010,
    "귀걸이": 200020,
    "반지": 200030,
    "팔찌": 200040
}

VALID_OPTION_DICT = {
    200020: {
        "name": "귀걸이",
        "valid_options": [45,46] # 공격%, 무공%
    },
    200010: {
        "name": "목걸이",
        "valid_options": [41,42] # 추피, 적추피
    }
}

base_query = {
    "ItemLevelMin": 0,
    "ItemLevelMax": 1800,
    "ItemGradeQuality": 70,
    "SkillOptions": [
        {"FirstOption": None, "SecondOption": None, "MinValue": None, "MaxValue": None}
    ],
    "EtcOptions": [
        {
            "FirstOption": 7,  # EtcOptions 의 value 값 (연마 효과: 7)
            "SecondOption": 45,  # EtcSubs 의 value 값 (공격력 %: 45)
            "MinValue": 2,  # 쿼리할 EtcSubs 의 최소 value 값 설정 (1~3)
            "MaxValue": 2,  # 쿼리할 EtcSubs 의 최대 value 값 설정 (1~3)
        }
    ],
    "Sort": "BIDSTART_PRICE",
    "CategoryCode": 200020,
    "CharacterClass": "",
    "ItemTier": 4,
    "ItemGrade": "고대",
    "ItemName": "",
    "PageNo": 0,
    "SortCondition": "ASC",
}


def make_single_api_call(page_num, option_idx):
    print(f"page_num: {page_num}")
    new_query = {
        **base_query, 
        "PageNo":page_num,
        "EtcOptions": [
            {
                "FirstOption": 7,  # EtcOptions 의 value 값 (연마 효과: 7)
                "SecondOption": option_idx,  # EtcSubs 의 value 값 (공격력 %: 45)
                "MinValue": 2,  # 쿼리할 EtcSubs 의 최소 value 값 설정 (1~3)
                "MaxValue": 3,  # 쿼리할 EtcSubs 의 최대 value 값 설정 (1~3)
            }
        ],
    }
    response = requests.post(AUCTION_ITEM_URL, headers=headers, json=new_query)
    # TODO: parsing 하는 부분과 request 하는 부분 다른 함수로 분리
    auction_item_dict = json.loads(response.text)
    item_list = auction_item_dict.get("Items", {})
    item_price_list = []
    for item_info in item_list:
        # Option 리스트에서 유효 옵션 있는지 확인 후 value에 따라서 ~
        buy_price = item_info["AuctionInfo"]["BuyPrice"]
        if buy_price:
            item_price_list.append(buy_price)
    return item_price_list


# page number 에 따라서 API 호출을 동시에 실행
def make_api_calls_and_append_results():
    total_price_list = []

    for option_idx in VALID_OPTION_DICT[200020]["valid_options"]:
        new_query = {
            **base_query,
            "EtcOptions": [
                {
                    "FirstOption": 7,  # EtcOptions 의 value 값 (연마 효과: 7)
                    "SecondOption": option_idx,  # EtcSubs 의 value 값 (공격력 %: 45)
                    "MinValue": 2,  # 쿼리할 EtcSubs 의 최소 value 값 설정 (1~3)
                    "MaxValue": 3,  # 쿼리할 EtcSubs 의 최대 value 값 설정 (1~3)
                }
            ],
        }
        response = requests.post(AUCTION_ITEM_URL, headers=headers, json=new_query)
        auction_item_dict = json.loads(response.text)
        total_pages = min(auction_item_dict["TotalCount"]//10,50) # 해당하는 아이템의 최대 페이지 개수
        
        # ThreadPoolExecutor를 사용하여 병렬로 API 호출을 처리
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # API 호출을 동시에 시작
            futures = [executor.submit(make_single_api_call, i, option_idx) for i in range(total_pages)]
            
            # 모든 작업이 완료되길 기다리며 결과를 합산
            for future in concurrent.futures.as_completed(futures):
                total_price_list.extend(future.result())
    
    return total_price_list

if __name__ == "__main__":
    total = make_api_calls_and_append_results()
    print(total)
