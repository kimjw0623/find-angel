import time
import threading
import numpy as np
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from src.database.raw_database import *
from src.common.utils import *
from src.core.pattern_reader import PatternReader
from sqlalchemy.orm import aliased

class ItemEvaluator:
    def __init__(self, debug=False):
        self.debug = debug
        self.pattern_reader = PatternReader(debug=debug)
        self.last_check_time = self.pattern_reader.get_last_update_time()
        
        # IPC 서버 설정
        self._setup_ipc_server()
        
        # 캐시 업데이트 체크 스레드 시작 (백업용)
        self._stop_flag = threading.Event()
        self._update_check_thread = threading.Thread(
            target=self._check_cache_updates,
            name="CacheUpdateChecker"
        )
        self._update_check_thread.daemon = True
        self._update_check_thread.start()
    
    def _setup_ipc_server(self):
        """IPC 서버 설정 및 메시지 핸들러 등록"""
        try:
            from src.common.ipc_utils import IPCServer, MessageTypes
            
            self.ipc_server = IPCServer()
            
            # 패턴 업데이트 메시지 핸들러 등록
            self.ipc_server.register_handler(
                MessageTypes.PATTERN_UPDATED,
                self._handle_pattern_update_message
            )
            
            # 헬스체크 핸들러 등록
            self.ipc_server.register_handler(
                MessageTypes.HEALTH_CHECK,
                self._handle_health_check
            )
            
            # 서버 시작
            self.ipc_server.start_server()
            
        except Exception as e:
            print(f"Warning: Failed to setup IPC server: {e}")
            self.ipc_server = None
    
    def _handle_pattern_update_message(self, message):
        """패턴 업데이트 메시지 처리"""
        try:
            search_cycle_id_str = message['data']['search_cycle_id']
            search_cycle_id = datetime.fromisoformat(search_cycle_id_str)
            
            print(f"🔔 Pattern update notification received via IPC: {search_cycle_id}")
            
            # 패턴 업데이트 시간 갱신
            self.last_check_time = search_cycle_id
            
            print("✅ Patterns reloaded via IPC notification")
            
            return {'status': 'reloaded', 'timestamp': datetime.now().isoformat()}
            
        except Exception as e:
            print(f"Error processing pattern update message: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _handle_health_check(self, message):
        """헬스체크 메시지 처리"""
        return {
            'status': 'healthy',
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'timestamp': datetime.now().isoformat()
        }

    def _check_cache_updates(self):
        """주기적으로 캐시 파일 업데이트 확인 (백업용)"""
        while not self._stop_flag.is_set():
            try:
                cache_update_time = self.pattern_reader.get_last_update_time()
                
                # 캐시 파일이 더 최신이면 리로드 (IPC 알림을 놓친 경우 대비)
                if (cache_update_time and 
                    (not self.last_check_time or cache_update_time > self.last_check_time)):
                    print(f"📅 Fallback: New cache update detected: {cache_update_time}")
                    
                    # 패턴 업데이트 확인
                    self.last_check_time = cache_update_time
                    
                    print("✅ Patterns reloaded via fallback check")
            
            except Exception as e:
                if self.debug:
                    print(f"Error in fallback cache check: {e}")
            
            # 5분마다 체크 (IPC가 있으므로 긴 주기로)
            time.sleep(300)
            
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
    
    def _estimate_dealer_price(self, reference_options: Dict[str, Any], quality: int,
                            price_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        딜러용 가격 추정 및 상세 계산 내역 반환
        """
        # 기본 가격
        quality_cut = (quality // 10) * 10
        quality_prices = price_data['quality_prices']
        result = {
            'base_price': quality_prices[quality_cut],
            'options': {},
            'final_price': quality_prices[quality_cut]
        }

        # 딜러용 보너스 옵션 가치 계산
        for opt_name, opt_value in reference_options["dealer_bonus"]:
            common_values = price_data.get('common_option_values', {})
            if opt_name in common_values and common_values[opt_name]:
                try:
                    valid_values = [float(v) for v in common_values[opt_name].keys() 
                                if float(v) <= opt_value]
                    if valid_values:
                        closest_value = max(valid_values)
                        additional_value = common_values[opt_name][closest_value]
                        result['options'][opt_name] = {
                            'value': opt_value,
                            'price': additional_value
                        }
                        result['final_price'] += additional_value
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        result['final_price'] = max(int(result['final_price']), 1)
        return result
    
    def _estimate_support_price(self, reference_options: Dict[str, Any], quality: int,
                            price_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        서포터용 가격 추정 및 상세 계산 내역 반환
        """
        # 기본 가격
        quality_cut = (quality // 10) * 10
        quality_prices = price_data['quality_prices']
        result = {
            'base_price': quality_prices[quality_cut],
            'options': {},
            'final_price': quality_prices[quality_cut]
        }

        # 서포터용 보너스 옵션 가치 계산
        for opt_name, opt_value in reference_options["support_bonus"]:
            common_values = price_data.get('common_option_values', {})
            if opt_name in common_values and common_values[opt_name]:
                try:
                    valid_values = [float(v) for v in common_values[opt_name].keys() 
                                if float(v) <= opt_value]
                    if valid_values:
                        closest_value = max(valid_values)
                        additional_value = common_values[opt_name][closest_value]
                        result['options'][opt_name] = {
                            'value': opt_value,
                            'price': additional_value
                        }
                        result['final_price'] += additional_value
                except ValueError:
                    if self.debug:
                        print(f"No cached values found for {opt_name} {opt_value}")
                    continue

        result['final_price'] = max(int(result['final_price']), 1)
        return result

    def _estimate_acc_price(self, item: Dict, grade: str, part: str, level: int) -> Dict[str, Any]:
        """
        악세서리 가격 추정 및 상세 계산 내역 반환
        """
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
            price_data = self.pattern_reader.get_price_data(grade, part, level, reference_options)

            # 딜러용/서포터용 가격 추정 - 상세 내역 포함
            dealer_details = self._estimate_dealer_price(reference_options, int(item['GradeQuality']), price_data["dealer"])
            support_details = self._estimate_support_price(reference_options, int(item['GradeQuality']), price_data["support"])

            result = {
                'dealer_details': dealer_details,
                'support_details': support_details,
                'has_dealer_options': bool(reference_options["dealer_exclusive"] or reference_options["dealer_bonus"]),
                'has_support_options': bool(reference_options["support_exclusive"] or reference_options["support_bonus"]),
            }

            # 최종 타입과 가격 결정
            if dealer_details['final_price'] > support_details['final_price']:
                result.update({
                    'type': '딜러',
                    'price': dealer_details['final_price']
                })
            else:
                result.update({
                    'type': '서폿',
                    'price': support_details['final_price']
                })

            return result

        except Exception as e:
            if self.debug:
                print(f"Error in price estimation: {str(e)}")
                import traceback
                traceback.print_exc()
            return {
                'type': 'dealer' if any(opt[0] in ["추피", "적주피", "공퍼", "무공퍼", "치적", "치피"] 
                                    for opt in reference_options["dealer_exclusive"]) else 'support',
                'price': current_price,
                'dealer_details': {'final_price': current_price} if reference_options["dealer_exclusive"] else None,
                'support_details': {'final_price': current_price} if reference_options["support_exclusive"] else None,
                'has_dealer_options': bool(reference_options["dealer_exclusive"]),
                'has_support_options': bool(reference_options["support_exclusive"]),
            }

    def evaluate_item(self, item: Dict) -> Optional[Dict]:
        """
        아이템 평가 및 상세 정보 반환
        """
        if not item["AuctionInfo"]["BuyPrice"]:
            return None

        # 아이템 타입 구분
        if "팔찌" in item["Name"]:
            return self._evaluate_bracelet(item)
        else:
            fix_dup_options(item)
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
            return None

        # 가격 추정 (상세 내역 포함)
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
            "price_details": {
                "딜러": estimate_result["dealer_details"],
                "서폿": estimate_result["support_details"]
            },
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
            'grade': grade,
            'fixed_option_count': fixed_option_count,
            'extra_option_count': extra_option_count,
            'combat_stats': combat_stats,
            'base_stats': base_stats,
            'special_effects': special_effects
        }
        
        bracelet_result = self.pattern_reader.get_bracelet_price(grade, item_data)
        expected_price = None
        if bracelet_result:
            expected_price, total_sample_count = bracelet_result

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

    def _sigmoid(self, expected_price: int) -> float:
        min_ratio = 0.5
        max_ratio = 0.75
        max_price = 400000
        k3 = 3e-5  # 가장 완만한 기울기
        midpoint3 = max_price*2/3  # 가장 늦은 변곡점
        sigmoid_ratio = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k3 * (expected_price - midpoint3)))
        return expected_price * sigmoid_ratio

    def _is_notable_accessory(
        self, level: int, current_price: int, expected_price: int, price_ratio: float
    ) -> bool:
        """악세서리가 주목할 만한지 판단"""
        # if level >= 3 and expected_price > 60000 and price_ratio < 0.6:
        #     return True
        # if level < 3 and expected_price > 40000 and price_ratio < 0.45:
        #     return True
        # return False
        if expected_price > 20000 and current_price < self._sigmoid(expected_price):
            return True
        return False

    def _is_notable_bracelet(self, current_price: int, expected_price: int, price_ratio: float) -> bool:
        """팔찌가 주목할 만한지 판단"""
        # if expected_price > 50000 and price_ratio < 0.7:
        #     return True
        # return False
        if expected_price > 20000 and current_price < self._sigmoid(expected_price):
            return True
        return False
