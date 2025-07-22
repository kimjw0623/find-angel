from datetime import datetime
import re
import numpy as np
from typing import List, Dict, Optional, Any, Union
from src.common.config import config

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

def normalize_option_value(option_name: str, option_value: float) -> float:
    """
    일반 옵션 값을 0~1로 정규화 ("힘민지" 제외)
    
    Args:
        option_name: 옵션 이름 ("깡공", "최생" 등)
        option_value: 실제 옵션 값 (80, 1300 등)
        
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

def extract_common_option_features(item, role: str) -> Dict[str, float]:
    """
    아이템에서 역할별 Common 옵션들을 추출하고 정규화된 feature vector 생성 - Dict와 AuctionAccessory 모두 지원
    
    Args:
        item: AuctionAccessory 인스턴스 또는 Dict 객체
        role: "dealer" 또는 "support"
        
    Returns:
        Dict[옵션명, 정규화된값] (0~1)
    """
    features = {}
    related_options = config.role_related_options[role]
    
    # 모든 관련 옵션을 0으로 초기화
    for opt_name in related_options:
        features[opt_name] = 0.0
    
    # AuctionAccessory 객체인지 Dict인지 확인
    if hasattr(item, 'grade'):  # AuctionAccessory 객체
        # base_stat = "힘민지" 처리
        if "힘민지" in related_options and hasattr(item, 'base_stat') and item.base_stat:
            try:
                base_stat_ratio = normalize_base_stat_value(
                    part=item.part,
                    enhancement_level=item.level, 
                    base_stat=item.base_stat
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
                        normalized_value = normalize_option_value(
                            option_name=opt_name,
                            option_value=float(option.option_value)
                        )
                        features[opt_name] = normalized_value
                    except (ValueError, TypeError):
                        continue
                        
    else:  # Dict 객체
        # 부위 추출
        if "목걸이" in item["Name"]:
            part = "목걸이"
        elif "귀걸이" in item["Name"]:
            part = "귀걸이"
        elif "반지" in item["Name"]:
            part = "반지"
        else:
            part = "unknown"
        
        # base_stat = "힘민지" 처리 (Dict에서는 힘, 민첩, 지능 중 하나)
        if "힘민지" in related_options:
            try:
                base_stat_value = 0
                for opt in item["Options"]:
                    if opt["OptionName"] in ["힘", "민첩", "지능"]:
                        base_stat_value = opt["Value"]
                        break  # 첫 번째로 찾은 것 사용
                
                if base_stat_value > 0:
                    base_stat_ratio = normalize_base_stat_value(
                        part=part,
                        enhancement_level=item["AuctionInfo"]["UpgradeLevel"], 
                        base_stat=base_stat_value,
                    )
                    features["힘민지"] = base_stat_ratio
            except (ValueError, TypeError):
                features["힘민지"] = 0.0
        
        # 다른 Common 옵션들 처리
        for option in item["Options"]:
            opt_name = option["OptionName"]
            if opt_name in related_options and opt_name != "힘민지":
                try:
                    normalized_value = normalize_option_value(
                        option_name=opt_name,
                        option_value=float(option["Value"])
                    )
                    features[opt_name] = normalized_value
                except (ValueError, TypeError):
                    continue
    
    return features

def normalize_base_stat_value(part: str, enhancement_level: int, base_stat: int) -> float:
    """
    악세서리의 base_stat에 따른 비율 계산 (Linear regression 모델용)
    
    Args:
        part: 부위 ("반지", "귀걸이", "목걸이")
        enhancement_level: 연마 레벨 (0-3)
        base_stat: 실제 base_stat 값
        
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

