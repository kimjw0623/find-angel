import os
import math
import requests
import json
import time
import numpy as np
import matplotlib.pyplot as plt
from utils import *
from google.oauth2 import service_account
from googleapiclient.discovery import build
from scipy import interpolate
from sklearn.isotonic import IsotonicRegression
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import init_db, save_price_data, get_recent_prices

# start_time = time.perf_counter()
# end_time = time.perf_counter()
# execution_time = end_time - start_time
# print(f"실행 시간: {execution_time:.5f} 초")

# .env 파일에서 환경 변수를 로드합니다
load_dotenv()

# 환경 변수를 가져옵니다
api_token = "bearer " + os.getenv('API_TOKEN_LOWESTPRICE')

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

def gen_search_data(grade, preset, pageNo=1):
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

  if is_necklace:
    enpoints = 4 + level_enpoint[grade][level]
  else:
    enpoints = 3 + level_enpoint[grade][level]

  data = {
      "ItemLevelMin": 0,
      "ItemLevelMax": 1800,
      "ItemGradeQuality": 60,
      # "ItemUpgradeLevel": null,
      # "ItemTradeAllowCount": null,
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
      "ItemTier": None,
      "ItemGrade": grade,
      "ItemName": "",
      "PageNo": pageNo,
      "SortCondition": "ASC"  # ASC, DESC
  }

  for option in options:
      option_name = option[0]
      option_level = option[1]
      option_to_dict = {
          "FirstOption": 7,
          "SecondOption": option_dict[option_name],
          "MinValue": option_level,
          "MaxValue": option_level,
      }
      data["EtcOptions"].append(option_to_dict)

  return data

