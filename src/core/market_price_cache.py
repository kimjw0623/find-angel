from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
from src.database.database import *
from src.database.cache_database import *
import pickle
import time
import os
import sys
import threading
from contextlib import contextmanager, nullcontext
import uuid
import json

@contextmanager
def redirect_stdout(file_path, mode='a'):
    """stdout을 파일로 임시 리다이렉트하는 컨텍스트 매니저"""
    original_stdout = sys.stdout
    with open(file_path, mode, encoding='utf-8') as f:
        sys.stdout = f
        try:
            yield
        finally:
            sys.stdout = original_stdout

def convert_json_keys_to_float(obj):
    """JSON 객체의 숫자 형태의 문자열 키를 float으로 변환"""
    if isinstance(obj, dict):
        return {
            float(k) if isinstance(k, str) and k.replace('.', '').isdigit() else k: convert_json_keys_to_float(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [convert_json_keys_to_float(item) for item in obj]
    return obj

def convert_json_keys_to_int(obj):
    """JSON 객체의 숫자 형태의 문자열 키를 int로 변환"""
    if isinstance(obj, dict):
        return {
            int(k) if isinstance(k, str) and k.isdigit() else k: convert_json_keys_to_int(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [convert_json_keys_to_int(item) for item in obj]
    return obj

class DBMarketPriceCache:
    def __init__(self, main_db_manager: DatabaseManager, debug: bool = False):
        self.main_db = main_db_manager  # 기존 DB (데이터 읽기용)
        self.cache_db = init_cache_database()  # 캐시 전용 DB
        self.debug = debug
        self.cache = {}  # 메모리 캐시
        self._load_cache()

        self.EXCLUSIVE_OPTIONS = {
            "목걸이": {
                "dealer": ["추피", "적주피"],
                "support": ["아덴게이지", "낙인력"]
            },
            "귀걸이": {
                "dealer": ["공퍼", "무공퍼"],
                "support": ["무공퍼"]
            },
            "반지": {
                "dealer": ["치적", "치피"],
                "support": ["아공강", "아피강"]
            }
        }

        self.COMMON_OPTIONS = {
            # 딜러용 부가 옵션
            "깡공": [80.0, 195.0, 390.0],
            "깡무공": [195.0, 480.0, 960.0], # 얘는 서포터용 부가 옵션이기도 함
            # 서포터용 부가 옵션
            "최생": [1300.0, 3250.0, 6500.0],
            "최마": [6.0, 15.0, 30.0],
            "아군회복": [0.95, 2.1, 3.5],
            "아군보호막": [0.95, 2.1, 3.5]
        }

    def _load_cache(self):
        """현재 활성화된 캐시 데이터 로드"""
        with self.cache_db.get_read_session() as session:
            # 활성화된 캐시 찾기
            active_cache = session.query(MarketPriceCache).filter_by(is_active=True).first()
            
            if not active_cache:
                if self.debug:
                    print("No active cache found, initializing empty cache")
                self.cache = {
                    "dealer": {},
                    "support": {},
                    "bracelet_고대": {},
                    "bracelet_유물": {}
                }
                return

            # 악세서리 패턴 로드
            accessory_patterns = session.query(AccessoryPricePattern).filter_by(
                cache_id=active_cache.cache_id
            ).all()

            # 팔찌 패턴 로드
            bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                cache_id=active_cache.cache_id
            ).all()

            # 캐시 데이터 구성
            self.cache = {
                "dealer": {},
                "support": {},
                "bracelet_고대": {},
                "bracelet_유물": {}
            }

            # 악세서리 패턴 처리
            for pattern in accessory_patterns:
                cache_key = f"{pattern.grade}:{pattern.part}:{pattern.level}:{pattern.pattern_key}"
                # JSON 로드 시 숫자 키를 float, int로 각각 변환
                converted_common_option_values = convert_json_keys_to_float(json.loads(pattern.common_option_values))
                converted_base_prices = convert_json_keys_to_int(json.loads(pattern.quality_prices))
                
                pattern_data = {
                    'quality_prices': converted_base_prices,
                    'common_option_values': converted_common_option_values,
                    'total_sample_count': pattern.total_sample_count,
                    'last_update': active_cache.search_cycle_id
                }
                
                if pattern.role == 'dealer':
                    self.cache['dealer'][cache_key] = pattern_data
                else:
                    self.cache['support'][cache_key] = pattern_data

            # 팔찌 패턴 처리
            for pattern in bracelet_patterns:
                pattern_key = (
                    pattern.combat_stats,
                    pattern.base_stats,
                    pattern.extra_slots
                )
                bracelet_cache_first_key = f'bracelet_{pattern.grade}'
                try:
                    self.cache[bracelet_cache_first_key][pattern.pattern_type][pattern_key] = pattern.price, pattern.total_sample_count
                except KeyError:
                    self.cache[bracelet_cache_first_key][pattern.pattern_type] = {}
                    self.cache[bracelet_cache_first_key][pattern.pattern_type][pattern_key] = pattern.price, pattern.total_sample_count

            if self.debug:
                print(f"Cache loaded. Last update: {active_cache.search_cycle_id}")
                print(f"Dealer cache entries: {len(self.cache['dealer'])}")
                print(f"Support cache entries: {len(self.cache['support'])}")
                print(f"고대 팔찌 cache entries: {len(self.cache['bracelet_고대'])}")
                print(f"유물 팔찌 cache entries: {len(self.cache['bracelet_유물'])}")

    def get_last_update_time(self) -> Optional[datetime]:
        """캐시의 마지막 업데이트 시간 확인"""
        with self.cache_db.get_read_session() as session:
            active_cache = session.query(MarketPriceCache).filter_by(is_active=True).first()
            return active_cache.search_cycle_id if active_cache else None

    def get_price_data(self, grade: str, part: str, level: int, 
                      options: Dict[str, List[Tuple[str, float]]]) -> Dict[str, Optional[Dict]]:
        """가격 데이터 조회"""            
        dealer_key, support_key = self.get_cache_key(grade, part, level, options)
        
        cache_data = {
            "dealer": None,
            "support": None
        }

        if dealer_key and dealer_key in self.cache["dealer"]:
            cache_data["dealer"] = self.cache["dealer"][dealer_key]
            if self.debug:
                print(f"\nDealer cache hit for {dealer_key}")
                print(f"Base price: {cache_data['dealer']['base_price']:,}")
                print(f"Sample count: {cache_data['dealer']['sample_count']}")

        if support_key and support_key in self.cache["support"]:
            cache_data["support"] = self.cache["support"][support_key]
            if self.debug:
                print(f"\nSupport cache hit for {support_key}")
                print(f"Base price: {cache_data['support']['base_price']:,}")
                print(f"Sample count: {cache_data['support']['sample_count']}")

        return cache_data

    def get_bracelet_price(self, grade: str, item_data: Dict) -> Optional[int]:
        """팔찌 가격 조회"""
        pattern_info = self._classify_bracelet_pattern(item_data)
        # print(f"찾아진 패턴 for item {item_data}: {pattern_info}")
        if not pattern_info:
            return None

        pattern_type, details = pattern_info
        key = (details['pattern'], details['values'], details['extra_slots'])

        # 캐시에서 해당 패턴의 가격 조회
        cache_key = f"bracelet_{grade}"

        # 1. 기본적인 캐시 존재 여부 확인
        if cache_key not in self.cache:
            if self.debug:
                print(f"No cache data found for {cache_key}")
            return None

        # 2. 해당 패턴 타입의 가격 데이터 가져오기
        pattern_prices = self.cache[cache_key].get(pattern_type, {})

        # 3. 정확한 매칭 시도
        if key in pattern_prices:
            if self.debug:
                print(f"\nExact pattern match found:")
                print(f"Pattern: {pattern_type} {key}")
                print(f"Price: {pattern_prices[key]:,}")
            return pattern_prices[key]

        # 4. 정확한 매칭이 없는 경우 비슷한 패턴 찾기
        # (기존 비슷한 패턴 찾기 로직 유지)
        for cached_key, (price, total_sample_count) in pattern_prices.items():
            cached_pattern, cached_values, cached_extra = cached_key
            if (cached_pattern == details['pattern'] and 
                cached_extra == details['extra_slots']):
                if self._is_similar_values(cached_values, details['values'], pattern_type):
                    if self.debug:
                        print(f"\nSimilar pattern match found:")
                        print(f"Original pattern: {pattern_type} {key}")
                        print(f"Matched pattern: {pattern_type} {cached_key}")
                        print(f"Price: {price:,}")
                    return (price, total_sample_count)

        if self.debug:
            print(f"No matching pattern found for {pattern_type} {key}")

        return None

    def update_cache(self, search_cycle_id: str) -> bool:
        """
        특정 search_cycle의 시장 가격 데이터로 캐시 업데이트
        
        Args:
            search_cycle_id: 캐시를 생성할 search_cycle의 ID
            
        Returns:
            bool: 캐시 업데이트 성공 여부
        """
        try:
            # 로그 파일 설정
            print(f"\nUpdating price cache for search cycle {search_cycle_id}")
            log_filename = f'price_log/price_calculation_{search_cycle_id}.log'

            with redirect_stdout(log_filename):
                new_cache = {
                    "dealer": {},
                    "support": {},
                    "bracelet_고대": {},
                    "bracelet_유물": {}
                }

                with self.main_db.get_read_session() as session:
                    # 해당 search_cycle의 timestamp 조회
                    cycle_info = session.query(PriceRecord.timestamp)\
                        .filter(PriceRecord.search_cycle_id == search_cycle_id)\
                        .first()
                    
                    if not cycle_info:
                        print(f"No data found for search cycle {search_cycle_id}")
                        return False
                        
                    print(f"Processing data from search cycle at {search_cycle_id}")
                    
                    # 해당 search_cycle의 데이터 조회
                    start_time = datetime.now()
                    records = session.query(PriceRecord)\
                        .filter(PriceRecord.search_cycle_id == search_cycle_id)\
                        .all()
                    print(f"DB query duration: {datetime.now() - start_time}")
                    start_time = datetime.now()
                    print(f"Found {len(records)} acc records in search cycle")

                    # 딜러용/서포터용 데이터 그룹화
                    dealer_groups = {}
                    support_groups = {}

                    for record in records:
                        session.refresh(record)

                        dealer_options = []
                        support_options = []
                        # 부위 확인
                        if "목걸이" in record.name:
                            part = "목걸이"
                            # 딜러 옵션 체크
                            dealer_options.extend([("추피", opt.option_value) for opt in record.raw_options if opt.option_name == "추피"])
                            dealer_options.extend([("적주피", opt.option_value) for opt in record.raw_options if opt.option_name == "적주피"])
                            # 서폿 옵션 체크
                            support_options.extend([("아덴게이지", opt.option_value) for opt in record.raw_options if opt.option_name == "아덴게이지"])
                            support_options.extend([("낙인력", opt.option_value) for opt in record.raw_options if opt.option_name == "낙인력"])
                        elif "귀걸이" in record.name:
                            part = "귀걸이"
                            # 딜러 옵션 체크
                            dealer_options.extend([("공퍼", opt.option_value) for opt in record.raw_options if opt.option_name == "공퍼"])
                            dealer_options.extend([("무공퍼", opt.option_value) for opt in record.raw_options if opt.option_name == "무공퍼"])
                            # 서폿 옵션 체크
                            support_options.extend([("무공퍼", opt.option_value) for opt in record.raw_options if opt.option_name == "무공퍼"])
                        elif "반지" in record.name:
                            part = "반지"
                            # 딜러 옵션 체크
                            dealer_options.extend([("치적", opt.option_value) for opt in record.raw_options if opt.option_name == "치적"])
                            dealer_options.extend([("치피", opt.option_value) for opt in record.raw_options if opt.option_name == "치피"])
                            # 서폿 옵션 체크
                            support_options.extend([("아공강", opt.option_value) for opt in record.raw_options if opt.option_name == "아공강"])
                            support_options.extend([("아피강", opt.option_value) for opt in record.raw_options if opt.option_name == "아피강"])
                        else:
                            continue

                        # 딜러용/서포터용 키 생성
                        dealer_key = f"{record.grade}:{part}:{record.level}:{sorted(dealer_options)}" if dealer_options else f"{record.grade}:{part}:{record.level}:base"
                        if dealer_key not in dealer_groups:
                            dealer_groups[dealer_key] = []
                        dealer_groups[dealer_key].append(record)

                        support_key = f"{record.grade}:{part}:{record.level}:{sorted(support_options)}" if support_options else f"{record.grade}:{part}:{record.level}:base"
                        if support_key not in support_groups:
                            support_groups[support_key] = []
                        support_groups[support_key].append(record)
                    print(f"Classifying acc patterns duration: {datetime.now() - start_time}")
                    start_time = datetime.now()

                    # 각 그룹별로 가격 계산
                    for key, items in dealer_groups.items():
                        if len(items) >= 3:  # 최소 3개 이상의 데이터가 있는 경우만
                            price_data = self._calculate_group_prices(items, key, "dealer")
                            if price_data:
                                new_cache["dealer"][key] = price_data

                    for key, items in support_groups.items():
                        if len(items) >= 3:
                            price_data = self._calculate_group_prices(items, key, "support")
                            if price_data:
                                new_cache["support"][key] = price_data

                    print(f"Calculating acc group prices duration: {datetime.now() - start_time}")

                    # 팔찌 가격 업데이트
                    for grade in ["고대", "유물"]:
                        cache_key = f"bracelet_{grade}"
                        new_cache[cache_key] = self._calculate_bracelet_prices(grade, search_cycle_id)
                        
                # 새로운 캐시 ID 생성
                new_cache_id = str(uuid.uuid4())
                start_time = datetime.now()

                with self.cache_db.get_write_session() as write_session:
                    # 가장 최근 search_cycle인지 확인
                    latest_cycle = write_session.query(MarketPriceCache.search_cycle_id)\
                        .order_by(MarketPriceCache.search_cycle_id.desc())\
                        .first()
                    
                    # 테이블이 비어있거나, 현재 cycle이 더 최신인 경우 True
                    is_latest = not latest_cycle or latest_cycle.search_cycle_id <= search_cycle_id
                    
                    print(f"Latest cycle id: {latest_cycle.search_cycle_id if latest_cycle else 'None'}")
                    print(f"Current cache id: {search_cycle_id}")
                    print(f"Is latest: {is_latest}")

                    # 새 캐시 메타데이터 생성
                    new_cache_entry = MarketPriceCache(
                        cache_id=new_cache_id,
                        search_cycle_id=search_cycle_id,  # timestamp 대신 search_cycle_id 사용
                        is_active=is_latest
                    )

                    if is_latest:
                        # 기존 활성 캐시 비활성화
                        write_session.query(MarketPriceCache).filter_by(is_active=True).update(
                            {"is_active": False}
                        )
                    write_session.add(new_cache_entry)
                    write_session.flush()

                    # 악세서리 패턴 저장
                    for role in ['dealer', 'support']:
                        for cache_key, pattern_data in new_cache[role].items():
                            grade, part, level, pattern_key = cache_key.split(':')
                            
                            acc_pattern = AccessoryPricePattern(
                                cache_id=new_cache_id,
                                grade=grade,
                                part=part,
                                level=level,
                                pattern_key=pattern_key,
                                role=role,
                                quality_prices=json.dumps(pattern_data['quality_prices']),
                                common_option_values=json.dumps(pattern_data['common_option_values']),
                                total_sample_count=pattern_data['total_sample_count'],
                            )
                            write_session.add(acc_pattern)

                    # 팔찌 패턴 저장
                    for grade in ['고대', '유물']:
                        bracelet_data = new_cache[f'bracelet_{grade}']
                        for pattern_type, patterns in bracelet_data.items():
                            for pattern_key, (price, total_sample_count) in patterns.items():
                                combat_stats, base_stats, extra_slots = pattern_key
                                
                                bracelet_pattern = BraceletPricePattern(
                                    cache_id=new_cache_id,
                                    grade=grade,
                                    pattern_type=pattern_type,
                                    combat_stats=combat_stats,
                                    base_stats=base_stats,
                                    extra_slots=extra_slots,
                                    price=price,
                                    total_sample_count=total_sample_count
                                )
                                write_session.add(bracelet_pattern)

                    print(f"Writing cache duration: {datetime.now() - start_time}")

                print(f"Cache created with ID {new_cache_id} for search cycle {search_cycle_id}")
                return True

        except Exception as e:
            print(f"Error updating price cache: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_cache_key(self, grade: str, part: str, level: int, options: Dict[str, List[Tuple[str, float]]]) -> Tuple[str, str]:
        """캐시 키 생성 - exclusive 옵션만 사용"""
        dealer_exclusive = sorted([
            (opt[0], opt[1]) for opt in options["dealer_exclusive"]
        ])
        support_exclusive = sorted([
            (opt[0], opt[1]) for opt in options["support_exclusive"]
        ])
        
        # exclusive 옵션이 있으면 그것을 포함한 키를, 없으면 기본 키를 리턴
        dealer_key = f"{grade}:{part}:{level}:{dealer_exclusive}" if dealer_exclusive else f"{grade}:{part}:{level}:base"
        support_key = f"{grade}:{part}:{level}:{support_exclusive}" if support_exclusive else f"{grade}:{part}:{level}:base"
        
        return dealer_key, support_key

    def _calculate_common_option_values(self, items: List[PriceRecord], role: str, quality_prices: Dict[str, int]) -> Dict: 
        """각 Common 옵션 값의 추가 가치를 계산"""
        MIN_SAMPLE = 2
        if len(items) < MIN_SAMPLE:
            print(f"\nInsufficient samples for common option calculation: {len(items)} < {MIN_SAMPLE}")
            return {}

        # 역할별 관련 옵션 정의
        role_related_options = {
            "dealer": ["깡공", "깡무공"],
            "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
        }

        values = {}
        # 역할별 관련 옵션에 대해서만 계산
        for opt_name in role_related_options[role]:
            if opt_name in self.COMMON_OPTIONS:
                print(f"\nProcessing option: {opt_name}")
                values[opt_name] = {}

                for target_value in self.COMMON_OPTIONS[opt_name]:
                    # target_value 이상의 옵션을 가진 아이템들
                    matching_items = [
                        item for item in items
                        if any(opt.option_name == opt_name and opt.option_value >= target_value
                            for opt in item.raw_options)
                    ]

                    if len(matching_items) >= MIN_SAMPLE:
                        # 각 아이템의 품질에 따른 base price 고려하여 추가 가치 계산
                        additional_values = []
                        for item in matching_items:
                            # 해당 품질 이하의 가장 높은 품질대의 가격 찾기
                            quality_cut = 90 if item.quality >= 90 else (item.quality // 10) * 10
                            valid_cutoffs = [qc for qc in quality_prices.keys() if int(qc) <= quality_cut]
                            if valid_cutoffs:
                                actual_quality_cut = max(valid_cutoffs)
                                base_price = quality_prices[actual_quality_cut]
                                additional_values.append(item.price - base_price)

                        sorted_values = sorted(additional_values)
                        additional_value = sorted_values[0]  # 가장 낮은 값 사용
                        if additional_value > 0:
                            values[opt_name][target_value] = additional_value
                            print(f"  {opt_name} {target_value}: +{additional_value:,} ({len(matching_items)} samples)")

        return values

    def _calculate_group_prices(self, items: List[PriceRecord], exclusive_key: str, role: str) -> Optional[Dict]:
        """그룹의 가격 통계 계산"""
        if not items:
            return None
        
        print(f"\n=== Calculating Group Prices for {exclusive_key} ({role}) ===")
        print(f"Total items in group: {len(items)}")

        # Calculate prices for each quality threshold
        quality_prices = {}
        quality_thresholds = [60, 70, 80, 90]
        
        for threshold in quality_thresholds:
            matching_items = [item for item in items if item.quality >= threshold]
            if len(matching_items) >= 2:  # Minimum 2 samples required
                prices = sorted(item.price for item in matching_items)
                # Use second lowest price to avoid outliers
                quality_prices[threshold] = prices[1] if len(prices) > 1 else prices[0]
                print(f"\nQuality {threshold}+:")
                print(f"- Sample count: {len(matching_items)}")
                print(f"- Base price: {quality_prices[threshold]:,}")

        if not quality_prices:
            return None

        # Calculate common option values using items with quality >= 60
        common_option_values = self._calculate_common_option_values(items, role, quality_prices)

        return {
            'quality_prices': quality_prices,
            'common_option_values': common_option_values,
            'total_sample_count': len(items)
        }

    def _calculate_bracelet_prices(self, grade: str, search_cycle_id: str) -> Dict:
        """팔찌 패턴별 가격 계산"""
        try:
            print(f"\n=== Calculating Bracelet Prices for {grade} Grade ===")

            with self.main_db.get_read_session() as session:

                start_time = datetime.now()
                records = session.query(BraceletPriceRecord)\
                    .filter(BraceletPriceRecord.search_cycle_id == search_cycle_id,
                            BraceletPriceRecord.grade == grade)\
                    .all()
                print(f"Bracelet DB query duration: {datetime.now() - start_time}")
                start_time = datetime.now()

                print(f"Found {len(records)} records in search cycle")

                # # 중복 제거는 더 이상 필요 없음
                # records = self._get_unique_items(records)
                # print(f"Records after deduplication: {len(records)}")

                pattern_prices = {
                    "전특2": {},
                    "전특1+기본": {},
                    "전특1+공이속": {},
                    "기본+공이속": {},  # 새로 추가된 패턴
                    "전특1+잡옵": {},
                    "전특1": {}
                }

                for record in records:
                    session.refresh(record)

                    item_data = {
                        'grade': record.grade,
                        'fixed_option_count': record.fixed_option_count,
                        'extra_option_count': record.extra_option_count,
                        'combat_stats': [(stat.stat_type, stat.value) for stat in record.combat_stats],
                        'base_stats': [(stat.stat_type, stat.value) for stat in record.base_stats],
                        'special_effects': [(effect.effect_type, effect.value) for effect in record.special_effects]
                    }

                    # return_list=True로 호출하여 모든 하위 구간의 패턴 가져오기
                    pattern_info_list = self._classify_bracelet_pattern(item_data, return_list=True)
                    if not pattern_info_list:
                        if self.debug:
                            print("No pattern found for this record")
                        continue

                    # 각 패턴에 대해 가격 정보 추가
                    for pattern_type, details in pattern_info_list:

                        key = (details['pattern'], details['values'], details['extra_slots'])

                        if pattern_type not in pattern_prices:
                            pattern_prices[pattern_type] = {}

                        if key not in pattern_prices[pattern_type]:
                            pattern_prices[pattern_type][key] = []

                        pattern_prices[pattern_type][key].append(record.price)

                print(f"Classifying bracelet patterns duration: {datetime.now() - start_time}")
                start_time = datetime.now()

                # 최종 가격 계산
                result = {}
                for pattern_type, patterns in pattern_prices.items():
                    print(f"\nProcessing {pattern_type} patterns:")

                    result[pattern_type] = {}
                    for key, prices in patterns.items():
                        if len(prices) >= 2:
                            sorted_prices = sorted(prices)
                            selected_price = sorted_prices[1]

                            print(f"\n  Pattern {key}:")
                            print(f"  - Total samples: {len(prices)}")
                            print(f"  - Price range: {min(prices):,} ~ {max(prices):,}")
                            print(f"  - Selected price: {selected_price:,}")

                            result[pattern_type][key] = selected_price, len(prices)

                print(f"Calculting bracelet group prices duration: {datetime.now() - start_time}")
                start_time = datetime.now()
                return result

        except Exception as e:
            print(f"Error calculating bracelet prices: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return {}

    def _classify_bracelet_pattern(self, item_data: Dict, return_list: bool = False) -> Union[Optional[Tuple[str, Dict]], Optional[List[Tuple[str, Dict]]]]:
        """
        팔찌 패턴 분류 및 키 생성
        return_list가 True면 해당 값 이하의 모든 구간을 포함한 패턴들의 리스트를 반환
        
        Args:
            item_data: 팔찌 데이터
            return_list: True면 가능한 모든 하위 구간의 패턴들을 리스트로 반환
            
        Returns:
            return_list=False: (pattern_type, details) tuple 또는 None
            return_list=True: List of (pattern_type, details) tuples 또는 None
        """
        grade = item_data['grade']
        fixed_count = item_data['fixed_option_count']
        extra_slots = item_data['extra_option_count']
        combat_stats = [(stat, value) for stat, value in item_data['combat_stats']]
        base_stats = [(stat, value) for stat, value in item_data['base_stats']]
        special_effects = [(effect, value) for effect, value in item_data['special_effects']]

        if self.debug:
            print("\nClassifying bracelet pattern:")
            print(f"Grade: {grade}")
            print(f"Fixed count: {fixed_count}")
            print(f"Extra slots: {extra_slots}")
            print(f"Combat stats: {combat_stats}")
            print(f"Base stats: {base_stats}")
            print(f"Special effects: {special_effects}")

        result = []  # return_list=True일 때 사용할 리스트

        # 고정 효과 2개인 경우
        if fixed_count == 2:
            if len(combat_stats) == 2:  # 전특 2개
                stat1, value1 = combat_stats[0]
                stat2, value2 = combat_stats[1]
                
                if return_list:
                    # 각 스탯의 가능한 모든 하위값 가져오기
                    values1 = self._round_combat_stat(grade, value1, return_list=True)
                    values2 = self._round_combat_stat(grade, value2, return_list=True)
                    
                    # 모든 가능한 조합 생성
                    for v1 in values1:
                        for v2 in values2:
                            stats = sorted([(stat1, v1), (stat2, v2)], key=lambda x: x[0])
                            result.append((
                                "전특2",
                                {
                                    "pattern": f"{stats[0][0]}+{stats[1][0]}",
                                    "values": f"{stats[0][1]}+{stats[1][1]}",
                                    "extra_slots": f"부여{extra_slots}"
                                }
                            ))
                else:
                    # 기존 로직
                    v1 = self._round_combat_stat(grade, value1)
                    v2 = self._round_combat_stat(grade, value2)
                    stats = sorted([(stat1, v1), (stat2, v2)], key=lambda x: x[0])
                    return (
                        "전특2",
                        {
                            "pattern": f"{stats[0][0]}+{stats[1][0]}",
                            "values": f"{stats[0][1]}+{stats[1][1]}",
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )
                        
            elif len(combat_stats) == 1 and base_stats:  # 전특1+기본
                combat = combat_stats[0]
                base = base_stats[0]
                
                if return_list:
                    combat_values = self._round_combat_stat(grade, combat[1], return_list=True)
                    base_values = self._round_base_stat(grade, base[1], return_list=True)
                    
                    for cv in combat_values:
                        for bv in base_values:
                            result.append((
                                "전특1+기본",
                                {
                                    "pattern": f"{combat[0]}+{base[0]}",
                                    "values": f"{cv}+{bv}",
                                    "extra_slots": f"부여{extra_slots}"
                                }
                            ))
                else:
                    # 기존 로직
                    cv = self._round_combat_stat(grade, combat[1])
                    bv = self._round_base_stat(grade, base[1])
                    return (
                        "전특1+기본",
                        {
                            "pattern": f"{combat[0]}+{base[0]}",
                            "values": f"{cv}+{bv}",
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )
                        
            elif len(combat_stats) == 1:  # 전특1+공이속 or 전특1+잡옵
                has_speed = any(effect.strip() == "공격 및 이동 속도 증가" 
                            for (effect, _) in special_effects)
                
                combat = combat_stats[0]
                pattern_type = "전특1+공이속" if has_speed else "전특1+잡옵"
                
                if return_list:
                    combat_values = self._round_combat_stat(grade, combat[1], return_list=True)
                    for cv in combat_values:
                        result.append((
                            pattern_type,
                            {
                                "pattern": combat[0],
                                "values": str(cv),
                                "extra_slots": f"부여{extra_slots}"
                            }
                        ))
                else:
                    # 기존 로직
                    cv = self._round_combat_stat(grade, combat[1])
                    return (
                        pattern_type,
                        {
                            "pattern": combat[0],
                            "values": str(cv),
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )
                    
            elif base_stats and any(effect == "공격 및 이동 속도 증가" 
                                for effect, _ in special_effects):  # 기본+공이속
                base = base_stats[0]
                
                if return_list:
                    base_values = self._round_base_stat(grade, base[1], return_list=True)
                    for bv in base_values:
                        result.append((
                            "기본+공이속",
                            {
                                "pattern": base[0],
                                "values": str(bv),
                                "extra_slots": f"부여{extra_slots}"
                            }
                        ))
                else:
                    # 기존 로직
                    bv = self._round_base_stat(grade, base[1])
                    return (
                        "기본+공이속",
                        {
                            "pattern": base[0],
                            "values": str(bv),
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )

        # 고정 효과 1개인 경우
        elif fixed_count == 1 and len(combat_stats) == 1:
            combat = combat_stats[0]
            
            if return_list:
                combat_values = self._round_combat_stat(grade, combat[1], return_list=True)
                for cv in combat_values:
                    result.append((
                        "전특1",
                        {
                            "pattern": combat[0],
                            "values": str(cv),
                            "extra_slots": f"부여{extra_slots}"
                        }
                    ))
            else:
                # 기존 로직
                cv = self._round_combat_stat(grade, combat[1])
                return (
                    "전특1",
                    {
                        "pattern": combat[0],
                        "values": str(cv),
                        "extra_slots": f"부여{extra_slots}"
                    }
                )

        if return_list:
            return result if result else None
        return None

    def _round_combat_stat(self, grade: str, value: float, return_list: bool = False) -> Union[int, List[int]]:
        """
        전투특성 값을 기준값으로 내림
        return_list가 True면 해당 값 이하의 모든 기준값을 리스트로 반환
        """
        thresholds = [40, 50, 60, 70, 80, 90]
        combat_stat_bonus = 20 if grade == "고대" else 0
        adjusted_thresholds = [t + combat_stat_bonus for t in thresholds]
        
        if return_list:
            # value보다 작거나 같은 모든 threshold 반환 (내림차순)
            return sorted([t for t in adjusted_thresholds if t <= value], reverse=True)
        
        # 기존 로직: 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]

    def _round_base_stat(self, grade: str, value: float, return_list: bool = False) -> Union[int, List[int]]:
        """
        기본스탯 값을 기준값으로 내림
        return_list가 True면 해당 값 이하의 모든 기준값을 리스트로 반환
        """
        thresholds = [6400, 8000, 9600, 11200]
        base_stat_bonus = 3200 if grade == "고대" else 0
        adjusted_thresholds = [t + base_stat_bonus for t in thresholds]
        
        if return_list:
            # value보다 작거나 같은 모든 threshold 반환 (내림차순)
            return sorted([t for t in adjusted_thresholds if t <= value], reverse=True)
        
        # 기존 로직: 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]

    def _is_similar_values(self, cached_values: str, target_values: str, pattern_type: str = None) -> bool:
        """
        값들이 충분히 비슷한지 확인
        전투특성은 10, 기본스탯은 1600 단위로 비교
        """
        try:
            if self.debug:
                print(f"\nComparing values for pattern {pattern_type}:")
                print(f"Cached values: {cached_values}")
                print(f"Target values: {target_values}")

            # 전특1+기본 패턴의 경우
            if pattern_type == "전특1+기본":
                if '+' not in cached_values or '+' not in target_values:
                    return False

                cached_v1, cached_v2 = map(float, cached_values.split('+'))
                target_v1, target_v2 = map(float, target_values.split('+'))

                # 첫 번째 값은 전투특성(10), 두 번째 값은 기본스탯(1600)
                combat_similar = abs(cached_v1 - target_v1) <= 10
                base_similar = abs(cached_v2 - target_v2) <= 1600

                if self.debug:
                    print(f"Combat stat comparison: {cached_v1} vs {target_v1} (diff: {abs(cached_v1 - target_v1)})")
                    print(f"Base stat comparison: {cached_v2} vs {target_v2} (diff: {abs(cached_v2 - target_v2)})")
                    print(f"Results - Combat: {combat_similar}, Base: {base_similar}")

                return combat_similar and base_similar

            # 그 외 패턴들 (전투특성만 있는 경우)
            elif '+' in cached_values and '+' in target_values:
                cached_v1, cached_v2 = map(float, cached_values.split('+'))
                target_v1, target_v2 = map(float, target_values.split('+'))
                return (abs(cached_v1 - target_v1) <= 10 and 
                    abs(cached_v2 - target_v2) <= 10)
            else:
                cached_v = float(cached_values)
                target_v = float(target_values)
                return abs(cached_v - target_v) <= 10

        except Exception as e:
            if self.debug:
                print(f"Error comparing values: {e}")
            return False

    def _get_unique_items(self, items):
        """완전히 동일한 매물은 가장 최근 것만 남김"""
        unique_items = {}
        for item in items:
            # 매물의 고유 특성을 키로 사용
            if "팔찌" in item.name:
                combat_stats = [(stat.stat_type, stat.value) for stat in item.combat_stats]
                base_stats = [(stat.stat_type, stat.value)
                              for stat in item.base_stats]
                special_effects = [(effect.effect_type, effect.value)
                                   for effect in item.special_effects]
                option_tuple = tuple(
                    sorted(combat_stats+base_stats+special_effects))
            else:
                option_tuple = tuple(sorted(
                    (opt.option_name, opt.option_value, opt.is_percentage)
                    for opt in item.raw_options 
                    if opt.option_name not in ["깨달음", "도약"]
                ))

            key = (
                item.grade,
                item.name, 
                item.part if hasattr(item, 'part') else None,  # 팔찌는 part 속성이 없음
                item.level if hasattr(item, 'level') else None,  # 팔찌는 level 속성이 없음
                item.quality if hasattr(item, 'quality') else None,  # 팔찌는 quality 속성이 없음
                item.price,
                item.trade_count,
                option_tuple
            )

            # 이미 있는 매물이면 타임스탬프 비교해서 최신 것만 유지
            if key not in unique_items or item.timestamp > unique_items[key].timestamp:
                unique_items[key] = item

        return list(unique_items.values())
