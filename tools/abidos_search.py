import os
from dotenv import load_dotenv
import requests
import json
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from playsound import playsound

# start_time = time.perf_counter()
# end_time = time.perf_counter()
# execution_time = end_time - start_time
# print(f"실행 시간: {execution_time:.5f} 초")

# .env 파일에서 환경 변수를 로드합니다
load_dotenv()

# 환경 변수를 가져옵니다
api_token = "bearer " + os.getenv('API_TOKEN_MANUAL')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
drive_api_file = os.getenv("DRIVE_API_PATH")
creds = service_account.Credentials.from_service_account_file(drive_api_file, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

url = "https://developer-lostark.game.onstove.com/markets/items"
headers = {
    'accept': 'application/json',
    'authorization': api_token,
    'content-Type': 'application/json'
}

def find_first_empty_cell(sheet_name, column="A"):

    SHEET_NAME = sheet_name
    range_name = f'{SHEET_NAME}!{column}1'
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    values = result.get('values', [])

    if values:
        a1_value = values[0][0]  # A1 셀의 값
        return int(a1_value)
    else:
        # 지정된 열의 모든 셀 가져오기
        SHEET_NAME = sheet_name
        range_name = f'{SHEET_NAME}!{column}:{column}'
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        
        # 첫 번째 빈 셀의 행 번호 찾기
        for i, value in enumerate(values, start=1):
            if not value:
                return i

        # 모든 셀이 채워져 있으면 다음 행 반환
        return len(values) + 1


living_skill_codes = ["90200", "90300", "90400", "90500", "90600", "90700"] # 식물채집, 벌목, 채광, 수렵, 냒시, 고고학 순서대로
avatar_codes = ["20005", "20010", "20050", "20060"] # 무기, 머리, 상의, 하의 순서대로
"""
6882101	6882104	6882107	6882109
6882301	6882304	6884307	6884308
6882401	6882404	6884407	6884408
6882501	6882504	6885505	6885508	6885509	6882508
6882601	6882604	6885608	6885609	6882608
6882701	6882704	6885705	6885708	6885709	6882708
"""

items_order = {
    "들꽃": 0,
    "수줍은 들꽃": 1,
    "화사한 들꽃": 2,
    "아비도스 들꽃": 3,
    "목재": 4,
    "부드러운 목재": 5,
    "튼튼한 목재": 6,
    "아비도스 목재": 7,
    "철광석": 8,
    "묵직한 철광석": 9,
    "단단한 철광석": 10,
    "아비도스 철광석": 11,
    "두툼한 생고기": 12,
    "다듬은 생고기": 13,
    "진귀한 가죽": 14,
    "오레하 두툼한 생고기": 15,
    "아비도스 두툼한 생고기": 16,
    "수렵의 결정": 17,
    "생선": 18,
    "붉은 살 생선": 19,
    "오레하 태양 잉어": 20,
    "아비도스 태양 잉어": 21,
    "낚시의 결정": 22,
    "고대 유물": 23,
    "희귀한 유물": 24,
    "진귀한 유물": 25,
    "오레하 유물": 26,
    "아비도스 유물": 27,
    "고고학의 결정": 28,
}

current_min_prices = []

def find_avatar():
    while True:
        for avatar_code in avatar_codes:
            if avatar_code == "20005":
                thold = 20000
            if avatar_code == "20010":
                continue
            if avatar_code == "20050":
                continue
            if avatar_code == "20060":
                continue

        post_body = {
        "Sort": "GRADE",
        "CategoryCode": avatar_code,
        "CharacterClass": "블레이드",
        "ItemTier": None,
        "ItemGrade": "전설",
        "ItemName": None,
        "PageNo": 1,
        "SortCondition": "ASC"
        }

        response = requests.post(url, headers=headers, json=post_body)
        if response.status_code != 200:
            print(response.status_code)
        # print(json.dumps(response.json(), indent=4, ensure_ascii=False))
        items = response.json()["Items"]
        for item in items:
            if item["CurrentMinPrice"] < thold:
                playsound('level-up-2-199574.mp3')
                print(item)
        time.sleep(30)

def fill_abidos():
    SHEET_NAME = "거래소 재료 가격"
    data_to_sheet = [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    current_min_prices = []
    for living_skill_code in living_skill_codes:

        
        post_body = {
        "Sort": "GRADE",
        "CategoryCode": living_skill_code,
        "CharacterClass": None,
        "ItemTier": None,
        "ItemGrade": None,
        "ItemName": None,
        "PageNo": 1,
        "SortCondition": "ASC"
        }


        response = requests.post(url, headers=headers, json=post_body)
        if response.status_code != 200:
            print(response.status_code)
        # print(json.dumps(response.json(), indent=4, ensure_ascii=False))
        items = response.json()["Items"]
        for item in items:
            print(f"{item['Name']}: {item['CurrentMinPrice']}")
            current_min_prices.append([item['Name'], item['CurrentMinPrice']])

    current_min_prices = sorted(current_min_prices, key=lambda x: items_order[x[0]])    
    current_min_prices = [x[1] for x in current_min_prices]
    data_to_sheet += current_min_prices
    
    first_empty_cell = find_first_empty_cell(SHEET_NAME, "A")
    
    result = service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!{"A"}{first_empty_cell}',
        valueInputOption='USER_ENTERED',
        body={'values': [data_to_sheet]}
    ).execute()

if __name__ == "__main__":
    # find_avatar()
    fill_abidos()