def create_auction_search_data(page_no: int, category_code: int = None) -> Dict:
    """item_checker용 경매장 검색 데이터 생성 (config 기반)
    
    Args:
        page_no: 페이지 번호
        category_code: 카테고리 코드 (None이면 config 기본값 사용)
    
    Returns:
        API 요청용 검색 데이터
    """
    
    search_params = config.item_checker_settings["search_params"]
    
    return {
        "ItemLevelMin": search_params["ItemLevelMin"],
        "ItemLevelMax": search_params["ItemLevelMax"],
        "ItemGradeQuality": None,
        "Sort": search_params["Sort"],
        "CategoryCode": category_code or search_params["CategoryCode"],
        "CharacterClass": "",
        "ItemTier": search_params["ItemTier"],
        "ItemGrade": "",
        "PageNo": page_no,
        "SortCondition": search_params["SortCondition"],
        "EtcOptions": [
            {
                "FirstOption": "",
                "SecondOption": "",
                "MinValue": "",
                "MaxValue": "",
            },
        ],
    }

def create_accessory_pattern_key(item: Union[Dict, Any], role: str) -> str:
    """아이템에서 pattern_key 생성 (악세서리용) - Dict와 AuctionAccessory 모두 지원"""
    
    # AuctionAccessory 객체인지 Dict인지 확인
    if hasattr(item, 'grade'):  # AuctionAccessory 객체
        grade = item.grade
        level = item.level
        part = item.part
        options = [(opt.option_name, opt.option_value) for opt in item.raw_options]
    else:  # Dict 객체
        grade = item["Grade"]
        level = item["AuctionInfo"]["UpgradeLevel"]
        # 아이템 이름에서 부위 추출
        if "목걸이" in item["Name"]:
            part = "목걸이"
        elif "귀걸이" in item["Name"]:
            part = "귀걸이"
        elif "반지" in item["Name"]:
            part = "반지"
        options = [(opt["OptionName"], opt["Value"]) for opt in item["Options"]]
        
    part_options = config.exclusive_options[part]
    role_options = []
    
    for opt_name, opt_value in options:
        # 해당 역할의 옵션인지 확인
        if role in part_options and opt_name in part_options[role]:
            role_options.append((opt_name, opt_value))
    
    # 키 생성 (pattern_generator와 동일)
    if role_options:
        return f"{grade}:{part}:{level}:{sorted(role_options)}"
    else:
        return f"{grade}:{part}:{level}:base"

