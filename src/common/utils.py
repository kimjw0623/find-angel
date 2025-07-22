from datetime import datetime
import re
from typing import List, Dict, Optional, Any

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

def fix_dup_options(item):
    """ For dealer accessory, fix duplicated options and long names

    Args:
        item: _description_
    """
    from src.common.config import config
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
        if option_name in config.FULLNAME_TO_ABB.keys():
            option["OptionName"] = config.FULLNAME_TO_ABB[option_name]

def extract_supporter_options(item):
    from src.common.config import config
    result = []
    options = item["Options"]
    for option in options:
        option_name = option["OptionName"]
        if (option_name == "아덴게이지") or (option_name == "아군회복") or (option_name == "아공강"):
            result.append((option_name, config.number_to_scale[option_name][option["Value"]]))
    for option in options:
        option_name = option["OptionName"]
        if (option_name == "낙인력") or (option_name == "아군보호막") or (option_name == "아피강"):
            result.append((option_name, config.number_to_scale[option_name][option["Value"]]))
    return tuple(result)

def calc_dmg_increment_percent(item):
    """ Calculate damage increment percent of an item, as dealer.

    Args:
        item: dictionary: the optionNames should be fixed by fix_dup_options.
        That is, it must be called after fix_dup_options.
    """
    from src.common.config import config
    dmg = 1.0
    options = item["Options"]
    for option in options:
      option_name = option["OptionName"]
      if option_name in config.dmg_increment_dict:
        dmg *= 1 + 0.01 * config.dmg_increment_dict[option_name][str(option["Value"])]
    if "목걸이" in item["Name"]:
        part = "목걸이"
    elif "귀걸이" in item["Name"]:
        part = "귀걸이"
    elif "반지" in item["Name"]:
        part = "반지"

    # 품질 고려
    dmg *= 1 + 0.01 * config.dmg_increment_dict["품질"][part] * (item["GradeQuality"] - 67)
    dmg_increment_percent = 100.0 * (dmg - 1)
    return dmg_increment_percent

def get_current_timestamp() -> str:
    """현재 시간을 YYYYMMDD_HHMM 형식으로 반환"""
    return datetime.now().strftime("%Y%m%d_%H%M")

def create_basic_search_request(grade: str, part: str, enhancement_level: Optional[int] = None, 
                               quality: Optional[int] = None, page_no: int = 1) -> Dict[str, Any]:
    """
    기본 경매장 검색 요청 데이터 생성
    
    Args:
        grade: 등급 (고대, 유물)
        part: 부위 (목걸이, 귀걸이, 반지, 팔찌)
        enhancement_level: 연마 단계
        quality: 품질
        page_no: 페이지 번호
    """
    from src.common.config import config
    category_code = config.CATEGORY_CODES[part]
    
    return {
        "ItemLevelMin": 0,
        "ItemLevelMax": 1800,
        "ItemGradeQuality": quality,
        "ItemUpgradeLevel": enhancement_level,
        "ItemTradeAllowCount": None,
        "SkillOptions": [{
            "FirstOption": None,
            "SecondOption": None,
            "MinValue": None,
            "MaxValue": None
        }],
        "EtcOptions": [],
        "Sort": "BIDSTART_PRICE",
        "CategoryCode": category_code,
        "CharacterClass": "",
        "ItemTier": 4,
        "ItemGrade": grade,
        "ItemName": "",
        "PageNo": page_no,
        "SortCondition": "ASC"
    }

def add_search_option(first_option: str, second_option: str, min_value: int, max_value: Optional[int] = None) -> Dict[str, Any]:
    """검색 옵션 생성 (문자열을 숫자 코드로 매핑)"""
    from src.common.config import config
    if max_value is None:
        max_value = min_value
        
    return {
        "FirstOption": config.SEARCH_OPTION_CODES[first_option],
        "SecondOption": config.SEARCH_OPTION_CODES[second_option],
        "MinValue": min_value,
        "MaxValue": max_value
    }

def calculate_reasonable_price(prices: List[int], min_samples: int = 10) -> Optional[int]:
    """경매장 가격 데이터에서 IQR을 이용해 이상치를 제거하고 최저가를 계산합니다."""
    import numpy as np
    
    real_min_sample = 2
    if len(prices) < min_samples:
        if len(prices) < real_min_sample:
            print(f"가격분석 | 데이터 정말 부족: {len(prices)}개/{min_samples}개")
            return 0
        else:
            print(f"가격분석 | 데이터 부족하지만: {len(prices)}개/{min_samples}개, 최저가에서 두 번째 반환 {prices[1]:,}")
            return prices[1]
    
    q1, q3 = np.percentile(prices, [25, 75])
    iqr = q3 - q1
    lower_bound, upper_bound = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    filtered_prices = [p for p in prices if lower_bound <= p <= upper_bound]
    
    if filtered_prices:
        min_price = min(filtered_prices)
        print(f"가격분석 | 원본: {len(prices)}개 {min(prices):,}~{max(prices):,} | Q1/Q2/Q3: {int(q1):,}/{int(np.median(prices)):,}/{int(q3):,} | 이상치제거: {len(prices)-len(filtered_prices)}개 | 최종최저가: {min_price:,}")
        return min_price
    
    print("데이터 없음")
    return 0

