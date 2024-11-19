import os
from dotenv import load_dotenv
import requests
import json
import time
from utils import *
from playsound import playsound
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from scipy import interpolate
import numpy as np
import matplotlib.pyplot as plt

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
creds = service_account.Credentials.from_service_account_file(
    drive_api_file, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

url = "https://developer-lostark.game.onstove.com/auctions/items"
headers = {
    'accept': 'application/json',
    'authorization': api_token,
    'content-Type': 'application/json'
}

def gen_search_data_honey(preset, name="", grade=None, pageNo=1):
    
    # preset의 첫 번째는 반드시 연마 단계가 되게 할 것
    level = preset[0]
    options = preset[1:]
    """
    목걸이는 주피적주피, 귀걸이는 공퍼무공퍼, 반지는 치적치피
    깡공깡무공
    목걸이 여부, 연마 단계, 상세 수치
    example of options: [(치피, 3), (치적, 3)] 
    """
    is_necklace = False
    for option in options:
        option_name = option[0]
        if option_name in necklace_only_list:
            is_necklace = True
        break

    enpoints = None
    if level:
        if is_necklace:
            enpoints = 4 + level_enpoint[grade][level]
        else:
            enpoints = 3 + level_enpoint[grade][level]

    data = {
        "ItemLevelMin": 0,
        "ItemLevelMax": 1800,
        "ItemGradeQuality": 60,
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
                "FirstOption": 8,
                "SecondOption": 1,
                "MinValue": enpoints,
                "MaxValue": enpoints
            },
        ],
        # First 7 연마효과
        # First 8 아크패시브, Second1 깨달음 Second2 도약
        "Sort": "BUY_PRICE",
        # BIDSTART_PRICE(최소입찰가), BUY_PRICE(경매시작가), EXPIREDATE, ITEM_GRADE, ITEM_LEVEL, ITEM_QUALITY
        "CategoryCode": 200000,
        # 200010 목걸이, 20 귀걸이, 30 반지, 40 팔찌, 200000 장신구
        "CharacterClass": "",
        "ItemTier": 4,
        "ItemGrade": grade,
        "ItemName": name,
        "PageNo": pageNo,
        "SortCondition": "ASC"  # ASC, DESC
    }

    for option in options:
        option_name = option[0]
        option_level_min = option[1]
        option_level_max = option[2]
        option_to_dict = {
            "FirstOption": 7,
            "SecondOption": option_dict[option_name],
            "MinValue": option_level_min,
            "MaxValue": option_level_max
        }
        data["EtcOptions"].append(option_to_dict)
    return data

def evaluate_accessory(item, grade, level, part, evaluate_functions):
    # 현재 시세표를 기반으로 해당 악세서리의 적정가를 판단

    # 딜러 악세로서의 가치 판단
    # "딜러용 or 서폿용, 뎀증퍼(딜러용) or ??(서폿용), 적정 가격: (), 가격 대비 비율: (), 꼭 확인 or None"
    result = []
    dmg_increment_percent = calc_dmg_increment_percent(item)
    f = evaluate_functions[f"{grade} {level}연마 딜러 {part}"]
    try:
        expected_price_dealer = int(f(dmg_increment_percent))
    except ValueError:
        expected_price_dealer = item["AuctionInfo"]["BuyPrice"]

    # 서폿 악세로서의 가치 판단
    f = evaluate_functions[f"{grade} {level}연마 서폿 {part}"]  # ??
    try:
        supporter_option_summarized = extract_supporter_options(item)
        expected_price_supporter = f[supporter_option_summarized]
    except (ValueError, KeyError): # 아마 유효옵 아닌 서폿옵들?
        # expected_price_supporter = item["AuctionInfo"]["BuyPrice"]
        expected_price_supporter = 10

    # if expected_price_dealer > expected_price_supporter:
    expected_price = expected_price_dealer
    result.append('딜러용')
    result.append(f'{dmg_increment_percent:.5f}%')
    # else:
    #   expected_price = expected_price_supporter
    #   result.append('서폿용')
    #   result.append(supporter_option_summarized)

    result.append(expected_price)
    ratio = item["AuctionInfo"]["BuyPrice"] / expected_price
    result.append(f'{100 * ratio:.2f}%')
    my_threshold = {
        "목걸이": 2.5,
        "귀걸이": 1.7,
        "반지": 1.5,
    }
    return result

