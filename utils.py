import re
import requests
import json
import copy
import os
import time
import pickle
from datetime import datetime
"""
Second 45 공퍼(0.4, 0.95, 1.55), 53 깡공(80, 195, 390), 44 낙인력(2.15, 4.8, 8), 46 무공퍼(0.8, 1.8, 3)
Second 54 깡무공(195, 480, 960), 57 상태이상공격지속시간(0.2, 0.5, 1), 43 아덴게이지(1.6, 3.6, 6)
Second 51 아공강(1.35, 3, 5), 52 아피강(2, 4.5, 7.5), 42 적주피(0.55, 1.2, 2), 58 전투중생회(10, 25, 50)
Second 56 최마(6, 15, 30), 55 최생(1300, 3250, 6500), 41 추피(0.7, 1.6, 2.6), 49 치적(0.4, 0.95, 1.55)
Second 50 치피(1.1, 2.4, 4.0), 48 아군보호막(0.95, 2.1, 3.5), 47 아군회복(0.95, 2.1, 3.5)
그런데 그냥 하옵, 중옵, 상옵을 1, 2, 3으로 두면 된다.
Quality: 품질
Grade: 고대, 유물 등
LeveL: 연마 단계
Scale: 하옵 중옵 상옵

"""
number_to_scale = {
    # 하중상을 뭐라고 할 질 모르겠어서(level, grade는 이미 있다...) 일단 scale로 두었다.
    # 공격력 관련
    "공퍼": {
        0.4: 1,
        0.95: 2,
        1.55: 3,
    },
    "깡공": {
        80.0: 1,
        195.0: 2,
        390.0: 3,
    },
    "무공퍼": {
        0.8: 1,
        1.8: 2,
        3.0: 3,
    },
    "깡무공": {
        195.0: 1,
        480.0: 2,
        960.0: 3,
    },
    # 치명타 관련
    "치적": {
        0.4: 1,
        0.95: 2,
        1.55: 3,
    },
    "치피": {
        1.1: 1,
        2.4: 2,
        4.0: 3,
    },
    # 피해량 관련
    "추피": {
        0.7: 1,
        1.6: 2,
        2.6: 3,
    },
    "적주피": {
        0.55: 1,
        1.2: 2,
        2.0: 3,
    },
    # 서포터 관련
    "아덴게이지": {
        1.6: 1,
        3.6: 2,
        6.0: 3,
    },
    "낙인력": {
        2.15: 1,
        4.8: 2,
        8.0: 3,
    },
    "아군회복": {
        0.95: 1,
        2.1: 2,
        3.5: 3,
    },
    "아군보호막": {
        0.95: 1,
        2.1: 2,
        3.5: 3,
    },
    "아공강": {
        1.35: 1,
        3.0: 2,
        5.0: 3,
    },
    "아피강": {
        2.0: 1,
        4.5: 2,
        7.5: 3,
    },
    # 기타 스탯
    "최마": {
        6.0: 1,
        15.0: 2,
        30.0: 3,
    },
    "최생": {
        1300.0: 1,
        3250.0: 2,
        6500.0: 3,
    },
    "상태이상공격지속시간": {
        0.2: 1,
        0.5: 2,
        1.0: 3,
    },
    "전투중생회": {
        10.0: 1,
        25.0: 2,
        50.0: 3,
    },
}
# 무공퍼, 공퍼, 깡무공, 깡공은 제외
ABB_TO_FULLNAME = {
    "추피": "추가 피해",
    "적주피": "적에게 주는 피해 증가",
    "아덴게이지": "세레나데, 신성, 조화 게이지 획득량 증가",
    "낙인력": "낙인력",
    "아군회복": "파티원 회복 효과",
    "아군보호막": "파티원 보호막 효과",
    "치적": "치명타 적중률",
    "치피": "치명타 피해",
    "아공강": "아군 공격력 강화 효과",
    "아피강": "아군 피해량 강화 효과",
    "최생": "최대 생명력",
    "최마": "최대 마나",
    "상태이상공격지속시간": "상태이상 공격 지속시간",
    "전투중생회": "전투 중 생명력 회복량"
}

FULLNAME_TO_ABB = {value: key for key, value in ABB_TO_FULLNAME.items()}

