
CATEGORYCODE_DICT = {
    "목걸이": 200010,
    "귀걸이": 200020,
    "반지": 200030,
    "팔찌": 200040
}

VALID_OPTION_DICT = {
    200020: {
        "name": "귀걸이",
        "valid_options": [45,46], # 공격%, 무공%
        "valid_option_value_dict": {
            "공격력 ": {1.55:3, 0.95:2, 0.40:1}, 
            "무기 공격력 ": {3.00:3, 1.80:2, 0.80:1},
        }
    },
    200010: {
        "name": "목걸이",
        "valid_options": [41,42] # 추피, 적추피
    }
}

def get_valid_option(item_info_dict:dict):
    """
    Item info를 받아 유효한 옵션을 추출하는 함수

    """
    # Item Info 에서 뽑을 수 있는 것: 
    # 아이템 부위 (귀걸이/반지/...)
    # 아이템 등급 (Grade:고대,유물)
    # 아이템 품질 (GradeQuality)
    # 경매 정보 (AuctionInfo: 시작 가격, 끝나는 시간 등)
    # 아이템 옵션 (Options: OptionName을 보고 유효 옵션 결정, Value를 보고 상중하 결정)

    item_type = item_info_dict.get("Name").split()[-1]
    item_type_digit = CATEGORYCODE_DICT[item_type]
    valid_option_value_dict = VALID_OPTION_DICT[item_type_digit]["valid_option_value_dict"]

    item_valid_option = dict()

    # 아이템 옵션 추출
    item_option_list = item_info_dict.get("Options",[])
    # 연마 횟수 확인
    item_remain_num = 4 - len(item_option_list)
    item_valid_option["remain_num"] = item_remain_num
    # 품질
    item_quality = item_info_dict.get("GradeQuality",0)
    item_valid_option["quality"] = item_quality
    # 교환가능횟수
    item_trade_allow_count = item_info_dict.get("AuctionInfo",{}).get("TradeAllowCount",0)
    item_valid_option["trade_allow_count"] = item_trade_allow_count

    for item_option in item_option_list:
        if item_option.get("Type") != "ACCESSORY_UPGRADE": continue
        if item_option.get("OptionName") in valid_option_value_dict:
            # 유효 옵션
            cur_valid_option_value_dict = valid_option_value_dict[item_option.get("OptionName")]
            cur_option_grade = cur_valid_option_value_dict.get(item_option.get("Value"))
            if cur_option_grade:
                item_valid_option[item_option.get("OptionName")] = cur_option_grade

    return item_valid_option