def normalize_common_option_value(option_name: str, option_value: float, config) -> float:
    """
    Common 옵션 값을 0~1로 정규화
    
    Args:
        option_name: 옵션 이름 ("깡공", "최생" 등)
        option_value: 실제 옵션 값 (80, 1300 등)
        config: Config 인스턴스
        
    Returns:
        0.0 ~ 1.0 사이의 정규화된 값
    """
    if option_name not in config.common_options:
        return 0.0  # 해당 옵션이 없으면 0
        
    values = config.common_options[option_name]
    max_value = max(values)  # 최대값으로 정규화
    
    # 값이 범위를 벗어나는 경우 처리
    if option_value <= 0:
        return 0.0
    if option_value >= max_value:
        return 1.0
    
    return option_value / max_value

def extract_common_option_features(item, role: str, config) -> Dict[str, float]:
    """
    아이템에서 역할별 Common 옵션들을 추출하고 정규화된 feature vector 생성
    
    Args:
        item: AuctionAccessory 인스턴스
        role: "dealer" 또는 "support"
        config: Config 인스턴스
        
    Returns:
        Dict[옵션명, 정규화된값] (0~1)
    """
    features = {}
    related_options = config.role_related_options[role]
    
    # 모든 관련 옵션을 0으로 초기화
    for opt_name in related_options:
        features[opt_name] = 0.0
    
    # base_stat = "힘민지" 처리
    if "힘민지" in related_options and hasattr(item, 'base_stat') and item.base_stat:
        try:
            base_stat_ratio = calculate_base_stat_ratio(
                part=item.part,
                enhancement_level=item.level, 
                base_stat=item.base_stat,
                config=config
            )
            features["힘민지"] = base_stat_ratio
        except (ValueError, TypeError):
            features["힘민지"] = 0.0
    
    # 다른 Common 옵션들 처리
    if hasattr(item, 'raw_options'):
        for option in item.raw_options:
            opt_name = option.option_name
            if opt_name in related_options and opt_name != "힘민지":
                try:
                    normalized_value = normalize_common_option_value(
                        option_name=opt_name,
                        option_value=float(option.option_value),
                        config=config
                    )
                    features[opt_name] = normalized_value
                except (ValueError, TypeError):
                    continue
    
    return features

def calculate_base_stat_ratio(part: str, enhancement_level: int, base_stat: int, config) -> float:
    """
    악세서리의 base_stat에 따른 비율 계산 (Linear regression 모델용)
    
    Args:
        part: 부위 ("반지", "귀걸이", "목걸이")
        enhancement_level: 연마 레벨 (0-3)
        base_stat: 실제 base_stat 값
        config: Config 인스턴스
        
    Returns:
        0.0 ~ 1.0 사이의 비율 값
    """
    if part not in config.accessory_base_stat_ranges:
        raise ValueError(f"Unknown accessory part: {part}")
        
    if enhancement_level not in config.accessory_base_stat_ranges[part]:
        raise ValueError(f"Unknown enhancement level: {enhancement_level} for {part}")
    
    min_stat, max_stat = config.accessory_base_stat_ranges[part][enhancement_level]
    
    # 범위를 벗어나는 경우 처리
    if base_stat <= min_stat:
        return 0.0
    if base_stat >= max_stat:
        return 1.0
    
    # 비율 계산 (모델별로 분기 - 추후 확장용)
    model_type = config.base_stat_ratio_settings["model_type"]
    ratio = (base_stat - min_stat) / (max_stat - min_stat)
    
    if model_type == "linear":
        return ratio
    elif model_type == "quadratic":
        return ratio ** 2
    elif model_type == "sqrt":
        return ratio ** 0.5
    elif model_type == "exponential":
        # e^(-2*(1-ratio)) - e^(-2) / (1 - e^(-2))로 정규화
        import math
        return (math.exp(-2 * (1 - ratio)) - math.exp(-2)) / (1 - math.exp(-2))
    else:
        # 기본값은 linear
        return ratio

