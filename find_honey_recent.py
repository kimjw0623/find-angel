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
api_token_3day = "bearer " + os.getenv('API_TOKEN_HONEYITEM_3DAY')
api_token_1day = "bearer " + os.getenv('API_TOKEN_HONEYITEM_1DAY')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
drive_api_file = os.getenv("DRIVE_API_PATH")
creds = service_account.Credentials.from_service_account_file(
    drive_api_file, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

url = "https://developer-lostark.game.onstove.com/auctions/items"
headers_3day = {
    'accept': 'application/json',
    'authorization': api_token_3day,
    'content-Type': 'application/json'
}
headers_1day = {
    'accept': 'application/json',
    'authorization': api_token_1day,
    'content-Type': 'application/json'
}



def gen_search_data_honey(grade, pageNo=1):
  # 가장 최근에 올라온 매물부터 확인
  data = {
      "ItemLevelMin": 0,
      "ItemLevelMax": 1800,
      "ItemGradeQuality": None,
      "SkillOptions": [
          {
              "FirstOption": None,
              "SecondOption": None,
              "MinValue": None,
              "MaxValue": None
          }
      ],
      # First 7 연마효과
      # Second 45 공퍼(0.4, 0.95, 1.55), 53 깡공(80, 195, 390), 44 낙인력(2.15, 4.8, 8), 46 무공퍼(0.8, 1.8, 3)
      # Second 54 깡무공(195, 480, 960), 57 상태이상공격지속시간(0.2, 0.5, 1), 43 아덴게이지(1.6, 3.6, 6)
      # Second 51 아공강(1.35, 3, 5), 52 아피강(2, 4.5, 7.5), 42 적주피(0.55, 1.2, 2), 58 전투중생회(10, 25, 50)
      # Second 56 최마(6, 15, 30), 55 최생(1300, 3250, 6500), 41 추피(0.7, 1.6, 2.6), 49 치적(0.4, 0.95, 1.55)
      # Second 50 치피(1.1, 2.4, 4.0), 48 아군보호막(0.95, 2.1, 3.5), 47 아군회복(0.95, 2.1, 3.5)
      # 그런데 그냥 하옵, 중옵, 상옵을 1, 2, 3으로 두면 된다.
      # First 8 아크패시브, Second1 깨달음 Second2 도약
      "Sort": "EXPIREDATE",
      # BIDSTART_PRICE(최소입찰가), BUY_PRICE(경매시작가), EXPIREDATE, ITEM_GRADE, ITEM_LEVEL, ITEM_QUALITY
      "CategoryCode": 200000,
      # 200010 목걸이, 20 귀걸이, 30 반지, 40 팔찌, 200000 장신구
      "CharacterClass": "",
      "ItemTier": 4,
      "ItemGrade": grade,
      "ItemName": "",
      "PageNo": pageNo,
      "SortCondition": "DESC",  # ASC, DESC
      "EtcOptions": [
            {
                "FirstOption": 8,
                "SecondOption": 1,
                "MinValue": 1,
                "MaxValue": '',
            },
        ],
  }

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

    if expected_price_dealer > expected_price_supporter:
      expected_price = expected_price_dealer
      result.append('딜러용')
      result.append(f'{dmg_increment_percent:.5f}%')
    else:
      expected_price = expected_price_supporter
      result.append('서폿용')
      result.append(supporter_option_summarized)

    result.append(expected_price)
    profit = expected_price - item["AuctionInfo"]["BuyPrice"]
    ratio = item["AuctionInfo"]["BuyPrice"] / expected_price
    result.append(f'{100 * ratio:.2f}%')
    my_threshold = {
        "목걸이": 222,
        "귀걸이": 222,
        "반지": 222,
    }
    if profit > 60000 : # 3연마
        result.append("꼭 확인")
    elif ratio < 0.6 and expected_price > 60000 and len(item["Options"]) == 4 : # 3연마
        result.append("꼭 확인")
    elif ratio < 0.45 and expected_price > 40000 and len(item["Options"]) < 4: # 3연마
        result.append("꼭 확인")
    # elif (dmg_increment_percent > my_threshold[part]) and item["Grade"] == "고대": # and (ratio < 1.1)
    #     result.append("내가 노리는 거")
    # elif ratio < 0.9 and profit > 10000:
    #     result.append("괜찮은 듯?")
    else:
        result.append("...")
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
        try:
            item_data = [f"{item['Grade']}", f'{item["Name"]}', f'{item["GradeQuality"]:>3d}', f'{item["AuctionInfo"]["BuyPrice"]:>7d}', f'구매 후 거래 {item["AuctionInfo"]["TradeAllowCount"]}회',
                     f'{remaining_time_str:>9s}', end_time_isoformat.strftime("%Y-%m-%d %H:%M:%S")]
        except TypeError as e:
            print(item)
        
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
        item_data = [item_data[-1]] + item_data[:-1]  # 최종 평가를 맨 앞으로
        wanted_info["Items"].append(item_data)

    return wanted_info

def find_new_items_3day(last_expireDate=None):
    # 3일짜리는 굳이 마지막 page index가 필요가 없다
    current_time = datetime.now()
    if not last_expireDate:
       last_expireDate = current_time + \
           timedelta(days=3) - timedelta(minutes=3)

    new_items = []
    repeat = True
    pageNo = 1
    next_expireDate = None
    while repeat:
        post_body = gen_search_data_honey(grade="", pageNo=pageNo)
        response = do_search(url, headers_3day, post_body, error_log=False)
        data = response.json()
        for item in data["Items"]:
            end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
            if end_time_isoformat <= last_expireDate:
                repeat = False
                break
            else:
               new_items.append(item)
               if not next_expireDate:
                   next_expireDate = end_time_isoformat
        pageNo += 1

    if not next_expireDate:
        next_expireDate = last_expireDate
    return new_items, next_expireDate


def find_starting_page(last_page_index, current_expireDate):
    """
    Case 1: This page is to early to check. We should go forward(the page number should be large)
    Case 2: Current page is the the best starting point
    Case 3: This page is too late to check. We should go backward(the page number should be small)
    """
    pageNo = last_page_index
    post_body = gen_search_data_honey(grade="", pageNo=pageNo)
    response = do_search(url, headers_1day, post_body, error_log=False)
    data = response.json()
    first_item = data["Items"][0]
    last_item = data["Items"][-1]

    first_item_end_time_isoformat = parse_datetime(
        first_item["AuctionInfo"]["EndDate"])
    last_item_end_time_isoformat = parse_datetime(
        first_item["AuctionInfo"]["EndDate"])

    if (first_item_end_time_isoformat > current_expireDate) and (last_item_end_time_isoformat < current_expireDate):
        # Case 2
        return pageNo

    elif (first_item_end_time_isoformat > current_expireDate) and (last_item_end_time_isoformat > current_expireDate):
        # Case 1
        going_forward = True
        while going_forward:
            pageNo += 3
            post_body = gen_search_data_honey(grade="", pageNo=pageNo)
            response = do_search(url, headers_1day, post_body, error_log=False)
            data = response.json()
            item = data["Items"][-1]

            end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
            if end_time_isoformat < current_expireDate:
                going_back = False
                break
        return pageNo-3

    elif (first_item_end_time_isoformat < current_expireDate) and (last_item_end_time_isoformat < current_expireDate):
        # Case 3
        going_back = True
        pageNo -= 3
        while going_back:
            post_body = gen_search_data_honey(grade="", pageNo=pageNo)
            response = do_search(url, headers_1day, post_body, error_log=False)
            data = response.json()
            item = data["Items"][-1]

            end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
            if end_time_isoformat > current_expireDate:
                going_back = False
                break
            pageNo -= 3
        return pageNo


def find_new_items_1day(last_page_index=None, last_expireDate=None):
    # 1일짜리
    current_time = datetime.now()
    current_expireDate = current_time + timedelta(days=1)
    if not last_expireDate:
       last_expireDate = current_expireDate - timedelta(minutes=3)

    new_items = []
    if not last_page_index:
        last_page_index = 260

    next_expireDate = None
    pageNo = find_starting_page(last_page_index, current_expireDate)
    repeat = True
    while repeat:
        post_body = gen_search_data_honey(grade="", pageNo=pageNo)
        response = do_search(url, headers_1day, post_body, error_log=False)
        data = response.json()
        for item in data["Items"]:
            end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
            if end_time_isoformat <= last_expireDate:
                repeat = False
                break
            elif end_time_isoformat < current_expireDate:
               new_items.append(item)
               if not next_expireDate:
                   next_expireDate = end_time_isoformat
        pageNo += 1
    if not next_expireDate:
        next_expireDate = last_expireDate
    return new_items, pageNo, next_expireDate


if __name__ == "__main__":

    last_expireDate_3day = None
    last_expireDate_1day = None
    last_page_index_1day = None
    evaluate_functions = load_evaluate_functions()

    while True:
        play_beep = False
        current_time = datetime.now()
        if (datetime.strptime(evaluate_functions["time"], "%Y-%m-%d %H:%M:%S") < current_time - timedelta(minutes=120)):
            evaluate_functions = load_evaluate_functions()
            print("Updating evaluate functions...")

        new_items, last_expireDate_3day = find_new_items_3day(last_expireDate=last_expireDate_3day)
        result = process_new_items(new_items, evaluate_functions)
        if result:
            # print(f"{result['TotalCount']} items were found, expire cut {last_expireDate_3day}")
            reversed_items = result["Items"][::-1]
            for item in reversed_items:
                if item[0] != "...":
                    print(item)
                # print(item)
                if not play_beep and (item[0] == "꼭 확인" or item[0] == "내가 노리는 거"):
                    play_beep = True
        if play_beep:
            playsound('level-up-2-199574.mp3')

        play_beep = False
        new_items, last_page_index_1day, last_expireDate_1day = find_new_items_1day(
            last_page_index=last_page_index_1day, last_expireDate=last_expireDate_1day)
        result = process_new_items(new_items, evaluate_functions)
        if result:
            # print(f"{result['TotalCount']} items were found, expire cut {last_expireDate_1day}")
            reversed_items = result["Items"][::-1]
            for item in reversed_items:
                if item[0] != "...":
                    print(item)
                # print(item)
                if not play_beep and (item[0] == "꼭 확인" or item[0] == "내가 노리는 거"):
                    play_beep = True

        if play_beep:
            print(datetime.now())
            playsound('level-up-2-199574.mp3')
        time.sleep(2)

        # new_items = find_new_items_1day()
        # response = do_search(url, headers, post_body)
        # print(json.dumps(response.json(), indent=4, ensure_ascii=False))  # Check raw response
        # print(search_preset)
        # print(result["TotalCount"])


# # 스프레드시트 ID와 범위 지정
# SHEET_NAME = "4T 악세 검색기"
# RANGE_NAME = f'{SHEET_NAME}!A:E'
# request = service.spreadsheets().values().update(
#     spreadsheetId=SPREADSHEET_ID,
#     range=RANGE_NAME,
#     valueInputOption='USER_ENTERED',
#     body={'values': result["Items"]}
# )

# response = request.execute()