def process_new_items(new_items, evaluate_functions):
    # 이름, 품질, 즉구가, 남은 시간, 만료 시각, 부가적인 옵션(깡공, 깡무공 등)
    data = new_items
    if not data:
        return None

    current_time = datetime.now()
    wanted_info = {
        "TotalCount": len(data),
        "Items": []
    }
    for item in data:
        # process time
        end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
        remaining_time = end_time_isoformat - current_time + timedelta(seconds=60)
        days = remaining_time.days
        hours, remainder = divmod(remaining_time.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if days >= 1:
            remaining_time_str = f'{days}일'
        else:
            remaining_time_str = f'{hours}시간 {minutes}분'

        if not item["AuctionInfo"]["BuyPrice"]:  # 즉구가 설정 안 되어 있으면 패스
            continue
        item_data = [f'{item["Name"]:>13s}', f'{item["GradeQuality"]:>3d}', f'{item["AuctionInfo"]["BuyPrice"]:>7d}', f'구매 후 거래 {item["AuctionInfo"]["TradeAllowCount"]}회',
                     f'{remaining_time_str:>9s}', end_time_isoformat.strftime("%Y-%m-%d %H:%M:%S")]
        
        # process detailed options
        grade = item["Grade"]
        level = len(item["Options"]) - 1  # 깨달음 항목 빼면 연마 단계 수가 나옴
        if level == 0 or item['GradeQuality'] < 67:      # 0연마랑 67 미만은 볼 것도 없어
            continue
        if "목걸이" in item["Name"]:
            part = "목걸이"
        elif "귀걸이" in item["Name"]:
            part = "귀걸이"
        elif "반지" in item["Name"]:
            part = "반지"
        fix_dup_options(item)
        options = item["Options"]
        for option in options:
            item_data.append(f"{option['OptionName']}{str(option['Value'])} ")
        evaluate_result = evaluate_accessory(item, grade, level, part, evaluate_functions)
        item_data += evaluate_result
        item_data = item_data[-3:] + item_data[:-3]  # 최종 평가를 맨 앞으로
        wanted_info["Items"].append(item_data)

    return wanted_info

def find_items_with_queries(grade, name, preset):

    items = []
    repeat = True
    pageNo = 1
    while repeat:
        post_body = gen_search_data_honey(preset, name, grade, pageNo=pageNo)
        response = do_search(url, headers, post_body)
        data = response.json()
        total_count = data["TotalCount"]
        for item in data["Items"]:
            items.append(item)
        if total_count > pageNo * 10:
            pageNo += 1
        else:
            break
    return items

if __name__ == "__main__":
    evaluate_functions = load_evaluate_functions()
    queries = [
        # {"grade": "고대",
        #  "name": "",
        #  "preset": [1, ("무공퍼", 1, 3),] # 귀걸이 1.2, 20만골
        #  },
        {"grade": "고대",
         "name": "",
         "preset": [3, ("추피", 1, 3), ("적주피", 1, 3)] # 목걸이 2, 25~만골 1개
         },
        # {"grade": "고대",
        #  "name": "반지",
        #  "preset": [3, ("치피", 1, 3)] # 반지 1.2, 15~20만골 2개 
        #  }, 
    ]
    for query in queries:
        new_items = find_items_with_queries(query["grade"], query["name"], query["preset"])
        print(f"{query['grade']} {query['name']}, {query['preset']}")   
        result = process_new_items(new_items, evaluate_functions)
        if result:
            print(f"{result['TotalCount']} items were found")
            for item in result["Items"]:
                if float(item[0][:-1]) > 2:
                # if item[0] != "...":
                #     print(item)
                    print(f"{float(item[0][:-1])/int(item[5])*100000:.4f}%/10만G", item)

        print()