def parse_datetime(date_string):
    match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?', date_string)
    if match:
        base_time = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
        if match.group(2):
            microseconds = int(match.group(2)[1:].ljust(6, '0')[:6])
            return base_time.replace(microsecond=microseconds)
        return base_time
    raise ValueError(f"Invalid datetime format: {date_string}")

def find_first_empty_cell(service, SPREADSHEET_ID, sheet_name, column="A"):
    # 지정된 열의 모든 셀 가져오기
    SHEET_NAME = sheet_name
    range_name = f'{SHEET_NAME}!{column}:{column}'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    values = result.get('values', [])

    # 첫 번째 빈 셀의 행 번호 찾기
    for i, value in enumerate(values, start=1):
        if not value:
            return i

    # 모든 셀이 채워져 있으면 다음 행 반환
    return len(values) + 1

def find_last_nonempty_cell(service, SPREADSHEET_ID, sheet_name, column="A"):
    # 지정된 열의 모든 셀 가져오기
    SHEET_NAME = sheet_name
    range_name = f'{SHEET_NAME}!{column}:{column}'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    values = result.get('values', [])

    # 첫 번째 빈 셀의 행 번호 찾기
    for i, value in enumerate(values, start=1):
        if not value:
            return i - 1

    # 모든 셀이 채워져 있으면 마지막 행 반환
    return len(values)

option_dict = {
    "추피": 41,         # "추가 피해"
    "적주피": 42,       # "적에게 주는 피해"
    "아덴게이지": 43,    # "세레나데, 신성, 조화 게이지 획득량 증가"
    "낙인력": 44,       # "낙인력"
    "공퍼": 45,         # "공격력 "
    "무공퍼": 46,       # "무기 공격력 "
    "아군회복": 47,     # "파티원 회복 효과"
    "아군보호막": 48,    # "파티원 보호막 효과"
    "치적": 49,         # "치명타 적중률"
    "치피": 50,         # "치명타 피해"
    "아공강": 51,       # "아군 공격력 강화 효과"
    "아피강": 52,       # "아군 피해량 강화 효과"
    "깡공": 53,         # "무기 공격력 "
    "깡무공": 54,       # "공격력 " # 뒤에 띄어 쓰기 있음. 깡무공, 깡공, 무공퍼도 마찬가지
    "최생": 55,         # "최대 생명력"
    "최마": 56,         # "최대 마나"
    "상태이상공격지속시간": 57, # 상태이상 공격 지속시간
    "전투중생회": 58,   # "전투 중 생명력 회복량"
}

option_dict_bracelet_first = {
    "팔찌 기본 효과": 1,
    "전투 특성": 2,
    "팔찌 옵션 수량": 4,
    "팔찌 특수 효과": 5,
}

option_dict_bracelet_second = {
    "고정 효과 수량": 1,
    "부여 효과 수량": 2,
    "힘": 3,
    "민첩": 4,
    "지능": 5,
    "체력": 6,
    "치명": 15,
    "특화": 16,
    "제압": 17,
    "신속": 18,
    "인내": 19,
    "숙련": 20,
    "강타": 39,
    "공격 및 이동 속도 증가": 60,
    "긴급 수혈": 33,
    "돌진": 38,
    "마나회수": 36,
    "마법 방어력": 2,
    "멸시": 29,
    "무시": 30,
    "물리 방어력": 1,
    "반격": 28,
    "반전": 31,
    "속공": 26,
    "시드 이하 받는 피해 감소": 62,
    "시드 이하 주는 피해 증가": 61,
    "앵콜": 35,
    "오뚝이": 37,
    "응급 처치": 34,
    "이동기 및 기상기 재사용 대기시간 감소": 63,
    "전투 자원 회복량": 59,
    "전투 중 생명력 회복량": 6,
    "최대 마나": 4,
    "최대 생명력": 3,
    "타격": 40,
    "투자": 27,
    "피격 이상 면역 효과": 64,
    "회생": 32,
}

necklace_only_list = [
    "추피", "적주피", "아덴게이지", "낙인력"
]