def create_bracelet_pattern_key(item: Union[Dict, Any]) -> str:
    """팔찌 아이템에서 pattern_key 생성 - Dict와 AuctionBracelet 모두 지원"""
    
    # 유효 스탯들 정의
    valid_combat_stats = ["치명", "특화", "신속"]
    jeinsuk_stats = ["제압", "인내", "숙련"]
    valid_base_stats = ["힘", "민첩", "지능"]
    
    # 전투 특성 분류
    valid_combat = []
    jeinsuk_combat = []
    invalid_option = []  # special_effects 중 공이속 아닌 것들
    
    # AuctionBracelet 객체인지 Dict인지 확인
    if hasattr(item, 'grade'):  # AuctionBracelet 객체
        grade = item.grade
        extra_option_count = item.extra_option_count
                
        for stat in item.combat_stats:
            stat_value = float(stat.value) if stat.value is not None else 0.0
            if stat_value > 0:
                if stat.stat_type in valid_combat_stats:
                    valid_combat.append((stat.stat_type, stat_value))
                elif stat.stat_type in jeinsuk_stats:
                    jeinsuk_combat.append((stat.stat_type, stat_value))
        
        # 기본 스탯 분류
        valid_base = []
        for stat in item.base_stats:
            stat_value = float(stat.value) if stat.value is not None else 0.0
            if stat_value > 0 and stat.stat_type in valid_base_stats:
                valid_base.append((stat.stat_type, stat_value))
        
        # 공격속도 효과 확인 및 잡옵 처리
        speed_value = 0
        if item.special_effects:
            for effect in item.special_effects:
                if "공격 및 이동 속도 증가" in str(effect.effect_type):
                    speed_value = float(effect.value)
                else:
                    # 공이속이 아닌 special_effects는 잡옵
                    invalid_option.append(("잡옵", 0))
        
    else:  # Dict 객체
        grade = item["Grade"]
        
        # 기본 스탯 분류
        valid_base = []
        
        # 공격속도 효과 확인
        speed_value = 0
        
        # 부여 효과 수량
        extra_option_count = 0

        for opt in item["Options"]:
            opt_name = opt["OptionName"]
            opt_value = opt["Value"]
            opt_type = opt.get("Type", "STAT")
                
            if opt_type == "BRACELET_RANDOM_SLOT":
                extra_option_count = int(opt_value)
            elif opt_type == "STAT":
                    if opt_name in valid_combat_stats:
                        valid_combat.append((opt_name, opt_value))
                    elif opt_name in jeinsuk_stats:
                        jeinsuk_combat.append((opt_name, opt_value))
                    elif opt_name in valid_base_stats:
                        valid_base.append((opt_name, opt_value))
            elif opt_type == "BRACELET_SPECIAL_EFFECTS":
                # 특수 효과 - 공격속도 확인 및 잡옵 처리
                if "공격 및 이동 속도 증가" in opt_name:
                    speed_value = opt_value
                else:
                    # 공이속이 아닌 특수 효과는 잡옵
                    invalid_option.append((opt_name, 0))
    
    # 정렬된 스탯 리스트 생성
    all_stats = []
    
    # 유효한 전투 특성 추가 (반올림 적용)
    for stat_name, stat_value in valid_combat:
        rounded_value = _round_combat_stat(grade, stat_value)
        all_stats.append((stat_name, rounded_value))
    
    # 유효한 기본 특성 추가 (반올림 적용)
    for stat_name, stat_value in valid_base:
        rounded_value = _round_base_stat(grade, stat_value)
        all_stats.append((stat_name, rounded_value))
    
    # 공격속도 추가 (실제 값 사용)
    if speed_value > 0:
        all_stats.append(("공이속", int(speed_value)))
    
    # 제인숙 스탯 추가 (모두 "제인숙"으로 통합, 값은 0)
    for stat_name, _ in jeinsuk_combat:
        all_stats.append(("제인숙", 0))
    
    # 잡옵 스탯 추가 (값은 0으로 통일)
    for stat_name, _ in invalid_option:
        all_stats.append(("잡옵", 0))
    
    # 정렬: 스탯명 기준으로 정렬 (값이 동일할 때 일관성 확보)
    sorted_stats = tuple(sorted(all_stats, key=lambda x: (x[0], x[1])))
    
    # pattern_key 생성: "grade:sorted_stats:extra_slots"
    pattern_key = f"{grade}:{str(sorted_stats)}:{extra_option_count}"
    return pattern_key

def _round_combat_stat(grade: str, value: float) -> int:
    """전투특성 값을 기준값으로 내림 - pattern_generator와 동일"""
    
    thresholds = config.bracelet_settings["combat_stat_thresholds"]
    combat_bonus = config.bracelet_settings["ancient_combat_stat_bonus"] if grade == "고대" else 0
    adjusted_thresholds = [threshold + combat_bonus for threshold in thresholds]

    # 내림 방식: 값보다 작거나 같은 가장 큰 threshold 반환
    for i in range(len(adjusted_thresholds) - 1, -1, -1):
        if value >= adjusted_thresholds[i]:
            return adjusted_thresholds[i]
    return adjusted_thresholds[0]  # 모든 threshold보다 작으면 최소값

def _round_base_stat(grade: str, value: float) -> int:
    """기본스탯 값을 기준값으로 내림 - pattern_generator와 동일"""
    
    thresholds = config.bracelet_settings["base_stat_thresholds"]
    base_stat_bonus = config.bracelet_settings["ancient_base_stat_bonus"] if grade == "고대" else 0
    adjusted_thresholds = [threshold + base_stat_bonus for threshold in thresholds]

    # 내림 방식: 값보다 작거나 같은 가장 큰 threshold 반환
    for i in range(len(adjusted_thresholds) - 1, -1, -1):
        if value >= adjusted_thresholds[i]:
            return adjusted_thresholds[i]
    return adjusted_thresholds[0]  # 모든 threshold보다 작으면 최소값


