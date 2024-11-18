import os
import time
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from database import *
from utils import *
from market_price_cache import MarketPriceCache
from sqlalchemy.orm import aliased

class MarketScanner:
    def __init__(self, db_manager, evaluator):
        self.db = db_manager
        self.evaluator = evaluator
        self.url = "https://developer-lostark.game.onstove.com/auctions/items"

        # 3일짜리 토큰
        self.headers_3day = {
            "accept": "application/json",
            "authorization": f"bearer {os.getenv('API_TOKEN_HONEYITEM_3DAY')}",
            "content-Type": "application/json",
        }

        # 1일짜리 토큰
        self.headers_1day = {
            "accept": "application/json",
            "authorization": f"bearer {os.getenv('API_TOKEN_HONEYITEM_1DAY')}",
            "content-Type": "application/json",
        }

        # 마지막 체크 시간 초기화
        self.last_expireDate_3day = None
        self.last_expireDate_1day = None
        self.last_page_index_1day = None

    def scan_market(self):
        """시장 스캔 실행"""
        try:
            # 3일 만료 매물 스캔
            self._scan_items(self.headers_3day, days=3)
            # 1일 만료 매물 스캔
            self._scan_items(self.headers_1day, days=1)
        except Exception as e:
            print(f"Error in market scan: {e}")

    def _scan_items(self, headers: Dict, days: int):
        """매물 스캔 및 실시간 평가"""
        current_time = datetime.now()
        # 매물 카운트
        count = 0
        # 1일/3일 매물 구분에 따른 초기화
        if days == 3:
            if not self.last_expireDate_3day:
                self.last_expireDate_3day = (
                    current_time + timedelta(days=3) - timedelta(minutes=3)
                )
            # print(f"3일 검색 시작, expire cut {self.last_expireDate_3day}")
            last_expireDate = self.last_expireDate_3day
            page_no = 1
        else:  # 1일 매물
            current_expireDate = current_time + timedelta(days=1)
            if not self.last_expireDate_1day:
                self.last_expireDate_1day = current_expireDate - timedelta(minutes=1)
            if not self.last_page_index_1day:
                self.last_page_index_1day = 740  # 초기 추정치

            # 적절한 시작 페이지 찾기
            page_no = self._find_starting_page(
                self.last_page_index_1day, current_expireDate
            )
            last_expireDate = self.last_expireDate_1day
            # print(f"1일 검색 시작, expire cut {self.last_expireDate_1day}")

        # 이번 검색 사이클의 첫 매물 시간을 저장할 변수
        next_expire_date = None
        
        while True:
            try:
                search_data = self._create_search_data(page_no)
                response = do_search(self.url, headers, search_data)
                data = response.json()

                if not data["Items"]:
                    break
                
                # 각 아이템 실시간 평가
                for item in data["Items"]:                  
                    end_time = datetime.strptime(
                        item["AuctionInfo"]["EndDate"].split(".")[0],
                        "%Y-%m-%dT%H:%M:%S",
                    )
                    
                    # 1일 매물인 경우 current_expireDate보다 작은지 추가 확인
                    if days == 1 and end_time >= current_expireDate:
                        continue
                    
                    # 첫 매물의 시간 저장 (아직 저장된 적 없는 경우에만)
                    if next_expire_date is None:
                        next_expire_date = end_time

                    # 이전에 체크한 시간보다 이후에 등록된 매물만 확인
                    if end_time <= last_expireDate:
                        # 1일 매물인 경우 마지막 페이지 인덱스 업데이트
                        if days == 1:
                            self.last_page_index_1day = page_no
                        # 마지막 확인 시간 업데이트 (첫 번째 매물 시간으로)
                        if days == 3:
                            self.last_expireDate_3day = next_expire_date
                        else:
                            self.last_expireDate_1day = next_expire_date
                        # print(f"... {count}개 검색 완료")
                        return
                    
                    count += 1
                    # 즉시 평가 및 처리
                    evaluation = self.evaluator.evaluate_item(item)
                    if evaluation and evaluation["is_notable"]:
                        self._handle_notable_item(item, evaluation)

                page_no += 1
                time.sleep(0.5)  # API 호출 간격 조절

            except Exception as e:
                print(f"Error scanning page {page_no}: {e}")
                break

    def _create_search_data(self, page_no: int) -> Dict:
        """검색 데이터 생성"""
        return {
            "ItemLevelMin": 0,
            "ItemLevelMax": 1800,
            "ItemGradeQuality": None,
            "Sort": "EXPIREDATE",
            "CategoryCode": 200000,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": "",
            "PageNo": page_no,
            "SortCondition": "DESC",
            "EtcOptions": [
                {
                    "FirstOption": "",
                    "SecondOption": "",
                    "MinValue": "",
                    "MaxValue": "",
                },
            ],
        }

    def _find_starting_page(
        self, last_page_index: int, current_expireDate: datetime
    ) -> int:
        """적절한 시작 페이지 찾기"""
        pageNo = last_page_index
        response = do_search(
            self.url, self.headers_1day, self._create_search_data(pageNo)
        )
        data = response.json()

        if not data["Items"]:
            return pageNo

        first_item = data["Items"][0]
        last_item = data["Items"][-1]

        first_item_end_time = datetime.strptime(
            first_item["AuctionInfo"]["EndDate"].split(".")[0], "%Y-%m-%dT%H:%M:%S"
        )
        last_item_end_time = datetime.strptime(
            last_item["AuctionInfo"]["EndDate"].split(".")[0], "%Y-%m-%dT%H:%M:%S"
        )

        # Case 1: 페이지가 너무 이름 (pageNo가 커져야 함)
        page_step = 3
        if (
            first_item_end_time > current_expireDate
            and last_item_end_time > current_expireDate
        ):
            while True:
                pageNo += page_step
                response = do_search(
                    self.url, self.headers_1day, self._create_search_data(pageNo)
                )
                data = response.json()

                if not data["Items"]:
                    return max(1, pageNo - page_step)

                last_item = data["Items"][-1]
                end_time = datetime.strptime(
                    last_item["AuctionInfo"]["EndDate"].split(".")[0],
                    "%Y-%m-%dT%H:%M:%S",
                )

                if end_time < current_expireDate:
                    return max(1, pageNo - page_step)

        # Case 2: 페이지가 너무 늦음 (pageNo가 작아져야 함)
        elif (
            first_item_end_time < current_expireDate
            and last_item_end_time < current_expireDate
        ):
            pageNo = max(1, pageNo - page_step)
            while pageNo > 0:
                response = do_search(
                    self.url, self.headers_1day, self._create_search_data(pageNo)
                )
                data = response.json()

                if not data["Items"]:
                    return pageNo + page_step

                last_item = data["Items"][-1]
                end_time = datetime.strptime(
                    last_item["AuctionInfo"]["EndDate"].split(".")[0],
                    "%Y-%m-%dT%H:%M:%S",
                )

                if end_time > current_expireDate:
                    return pageNo

                pageNo -= page_step

            return 1

        # Case 3: 현재 페이지가 적절함
        return pageNo

    def _handle_notable_item(self, item: Dict, evaluation: Dict):
        """주목할 만한 매물 처리"""
        options_str = ' '.join([f"{opt['OptionName']}{opt['Value']}" for opt in item["Options"] 
                            if opt["OptionName"] not in ["깨달음", "도약"]])
        
        end_date = item["AuctionInfo"]["EndDate"]  # 원본 문자열 그대로 사용
        
        if evaluation["type"] == "accessory":
            print(f"{evaluation['grade']} {item['Name']} | "
                f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
                f"({evaluation['price_ratio']*100:.1f}%) | "
                f"품질 {evaluation['quality']} | {evaluation['level']}연마 | "
                f"만료 {end_date} | "
                f"{options_str} | "
                f"거래 {item['AuctionInfo']['TradeAllowCount']}회")
        else:  # bracelet
            print(f"{evaluation['grade']} {item['Name']} | "
                f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
                f"({evaluation['price_ratio']*100:.1f}%) | "
                f"고정 {evaluation['fixed_option_count']} 부여 {int(evaluation['extra_option_count'])} | "
                f"만료 {end_date} | "
                f"{options_str}")