def process_response(response):
  # 이름, 품질, 즉구가, 남은 시간, 만료 시각, 부가적인 옵션(깡공, 깡무공 등)
    data = response.json()
    if not data["Items"]:
       return None

    current_time = datetime.now()
    wanted_info = {
      "TotalCount": data["TotalCount"],
      "ValidCount": min(data["TotalCount"], 10),
      "SearchedTime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
      "Items": []
    }
    for item in data["Items"]:
        # 즉구가 설정 안 되어 있으면 패스, 혹은 품질이 67 미만
        if (not item["AuctionInfo"]["BuyPrice"]) or (item["GradeQuality"] < 67):
            wanted_info["ValidCount"] -= 1
            continue
        # process time
        end_time_isoformat = parse_datetime(item["AuctionInfo"]["EndDate"])
        # end_time_isoformat = datetime.strptime(item["AuctionInfo"]["EndDate"], "%Y-%m-%dT%H:%M:%S.%f")
        remaining_time = end_time_isoformat - current_time + timedelta(seconds=60)
        days = remaining_time.days
        hours, remainder = divmod(remaining_time.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if days >= 1:
            remaining_time_str = f'{days}일'
        else:
            remaining_time_str = f'{hours}시간 {minutes}분'

        item_data = [item["Name"], f'{item["GradeQuality"]:>3d}', f'{item["AuctionInfo"]["BuyPrice"]:>7d}',
                    f'{remaining_time_str:>9s}', end_time_isoformat.strftime("%Y-%m-%d %H:%M:%S")]

        # process options
        fix_dup_options(item)
        for option in item["Options"]:
            item_data.append(f"{option['OptionName']}{str(option['Value'])} ")

        dmg_increment_percent = calc_dmg_increment_percent(item)
        item_data.append(f'{dmg_increment_percent:.3f}%')
        wanted_info["Items"].append(item_data)

    return wanted_info

def sort_and_average(x, y):
    sort_indices = np.argsort(x)
    x_sorted = x[sort_indices]
    y_sorted = y[sort_indices]
    
    unique_x, indices, counts = np.unique(x_sorted, return_index=True, return_counts=True)
    y_averaged = np.array([np.mean(y_sorted[i:i+c]) for i, c in zip(indices, counts)])
    
    return unique_x, y_averaged

def interpolate_increment_price(increments, prices, grade, i, position, part):
    print(increments)
    print(prices)
    unique_increments, prices_averaged = sort_and_average(increments, prices)

    # Isotonic Regression 적용. 단조증가하게 변형
    ir = IsotonicRegression(out_of_bounds='clip')
    y_iso = ir.fit_transform(unique_increments, prices_averaged)

    if len(unique_increments) > 3:
        # f = interpolate.UnivariateSpline(unique_increments, y_iso, s=len(unique_increments)*0.1)
        f = interpolate.UnivariateSpline(unique_increments, y_iso, k=1) # 그냥 다 선형으로...
    else:
        f = interpolate.UnivariateSpline(unique_increments, y_iso, k=1) # 데이터 포인트가 너무 적으면 선형으로

    min_increment = min(unique_increments)
    max_increment = max(unique_increments)
    test_increments = np.linspace(min_increment, max_increment, 50)
    test_prices = f(test_increments)

    plt.figure(figsize=(10, 6))
    plt.scatter(unique_increments, prices_averaged, c='red', label='searched')
    plt.plot(test_increments, test_prices, 'b-', label='interpolated')
    plt.xlabel('damage increments(%)')
    plt.ylabel('price')
    plt.grid()
    plt.savefig(f'{grade} {i}연마 {position} {part}.png')
    plt.close()

    return f

def search_part_and_update_subroutine(grade, position, part, search_presets, evaluate_functions):
    # 예: 고대 딜러 목걸이(3, 2, 1연마 모두 가지고 있음)에 대한 결과 반환
    # 딜러옵은 damage increment percent를, 서폿옵은 옵션 자체로 문자열로 따짐
    keys_or_increments = {
       3: [],
       2: [],
       1: [],
    }
    prices = {
       3: [],
       2: [],
       1: []
    }
    
    sub_result_for_sheet = []
    for search_preset in search_presets:
        level = search_preset[0] # 연마 단계
        post_body = gen_search_data(grade, search_preset)
        # print(json.dumps(post_body, indent=4, ensure_ascii=False))  # Check post body
        response = do_search(url, headers, post_body)
        # print(json.dumps(response.json(), indent=4, ensure_ascii=False))  # Check raw response
        print(grade, search_preset, end=": ")
        result = process_response(response)
        if result and result["Items"]:
            totalCount = result["TotalCount"]
            validCount = result["ValidCount"]
            num_of_points = min(validCount, math.ceil(totalCount / 10)) # 매물이 많은 검색 조건은 시장가 계산을 위한 매물을 많이 준비
            for j in range(num_of_points):
                low_price_item = result["Items"][j]
                low_price = low_price_item[2]
                if position == "딜러":
                    keys_or_increments[level].append(float(low_price_item[-1][:-1])) # damage increment in percent.
                elif position == "서폿":
                    keys_or_increments[level].append(search_preset[1:]) # 연마 단계를 제외한 유효옵 리스트 자체가 키가 됨
                prices[level].append(int(low_price))
                if j == 0:
                  sub_result_for_sheet.append(low_price)  # 진짜 최저가(딱 하나만)
            print(f"Total {result['TotalCount']} items")
            for item in result["Items"]:
                print(item)
        else:
            sub_result_for_sheet.append(0)  # 매물 없음
            print("no item searched")

    # print(keys_or_increments)
    # print(prices)
    # 1, 2, 3연마 업데이트
    for i in [1, 2, 3]:
        if position == "딜러":
            f = interpolate_increment_price(np.array(keys_or_increments[i]), np.array(prices[i]), grade, i, position, part)
            evaluate_functions[f"{grade} {i}연마 {position} {part}"] = f
        elif position == "서폿":
          evaluate_functions[f"{grade} {i}연마 {position} {part}"] = dict(zip(map(tuple , keys_or_increments[i]), prices[i]))

    return sub_result_for_sheet, evaluate_functions

def search_part_and_update(part, first_empty_cell=None):
    # 주피, 적주피 등 줄임말 쓸 것
    # Return next empty cell
    # 여기서 파일들을 업데이트.
    if part == "목걸이":
        search_presets_antique_dealer = [
          [3, ("추피", 3), ("적주피", 3)],
          [3, ("추피", 2), ("적주피", 3)],
          [3, ("추피", 3), ("적주피", 2)],
          [3, ("추피", 3), ("적주피", 1)],
          [3, ("추피", 1), ("적주피", 3)],
          [3, ("추피", 2), ("적주피", 2)],
          [3, ("추피", 3)],
          [3, ("적주피", 3)],
          [3, ("추피", 2), ("적주피", 1)],
          [3, ("추피", 1), ("적주피", 2)],
          [3, ("추피", 2)],
          [3, ("적주피", 2)],
          [3, ("추피", 1), ("적주피", 1)],
          [3, ("추피", 1)],
          [3, ("적주피", 1)],
          [3, ],
          [2, ("추피", 3), ("적주피", 3)],
          [2, ("추피", 2), ("적주피", 3)],
          [2, ("추피", 3), ("적주피", 2)],
          [2, ("추피", 3), ("적주피", 1)],
          [2, ("추피", 1), ("적주피", 3)],
          [2, ("추피", 2), ("적주피", 2)],
          [2, ("추피", 3)],
          [2, ("적주피", 3)],
          [2, ("추피", 2), ("적주피", 1)],
          [2, ("추피", 1), ("적주피", 2)],
          [2, ("추피", 2)],
          [2, ("적주피", 2)],
          [2, ("추피", 1), ("적주피", 1)],
          [2, ("추피", 1)],
          [2, ("적주피", 1)],
          [2, ],
          [1, ("추피", 3)],
          [1, ("적주피", 3)],
          [1, ("추피", 2)],
          [1, ("적주피", 2)],
          [1, ("추피", 1)],
          [1, ("적주피", 1)],
          [1, ],
      ]
        search_presets_antique_supporter = [
          [3, ("아덴게이지", 3), ("낙인력", 3)],
          [3, ("아덴게이지", 2), ("낙인력", 3)],
          [3, ("아덴게이지", 1), ("낙인력", 3)],
          [3, ("아덴게이지", 3), ("낙인력", 2)],
          [3, ("낙인력", 3)],
          [2, ("아덴게이지", 3), ("낙인력", 3)],
          [2, ("아덴게이지", 2), ("낙인력", 3)],
          [2, ("아덴게이지", 1), ("낙인력", 3)],
          [2, ("아덴게이지", 3), ("낙인력", 2)],
          [2, ("낙인력", 3)],
          [1, ("낙인력", 3)],
      ]
        search_presets_artifact_dealer = [
          [3, ("추피", 3), ("적주피", 3)],
          [3, ("추피", 2), ("적주피", 3)],
          [3, ("추피", 3), ("적주피", 2)],
          [3, ("추피", 3), ("적주피", 1)],
          [3, ("추피", 1), ("적주피", 3)],
          [3, ("추피", 2), ("적주피", 2)],
          [3, ("추피", 3)],
          [3, ("적주피", 3)],
          [3, ],
          [2, ("추피", 3), ("적주피", 3)],
          [2, ("추피", 2), ("적주피", 3)],
          [2, ("추피", 3), ("적주피", 2)],
          [2, ("추피", 3), ("적주피", 1)],
          [2, ("추피", 1), ("적주피", 3)],
          [2, ("추피", 2), ("적주피", 2)],
          [2, ("추피", 3)],
          [2, ("적주피", 3)],
          [2, ],
          [1, ("추피", 3)],
          [1, ("적주피", 3)],
          [1, ],
      ]
        search_presets_artifact_supporter = [
          [3, ("아덴게이지", 3), ("낙인력", 3)],
          [3, ("아덴게이지", 2), ("낙인력", 3)],
          [3, ("아덴게이지", 1), ("낙인력", 3)],
          [3, ("아덴게이지", 3), ("낙인력", 2)],
          [3, ("낙인력", 3)],
          [2, ("아덴게이지", 3), ("낙인력", 3)],
          [2, ("아덴게이지", 2), ("낙인력", 3)],
          [2, ("아덴게이지", 1), ("낙인력", 3)],
          [2, ("아덴게이지", 3), ("낙인력", 2)],
          [2, ("낙인력", 3)],
          [1, ("낙인력", 3)],
      ]
        SHEET_NAME = "4T 목걸이 검색기"
    elif part == "귀걸이":  # 아 서폿거 너무 골때려 쉬불
        search_presets_antique_dealer = [
            [3, ("공퍼", 3), ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 3)],
            [3, ("공퍼", 3), ("무공퍼", 2)],
            [3, ("공퍼", 3), ("무공퍼", 1)],
            [3, ("공퍼", 1), ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 2)],
            [3, ("공퍼", 3)],
            [3, ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 1)],
            [3, ("공퍼", 1), ("무공퍼", 2)],
            [3, ("공퍼", 2)],
            [3, ("무공퍼", 2)],
            [3, ("공퍼", 1), ("무공퍼", 1)],
            [3, ("무공퍼", 1)],
            [3, ("공퍼", 1)],
            [3, ],
            [2, ("공퍼", 3), ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 3)],
            [2, ("공퍼", 3), ("무공퍼", 2)],
            [2, ("공퍼", 3), ("무공퍼", 1)],
            [2, ("공퍼", 1), ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 2)],
            [2, ("공퍼", 3)],
            [2, ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 1)],
            [2, ("공퍼", 1), ("무공퍼", 2)],
            [2, ("공퍼", 2)],
            [2, ("무공퍼", 2)],
            [2, ("공퍼", 1), ("무공퍼", 1)],
            [2, ("무공퍼", 1)],
            [2, ("공퍼", 1)],
            [2, ],
            [1, ("공퍼", 3)],
            [1, ("무공퍼", 3)],
            [1, ("공퍼", 2)],
            [1, ("무공퍼", 2)],
            [1, ("무공퍼", 1)],
            [1, ("공퍼", 1)],
            [1, ],
        ]
        search_presets_antique_supporter = [
            [3, ("아군회복", 3), ("아군보호막", 3)],
            [2, ("아군회복", 3), ("아군보호막", 3)],
        ]
        search_presets_artifact_dealer = [
            [3, ("공퍼", 3), ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 3)],
            [3, ("공퍼", 3), ("무공퍼", 2)],
            [3, ("공퍼", 3), ("무공퍼", 1)],
            [3, ("공퍼", 1), ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 2)],
            [3, ("공퍼", 3)],
            [3, ("무공퍼", 3)],
            [3, ("공퍼", 2), ("무공퍼", 1)],
            [3, ("공퍼", 1), ("무공퍼", 2)],
            [3, ],
            [2, ("공퍼", 3), ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 3)],
            [2, ("공퍼", 3), ("무공퍼", 2)],
            [2, ("공퍼", 3), ("무공퍼", 1)],
            [2, ("공퍼", 1), ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 2)],
            [2, ("공퍼", 3)],
            [2, ("무공퍼", 3)],
            [2, ("공퍼", 2), ("무공퍼", 1)],
            [2, ("공퍼", 1), ("무공퍼", 2)],
            [2, ],
            [1, ("공퍼", 3)],
            [1, ("무공퍼", 3)],
            [1, ],
        ]
        search_presets_artifact_supporter = [        
            [3, ("아군회복", 3), ("아군보호막", 3)],
            [2, ("아군회복", 3), ("아군보호막", 3)],
        ]
        SHEET_NAME = "4T 귀걸이 검색기"
    elif part == "반지":
        search_presets_antique_dealer = [
          [3, ("치적", 3), ("치피", 3)],
          [3, ("치적", 2), ("치피", 3)],
          [3, ("치적", 3), ("치피", 2)],
          [3, ("치적", 1), ("치피", 3)],
          [3, ("치적", 2), ("치피", 2)],
          [3, ("치적", 3), ("치피", 1)],
          [3, ("치피", 3)],
          [3, ("치적", 1), ("치피", 2)],
          [3, ("치적", 3)],
          [3, ("치적", 2), ("치피", 1)],
          [3, ("치피", 2)],
          [3, ("치적", 1), ("치피", 1)],
          [3, ("치적", 2)],
          [3, ("치피", 1)],
          [3, ("치적", 1)],
          [3, ],
          [2, ("치적", 3), ("치피", 3)],
          [2, ("치적", 2), ("치피", 3)],
          [2, ("치적", 3), ("치피", 2)],
          [2, ("치적", 1), ("치피", 3)],
          [2, ("치적", 2), ("치피", 2)],
          [2, ("치적", 3), ("치피", 1)],
          [2, ("치피", 3)],
          [2, ("치적", 1), ("치피", 2)],
          [2, ("치적", 3)],
          [2, ("치적", 2), ("치피", 1)],
          [2, ("치피", 2)],
          [2, ("치적", 1), ("치피", 1)],
          [2, ("치적", 2)],
          [2, ("치피", 1)],
          [2, ("치적", 1)],
          [2, ],
          [1, ("치피", 3)],
          [1, ("치적", 3)],
          [1, ("치피", 2)],
          [1, ("치적", 2)],
          [1, ("치피", 1)],
          [1, ("치적", 1)],
          [1, ],
      ]
        search_presets_antique_supporter = [
            [3, ("아공강", 3), ("아피강", 3)],
            [3, ("아공강", 3), ("아피강", 2)],
            [3, ("아공강", 2), ("아피강", 3)],
            [3, ("아공강", 3), ("아피강", 1)],
            [3, ("아공강", 1), ("아피강", 3)],
            [3, ("아공강", 2), ("아피강", 2)],
            [3, ("아공강", 3)],
            [2, ("아공강", 3), ("아피강", 3)],
            [2, ("아공강", 3), ("아피강", 2)],
            [2, ("아공강", 2), ("아피강", 3)],
            [2, ("아공강", 3), ("아피강", 1)],
            [2, ("아공강", 1), ("아피강", 3)],
            [2, ("아공강", 2), ("아피강", 2)],
            [2, ("아공강", 3)],
            [1, ("아공강", 3)],
            [1, ("아피강", 3)],
        ]
        search_presets_artifact_dealer = [
            [3, ("치적", 3), ("치피", 3)],
            [3, ("치적", 2), ("치피", 3)],
            [3, ("치적", 3), ("치피", 2)],
            [3, ("치적", 1), ("치피", 3)],
            [3, ("치적", 2), ("치피", 2)],
            [3, ("치적", 3), ("치피", 1)],
            [3, ("치피", 3)],
            [3, ("치적", 3)],
            [3, ],
            [2, ("치적", 3), ("치피", 3)],
            [2, ("치적", 2), ("치피", 3)],
            [2, ("치적", 3), ("치피", 2)],
            [2, ("치적", 1), ("치피", 3)],
            [2, ("치적", 2), ("치피", 2)],
            [2, ("치적", 3), ("치피", 1)],
            [2, ("치피", 3)],
            [2, ("치적", 3)],
            [2, ],
            [1, ("치피", 3)],
            [1, ("치적", 3)],
            [1, ],
        ]
        search_presets_artifact_supporter = [
            [3, ("아공강", 3), ("아피강", 3)],
            [3, ("아공강", 3), ("아피강", 2)],
            [3, ("아공강", 2), ("아피강", 3)],
            [3, ("아공강", 3), ("아피강", 1)],
            [3, ("아공강", 1), ("아피강", 3)],
            [3, ("아공강", 2), ("아피강", 2)],
            [2, ("아공강", 3), ("아피강", 3)],
            [2, ("아공강", 3), ("아피강", 2)],
            [2, ("아공강", 2), ("아피강", 3)],
            [2, ("아공강", 3), ("아피강", 1)],
            [2, ("아공강", 1), ("아피강", 3)],
            [2, ("아공강", 2), ("아피강", 2)],
            [1, ("아공강", 3)],
            [1, ("아피강", 3)],
        ]
        SHEET_NAME = "4T 반지 검색기"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_to_sheet = [current_time]

    try:
        evaluate_functions = load_evaluate_functions()
    except (EOFError, FileNotFoundError) as e:
        print(e)
        evaluate_functions = copy.deepcopy(evaluate_functions_skeleton)
        save_evaluate_functions(evaluate_functions)

    evaluate_functions["time"] = current_time
    data_to_sheet_temp, evaluate_functions = search_part_and_update_subroutine("고대", "딜러", part, search_presets_antique_dealer, evaluate_functions)
    data_to_sheet += data_to_sheet_temp
    data_to_sheet_temp, evaluate_functions = search_part_and_update_subroutine("고대", "서폿", part, search_presets_antique_supporter, evaluate_functions)
    data_to_sheet += data_to_sheet_temp
    data_to_sheet_temp, evaluate_functions = search_part_and_update_subroutine("유물", "딜러", part, search_presets_artifact_dealer, evaluate_functions)
    data_to_sheet += data_to_sheet_temp
    data_to_sheet_temp, evaluate_functions = search_part_and_update_subroutine("유물", "서폿", part, search_presets_artifact_supporter, evaluate_functions)
    data_to_sheet += data_to_sheet_temp

    save_evaluate_functions(evaluate_functions)

    if not first_empty_cell:
        first_empty_cell = find_first_empty_cell(service, SPREADSHEET_ID, SHEET_NAME, "A")
    
    result = service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{SHEET_NAME}!{"A"}{first_empty_cell}',
        valueInputOption='USER_ENTERED',
        body={'values': [data_to_sheet]}
    ).execute()

    return first_empty_cell + 1

if __name__ == "__main__":
    necklace_row = None
    earring_row = None
    ring_row = None
    
    while True:
        necklace_row = search_part_and_update("목걸이", necklace_row)
        # update_evaluate_functions("necklace")
        time.sleep(60)
        earring_row = search_part_and_update("귀걸이", earring_row)
        time.sleep(60)
        ring_row = search_part_and_update("반지", ring_row)
        time.sleep(7080)


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