dmg_increment_dict = {
    "추피": {
        "0.7": 0.495,
        "1.6": 1.131,
        "2.6": 1.839,
    },
    "적주피": {
        "0.55": 0.55,
        "1.2": 1.2,
        "2.0": 2.0,
    },
    "공퍼": {
        "0.4": 0.358,
        "0.95": 0.850,
        "1.55": 1.387,
    },
    "무공퍼": {
        "0.8": 0.306,
        "1.8": 0.686,
        "3.0": 1.14,
    },
    "치피": {
        "1.1": 0.365,
        "2.4": 0.797,
        "4.0": 1.328,
    },
    "치적": {
        "0.4": 0.273,
        "0.95": 0.648,
        "1.55": 1.057,
    },
    "깡공": {   # 인식 상 데미지 증가 비율 계수를 0.5정도로 잡았다...
        "80.0": 0.059*0.5,
        "195.0": 0.144*0.5,
        "390.0": 0.288*0.5,
    },
    "깡무공": {
        "195.0": 0.061*0.5,
        "480.0": 0.151*0.5,
        "960.0": 0.302*0.5,
    },
    "품질": {  # 1당 힘민지 기대 증가량으로 인한 딜상승.. 인데 좀 낮출 필요가 있다
        "목걸이": 0.00785*0.5,
        "귀걸이": 0.00610*0.5,
        "반지": 0.00567*0.5
    }
}

effective_option_list = dmg_increment_dict.keys()

level_enpoint = {
    "고대": {
        0: 0,
        1: 2,
        2: 5,
        3: 9,
    },
    "유물": {
        0: 0,
        1: 1,
        2: 3,
        3: 6,
    },
}

def do_search(url, headers, post_body, timeout=10, max_retries=6, delay=10, error_log=True):
    """_summary_

    Args:
        url: _description_
        headers: _description_
        post_body: _description_
        timeout: _description_. Defaults to 10.
        max_retries: _description_. Defaults to 3.
        delay: _description_. Defaults to 60.

    Returns:
        _description_
    """
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=post_body, timeout=timeout)
            response.raise_for_status()
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError, requests.exceptions.ReadTimeout) as e:
            if error_log:
                print(f"시도 {attempt + 1}/{max_retries} 실패: {e}")
            if attempt + 1 == max_retries:
                raise
            time.sleep(delay)

def fix_dup_options(item):
    """ For dealer accessory, fix duplicated options and long names

    Args:
        item: _description_
    """
    options = item["Options"]
    for option in options:
        option_name = option["OptionName"]
        if option_name == "공격력 ":
            if option["IsValuePercentage"]:
                option["OptionName"] = "공퍼"
            else:
                option["OptionName"] = "깡공"
        if option_name == "무기 공격력 ":
            if option["IsValuePercentage"]:
                option["OptionName"] = "무공퍼"
            else:
                option["OptionName"] = "깡무공"
        if option_name in FULLNAME_TO_ABB.keys():
            option["OptionName"] = FULLNAME_TO_ABB[option_name]

def extract_supporter_options(item):
    result = []
    options = item["Options"]
    for option in options:
        option_name = option["OptionName"]
        if (option_name == "아덴게이지") or (option_name == "아군회복") or (option_name == "아공강"):
            result.append((option_name, number_to_scale[option_name][option["Value"]]))
    for option in options:
        option_name = option["OptionName"]
        if (option_name == "낙인력") or (option_name == "아군보호막") or (option_name == "아피강"):
            result.append((option_name, number_to_scale[option_name][option["Value"]]))
    return tuple(result)

def calc_dmg_increment_percent(item):
    """ Caulcate damage increment percent of an item, as dealer..

    Args:
        item: dictionary: the optionNames should be fixed by fix_dup_options.
        That is, it must be called after fix_dup_options.
    """
    dmg = 1.0
    options = item["Options"]
    for option in options:
      option_name = option["OptionName"]
      if option_name in effective_option_list:
        dmg *= 1 + 0.01 * dmg_increment_dict[option_name][str(option["Value"])]
    if "목걸이" in item["Name"]:
        part = "목걸이"
    elif "귀걸이" in item["Name"]:
        part = "귀걸이"
    elif "반지" in item["Name"]:
        part = "반지"

    # 품질 고려
    dmg *= 1 + 0.01 * dmg_increment_dict["품질"][part] * (item["GradeQuality"] - 67)
        # print(dmg)
    dmg_increment_percent = 100.0 * (dmg - 1)
    return dmg_increment_percent

SEARCH_INTERVAL = 0.61