class ItemEvaluator:
    def __init__(self, db_manager, debug=False):
        self.db = db_manager
        self.debug = debug
        self.price_cache = MarketPriceCache(db_manager, debug)

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
            elif ((part == "목걸이" and opt_name in ["아덴게이지", "낙인력"]) or
                (part == "귀걸이" and opt_name == "무공퍼") or  # 귀걸이 무공퍼 추가
                (part == "반지" and opt_name in ["아공강", "아피강"])):
                reference_options["support_exclusive"].append((opt_name, opt["Value"]))
            
            # 딜러용 보너스 옵션
            elif opt_name in ["깡공", "깡무공"]:
                reference_options["dealer_bonus"].append((opt_name, opt["Value"]))
            
            # 서포터용 보너스 옵션
            elif opt_name in ["최생", "최마", "아군회복", "아군보호막", "깡무공"]:
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
                    # 가장 가까운 정해진 값 찾기
                    closest_value = min(common_values[opt_name].keys(), 
                                    key=lambda x: abs(float(x) - opt_value))
                    additional_value = common_values[opt_name].get(closest_value, 0)
                    estimated_price += additional_value
                    if self.debug:
                        print(f"Added value for {opt_name} {opt_value}: +{additional_value:,}")
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        # 품질 보정 (항상 적용)
        quality_diff = reference_options["base_info"]["quality"] - 67  # 67이 기준 품질
        quality_adjustment = quality_diff * price_data['quality_coefficient']
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
                    closest_value = min(common_values[opt_name].keys(), 
                                    key=lambda x: abs(float(x) - opt_value))
                    additional_value = common_values[opt_name].get(closest_value, 0)
                    estimated_price += additional_value
                    if self.debug:
                        print(f"Added value for {opt_name} {opt_value}: +{additional_value:,}")
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        # 품질 보정 (항상 적용)
        quality_diff = reference_options["base_info"]["quality"] - 67
        quality_adjustment = quality_diff * price_data['quality_coefficient']
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
        if current_price > 10000 or expected_price > 10000:
            return True
        return False

    def _is_notable_bracelet(self, current_price: int, expected_price: int, price_ratio: float) -> bool:
        """팔찌가 주목할 만한지 판단"""
        # if expected_price > 50000 and price_ratio < 0.7:
        #     return True
        # return False
        if current_price > 10000 or expected_price > 10000:
            return True
        return False

class MarketMonitor:
    def __init__(self, db_manager, debug=False):
        self.evaluator = ItemEvaluator(db_manager, debug=debug)
        self.scanner = MarketScanner(db_manager, self.evaluator)

    def run(self):
        """모니터링 실행"""
        print(f"Starting market monitoring at {datetime.now()}")

        while True:
            try:
                self.scanner.scan_market()
                time.sleep(2)  # 다음 스캔까지 대기
            except KeyboardInterrupt:
                print("\nStopping market monitoring...")
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(5)

def main():
    db_manager = DatabaseManager()
    monitor = MarketMonitor(db_manager, debug=False)
    monitor.run()

if __name__ == "__main__":  
    main()
  
