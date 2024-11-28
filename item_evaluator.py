import time
import threading
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from database import *
from utils import *
from market_price_cache import MarketPriceCache
from sqlalchemy.orm import aliased
from discord_utils import send_discord_message

class ItemEvaluator:
    def __init__(self, price_cache, debug=False):
        self.debug = debug
        self.price_cache = price_cache
        self.last_check_time = self.price_cache.get_last_update_time()
        
        # 캐시 업데이트 체크 스레드 시작
        self._stop_flag = threading.Event()
        self._update_check_thread = threading.Thread(
            target=self._check_cache_updates,
            name="CacheUpdateChecker"
        )
        self._update_check_thread.daemon = True
        self._update_check_thread.start()

    def _check_cache_updates(self):
        """주기적으로 캐시 파일 업데이트 확인"""
        while not self._stop_flag.is_set():
            try:
                cache_update_time = self.price_cache.get_last_update_time()
                
                # 캐시 파일이 더 최신이면 리로드
                if (cache_update_time and 
                    (not self.last_check_time or cache_update_time > self.last_check_time)):
                    if self.debug:
                        print(f"New cache update detected: {cache_update_time}")
                    
                    # 캐시 리로드
                    self.price_cache._load_cache()
                    self.last_check_time = cache_update_time
                    
                    if self.debug:
                        print("Cache reloaded successfully")
            
            except Exception as e:
                if self.debug:
                    print(f"Error checking cache updates: {e}")
            
            # 1분마다 체크
            time.sleep(60)
            
    def _get_reference_options(self, item: Dict, part: str) -> Dict[str, Any]:
        """
        아이템의 옵션들을 타입별로 분류
        
        분류 기준:
        - dealer_exclusive: 각 부위별 딜러 전용 특수 옵션
        * 목걸이: 추피/적주피
        * 귀걸이: 공퍼/무공퍼
        * 반지: 치적/치피
        
        - dealer_bonus: 딜러용 보너스 옵션
        * 깡공, 깡무공
        
        - support_exclusive: 각 부위별 서포터 전용 특수 옵션
        * 목걸이: 아덴게이지/낙인력
        * 귀걸이: 무공퍼
        * 반지: 아공강/아피강
        
        - support_bonus: 서포터용 보너스 옵션
        * 최생, 최마, 아군회복, 아군보호막, 깡무공
        
        - base_info: 품질, 거래 가능 횟수 등 기본 정보
        """
        reference_options = {
            "dealer_exclusive": [],    
            "dealer_bonus": [],       
            "support_exclusive": [],   
            "support_bonus": [],      
            "base_info": {
                "quality": item["GradeQuality"],
                "trade_count": item["AuctionInfo"]["TradeAllowCount"],
            }
        }

        for opt in item["Options"]:
            opt_name = opt["OptionName"]
            if opt_name in ["깨달음", "도약"]:
                continue

            # 딜러 전용 옵션
            if ((part == "목걸이" and opt_name in ["추피", "적주피"]) or
                (part == "귀걸이" and opt_name in ["공퍼", "무공퍼"]) or
                (part == "반지" and opt_name in ["치적", "치피"])):
                reference_options["dealer_exclusive"].append((opt_name, opt["Value"]))
            
            # 서포터 전용 옵션
            if ((part == "목걸이" and opt_name in ["아덴게이지", "낙인력"]) or
                (part == "귀걸이" and opt_name == "무공퍼") or  # 귀걸이 무공퍼 추가
                (part == "반지" and opt_name in ["아공강", "아피강"])):
                reference_options["support_exclusive"].append((opt_name, opt["Value"]))
            
            # 딜러용 보너스 옵션
            if opt_name in ["깡공", "깡무공"]:
                reference_options["dealer_bonus"].append((opt_name, opt["Value"]))
            
            # 서포터용 보너스 옵션
            if opt_name in ["최생", "최마", "아군회복", "아군보호막", "깡무공"]:
                reference_options["support_bonus"].append((opt_name, opt["Value"]))

        if self.debug:
            print("\nClassified options:")
            for key, value in reference_options.items():
                if key != "base_info":
                    print(f"{key}: {value}")
                else:
                    print(f"{key}: {reference_options['base_info']}")

        return reference_options
    
    def _estimate_dealer_price(self, reference_options: Dict[str, Any], 
                            price_data: Dict[str, Any]) -> int:
        """
        딜러용 가격 추정
        모든 아이템은 최소한 base_price를 가지며,
        옵션이 있는 경우 해당 옵션들의 가치를 더함
        """
        # 기본 가격에서 시작
        estimated_price = price_data['base_price']

        # Common 딜러용 보너스 옵션 가치 추가
        for opt_name, opt_value in reference_options["dealer_bonus"]:
            common_values = price_data.get('common_option_values', {})
            if opt_name in common_values and common_values[opt_name]:
                try:
                    # 정확히 일치하거나 더 작은 값들 중 최대값 찾기
                    valid_values = [float(v) for v in common_values[opt_name].keys() 
                                if float(v) <= opt_value]
                    if valid_values:
                        closest_value = max(valid_values)
                        additional_value = common_values[opt_name][closest_value]
                        estimated_price += additional_value
                        if self.debug:
                            print(f"Added value for {opt_name} {opt_value}: +{additional_value:,}")
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        # 품질 보정 (항상 적용)
        quality_diff = reference_options["base_info"]["quality"] - 67  # 67이 기준 품질
        quality_adjustment = quality_diff * price_data['quality_coefficient'] * 0.5 # 보수적으로 잡기 위해 0.5 넣음
        estimated_price += quality_adjustment

        # 거래 횟수 보정 (항상 적용)
        trade_diff = reference_options["base_info"]["trade_count"] - 2  # 2회가 기준
        if trade_diff < 0:  # 거래 횟수가 적으면 가치 감소
            trade_adjustment = trade_diff * abs(price_data['trade_count_coefficient'])
            estimated_price += trade_adjustment

        if self.debug:
            print("\nDealer price estimation:")
            print(f"Base price: {price_data['base_price']:,}")
            print(f"Quality adjustment: {quality_adjustment:,}")
            print(f"Trade adjustment: {trade_adjustment if 'trade_adjustment' in locals() else 0:,}")
            print(f"Final estimate: {estimated_price:,}")

        return max(int(estimated_price), 1)
    
    def _estimate_support_price(self, reference_options: Dict[str, Any], 
                            price_data: Dict[str, Any]) -> int:
        """
        서포터용 가격 추정
        모든 아이템은 최소한 base_price를 가지며,
        옵션이 있는 경우 해당 옵션들의 가치를 더함
        """
        # 기본 가격에서 시작
        estimated_price = price_data['base_price']

        # 서포터용 보너스 옵션 가치 추가
        for opt_name, opt_value in reference_options["support_bonus"]:
            common_values = price_data.get('common_option_values', {})
            if opt_name in common_values and common_values[opt_name]:
                try:
                    # 정확히 일치하거나 더 작은 값들 중 최대값 찾기
                    valid_values = [float(v) for v in common_values[opt_name].keys() 
                                if float(v) <= opt_value]
                    if valid_values:
                        closest_value = max(valid_values)
                        additional_value = common_values[opt_name][closest_value]
                        estimated_price += additional_value
                        if self.debug:
                            print(f"Added value for {opt_name} {opt_value}: +{additional_value:,}")
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        # 품질 보정 (항상 적용)
        quality_diff = reference_options["base_info"]["quality"] - 67
        quality_adjustment = quality_diff * price_data['quality_coefficient'] * 0.5 # 보수적으로 잡기 위해 0.5 넣음
        estimated_price += quality_adjustment

        # 거래 횟수 보정 (항상 적용)
        trade_diff = reference_options["base_info"]["trade_count"] - 2
        if trade_diff < 0:  # 거래 횟수가 적으면 가치 감소
            trade_adjustment = trade_diff * abs(price_data['trade_count_coefficient'])
            estimated_price += trade_adjustment

        if self.debug:
            print("\nSupport price estimation:")
            print(f"Base price: {price_data['base_price']:,}")
            print(f"Quality adjustment: {quality_adjustment:,}")
            print(f"Trade adjustment: {trade_adjustment if 'trade_adjustment' in locals() else 0:,}")
            print(f"Final estimate: {estimated_price:,}")

        return max(int(estimated_price), 1)

    def _estimate_acc_price(self, item: Dict, grade: str, part: str, level: int) -> Dict[str, Any]:
        try:
            if self.debug:
                print(f"\n=== Price Estimation Debug ===")
                print(f"Item: {grade} {part} (Level {level})")
                print(f"Quality: {item['GradeQuality']}")
                print("Options:")
                for opt in item["Options"]:
                    if opt["OptionName"] not in ["깨달음", "도약"]:
                        print(f"  - {opt['OptionName']}: {opt['Value']}")

            # 옵션 분류
            reference_options = self._get_reference_options(item, part)
        
            # 현재 즉구가
            current_price = item["AuctionInfo"]["BuyPrice"]

            # 캐시된 가격 데이터 조회
            price_data = self.price_cache.get_price_data(grade, part, level, reference_options)

            # 딜러용/서포터용 가격 추정 - 항상 양쪽 다 계산
            dealer_price = self._estimate_dealer_price(reference_options, price_data["dealer"])
            support_price = self._estimate_support_price(reference_options, price_data["support"])

            # has_options는 여전히 실제 옵션 존재 여부로 판단
            result = {
                "dealer_price": dealer_price,
                "support_price": support_price,
                "has_dealer_options": bool(reference_options["dealer_exclusive"] or reference_options["dealer_bonus"]),
                "has_support_options": bool(reference_options["support_exclusive"] or reference_options["support_bonus"]),
            }

            # 최종 타입과 가격 결정 - 항상 둘 중 더 높은 쪽으로
            if dealer_price > support_price:
                result.update({
                    "type": "dealer",
                    "price": dealer_price
                })
            else:
                result.update({
                    "type": "support",
                    "price": support_price
                })

            return result

        except Exception as e:
            if self.debug:
                print(f"Error in price estimation: {str(e)}")
                import traceback
                traceback.print_exc()
            # 에러가 발생해도 현재 가격으로 기본 결과 반환
            return {
                "type": "dealer" if any(opt[0] in ["추피", "적주피", "공퍼", "무공퍼", "치적", "치피"] 
                                    for opt in reference_options["dealer_exclusive"]) else "support",
                "price": current_price,
                "dealer_price": current_price if reference_options["dealer_exclusive"] else None,
                "support_price": current_price if reference_options["support_exclusive"] else None,
                "has_dealer_options": bool(reference_options["dealer_exclusive"]),
                "has_support_options": bool(reference_options["support_exclusive"]),
            }

    def evaluate_item(self, item: Dict) -> Optional[Dict]:
        """아이템 평가"""
        if not item["AuctionInfo"]["BuyPrice"]:
            return None

        # 아이템 타입 구분
        if "팔찌" in item["Name"]:
            return self._evaluate_bracelet(item)
        else:
            fix_dup_options(item) # 중복 옵션 처리해서 보내기
            return self._evaluate_accessory(item)

    def _evaluate_accessory(self, item: Dict) -> Optional[Dict]:
            grade = item["Grade"]
            level = len(item["Options"]) - 1

            # 파트 확인
            if "목걸이" in item["Name"]:
                part = "목걸이"
            elif "귀걸이" in item["Name"]:
                part = "귀걸이"
            elif "반지" in item["Name"]:
                part = "반지"
            else:
                return None

            # 기본 검증
            if item["GradeQuality"] < 67:
                # print("품질이 67 미만임")
                return None

            # 가격 추정
            estimate_result = self._estimate_acc_price(item, grade, part, level)

            current_price = item["AuctionInfo"]["BuyPrice"]
            expected_price = estimate_result["price"]
            price_ratio = current_price / expected_price
            profit = expected_price - current_price

            return {
                "type": "accessory",
                "grade": grade,
                "part": part,
                "level": level,
                "quality": item["GradeQuality"],
                "current_price": current_price,
                "expected_price": expected_price,
                "price_ratio": price_ratio,
                "profit": profit,
                "usage_type": estimate_result["type"],
                "dealer_price": estimate_result["dealer_price"],
                "support_price": estimate_result["support_price"],
                "has_dealer_options": estimate_result["has_dealer_options"],
                "has_support_options": estimate_result["has_support_options"],
                "is_notable": self._is_notable_accessory(level, current_price, expected_price, price_ratio)
            }

    def _evaluate_bracelet(self, item: Dict) -> Optional[Dict]:
        """팔찌 평가"""
        grade = item["Grade"]
        current_price = item["AuctionInfo"]["BuyPrice"]

        # 기본 정보 추출
        fixed_option_count = 0  # 처음부터 카운트
        extra_option_count = 0
        combat_stats = []
        base_stats = []
        special_effects = []

        for option in item["Options"]:
            # 깨달음/도약은 건너뛰기
            if option["OptionName"] in ["깨달음", "도약"]:
                continue
                
            # 부여 효과 수량만 따로 처리하고, 나머지는 모두 고정 효과로 카운트
            if option["Type"] == "BRACELET_RANDOM_SLOT":
                extra_option_count = int(option["Value"])
            else:
                fixed_option_count += 1  # 모든 다른 옵션은 고정 효과로 카운트
                
                # 옵션 종류별 분류
                if option["Type"] == "STAT":
                    if option["OptionName"] in ["특화", "치명", "신속"]:
                        combat_stats.append((option["OptionName"], option["Value"]))
                    elif option["OptionName"] in ["힘", "민첩", "지능"]:
                        base_stats.append((option["OptionName"], option["Value"]))
                    else: # special_effect는 아닌데 의미는 없음(제인숙, 체력)
                        special_effects.append((option["OptionName"], option["Value"]))
                else:
                    special_effects.append((option["OptionName"], option["Value"]))

        # print(grade, fixed_option_count, extra_option_count, combat_stats, base_stats, special_effects)
        # 캐시된 가격 데이터를 사용하여 예상 가격 계산
        item_data = {
            'fixed_option_count': fixed_option_count,
            'extra_option_count': extra_option_count,
            'combat_stats': combat_stats,
            'base_stats': base_stats,
            'special_effects': special_effects
        }
        
        expected_price = self.price_cache.get_bracelet_price(grade, item_data)

        if not expected_price:
            if current_price > 5000:
                # print(f"팔찌값 산출 실패 {item_data}")
                stats_str = []
                # 전투 특성
                for stat_type, value in combat_stats:
                    stats_str.append(f"{stat_type}{value}")
                # 기본 스탯
                for stat_type, value in base_stats:
                    stats_str.append(f"{stat_type}{value}")
                # 특수 효과 (이제 (이름, 값) 튜플)
                for effect_name, effect_value in special_effects:
                    stats_str.append(f"{effect_name}{effect_value}")
                # 부여 효과 수량 추가
                stats_str.append(f"부여 효과 수량{extra_option_count}")
                # print(item["Options"])
                print(f"{grade} {item['Name']} | {current_price:,}골드 vs ?? | 고정 {fixed_option_count} 부여 {extra_option_count} | 만료 {item['AuctionInfo']['EndDate']} | {' '.join(stats_str)}")
            return None

        price_ratio = current_price / expected_price
        profit = expected_price - current_price

        return {
            "type": "bracelet",
            "grade": grade,
            "current_price": current_price,
            "expected_price": expected_price,
            "price_ratio": price_ratio,
            "profit": profit,
            "fixed_option_count": fixed_option_count,
            "extra_option_count": extra_option_count,
            "combat_stats": combat_stats,
            "base_stats": base_stats,
            "special_effects": special_effects,
            "is_notable": self._is_notable_bracelet(current_price, expected_price, price_ratio),
        }

    def _is_notable_accessory(
        self, level: int, current_price: int, expected_price: int, price_ratio: float
    ) -> bool:
        """악세서리가 주목할 만한지 판단"""
        # if level >= 3 and expected_price > 60000 and price_ratio < 0.6:
        #     return True
        # if level < 3 and expected_price > 40000 and price_ratio < 0.45:
        #     return True
        # return False
        if price_ratio < 0.5 and expected_price > 10000:
            return True
        return False

    def _is_notable_bracelet(self, current_price: int, expected_price: int, price_ratio: float) -> bool:
        """팔찌가 주목할 만한지 판단"""
        # if expected_price > 50000 and price_ratio < 0.7:
        #     return True
        # return False
        if price_ratio < 0.5 and expected_price > 10000:
            return True
        return False
