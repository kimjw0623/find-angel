from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
from src.database.raw_database import (
    RawDatabaseManager, AuctionAccessory, AuctionBracelet, 
    AuctionStatus, ItemOption, RawItemOption, 
    BraceletCombatStat, BraceletBaseStat, BraceletSpecialEffect
)
from src.database.pattern_database import (
    PatternDatabaseManager, AuctionPricePattern, 
    AccessoryPricePattern, BraceletPricePattern
)
from src.common.types import (
    MemoryPatterns, PatternKey, AccessoryPatternData, BraceletPatternData,
    OptionList, OptionTuple, QualityPrices, CommonOptionValues,
    BraceletPatternType, BraceletPatternKey, BraceletPriceInfo,
    BraceletPatternDetails, BraceletItemData, Role
)
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

class PricePatternAnalyzer:
    def __init__(self, main_db_manager: RawDatabaseManager, debug: bool = False):
        self.main_db = main_db_manager  # 기존 DB (데이터 읽기용)
        self.pattern_db = PatternDatabaseManager()  # 패턴 데이터베이스
        self.debug = debug
        # 패턴 생성 전용 - 메모리 캐시 제거

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

    def _load_patterns(self) -> None:
        """현재 활성화된 패턴 데이터 로드"""
        with self.pattern_db.get_read_session() as session:
            # 활성화된 캐시 찾기
            active_pattern = session.query(AuctionPricePattern).filter_by(is_active=True).first()
            
            if not active_pattern:
                if self.debug:
                    print("No active pattern found, initializing empty patterns")
                self.memory_patterns = {
                    "dealer": {},
                    "support": {},
                    "bracelet_고대": {},
                    "bracelet_유물": {}
                }
                return

            # 악세서리 패턴 로드
            accessory_patterns = session.query(AccessoryPricePattern).filter_by(
                pattern_id=active_pattern.pattern_id
            ).all()

            # 팔찌 패턴 로드
            bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                pattern_id=active_pattern.pattern_id
            ).all()

            # 캐시 데이터 구성
            self.memory_patterns = {
                "dealer": {},
                "support": {},
                "bracelet_고대": {},
                "bracelet_유물": {}
            }

            # 악세서리 패턴 처리
            for pattern in accessory_patterns:
                pattern_key = f"{pattern.grade}:{pattern.part}:{pattern.level}:{pattern.pattern_key}"
                # SQLiteJSON이 자동으로 dict로 변환해줌 (테스트)
                # 만약 문자열로 나오면 json.loads() 필요, dict로 나오면 불필요
                raw_common_values = pattern.common_option_values  # type: ignore
                raw_quality_prices = pattern.quality_prices  # type: ignore
                
                print(f"DEBUG: common_option_values type: {type(raw_common_values)}")
                print(f"DEBUG: quality_prices type: {type(raw_quality_prices)}")
                
                if isinstance(raw_common_values, str):
                    converted_common_option_values = convert_json_keys_to_float(json.loads(raw_common_values))
                else:
                    converted_common_option_values = convert_json_keys_to_float(raw_common_values)
                    
                if isinstance(raw_quality_prices, str):
                    converted_base_prices = convert_json_keys_to_int(json.loads(raw_quality_prices))
                else:
                    converted_base_prices = convert_json_keys_to_int(raw_quality_prices)
                
                pattern_data = {
                    'quality_prices': converted_base_prices,
                    'common_option_values': converted_common_option_values,
                    'total_sample_count': pattern.total_sample_count,
                    'last_update': active_pattern.pattern_id
                }
                
                if pattern.role == 'dealer':  # type: ignore
                    self.memory_patterns['dealer'][pattern_key] = pattern_data # type: ignore
                else:
                    self.memory_patterns['support'][pattern_key] = pattern_data # type: ignore

            # 팔찌 패턴 처리
            for pattern in bracelet_patterns:
                pattern_key = (
                    pattern.combat_stats,
                    pattern.base_stats,
                    pattern.extra_slots
                )
                bracelet_pattern_first_key = f'bracelet_{pattern.grade}'
                try:
                    self.memory_patterns[bracelet_pattern_first_key][pattern.pattern_type][pattern_key] = pattern.price, pattern.total_sample_count  # type: ignore
                except KeyError:
                    self.memory_patterns[bracelet_pattern_first_key][pattern.pattern_type] = {}  # type: ignore
                    self.memory_patterns[bracelet_pattern_first_key][pattern.pattern_type][pattern_key] = pattern.price, pattern.total_sample_count  # type: ignore

            if self.debug:
                print(f"Patterns loaded. Last update: {active_pattern.pattern_id}")
                print(f"Dealer pattern entries: {len(self.memory_patterns['dealer'])}")
                print(f"Support pattern entries: {len(self.memory_patterns['support'])}")
                print(f"고대 팔찌 pattern entries: {len(self.memory_patterns['bracelet_고대'])}")
                print(f"유물 팔찌 pattern entries: {len(self.memory_patterns['bracelet_유물'])}")

    def get_last_update_time(self) -> Optional[datetime]:
        """캐시의 마지막 업데이트 시간 확인"""
        with self.pattern_db.get_read_session() as session:
            active_pattern = session.query(AuctionPricePattern).filter_by(is_active=True).first()
            return active_pattern.pattern_id if active_pattern else None  # type: ignore

    def get_price_data(self, grade: str, part: str, level: int, 
                      options: Dict[str, OptionList]) -> Dict[str, Optional[AccessoryPatternData]]:
        """가격 데이터 조회"""            
        dealer_key, support_key = self.get_pattern_key(grade, part, level, options)
        
        pattern_data: Dict[str, Optional[AccessoryPatternData]] = {
            "dealer": None,
            "support": None
        }

        if dealer_key and dealer_key in self.memory_patterns["dealer"]:
            pattern_data["dealer"] = self.memory_patterns["dealer"][dealer_key]
            if self.debug:
                print(f"\nDealer pattern hit for {dealer_key}")
                print(f"Quality prices: {pattern_data['dealer']['quality_prices']}")
                print(f"Sample count: {pattern_data['dealer']['total_sample_count']}")

        if support_key and support_key in self.memory_patterns["support"]:
            pattern_data["support"] = self.memory_patterns["support"][support_key]
            if self.debug:
                print(f"\nSupport pattern hit for {support_key}")
                print(f"Quality prices: {pattern_data['support']['quality_prices']}")
                print(f"Sample count: {pattern_data['support']['total_sample_count']}")

        return pattern_data

    def get_bracelet_price(self, grade: str, item_data: BraceletItemData) -> Optional[Union[int, BraceletPriceInfo]]:
        """팔찌 가격 조회"""
        pattern_info = self._classify_bracelet_pattern(item_data)
        # print(f"찾아진 패턴 for item {item_data}: {pattern_info}")
        if not pattern_info:
            return None

        pattern_type, details = pattern_info
        key = (details['pattern'], details['values'], details['extra_slots']) # type: ignore

        # 캐시에서 해당 패턴의 가격 조회
        pattern_key = f"bracelet_{grade}"

        # 1. 기본적인 캐시 존재 여부 확인
        if pattern_key not in self.memory_patterns:
            if self.debug:
                print(f"No pattern data found for {pattern_key}")
            return None

        # 2. 해당 패턴 타입의 가격 데이터 가져오기
        pattern_prices = self.memory_patterns[pattern_key].get(pattern_type, {})

        # 3. 정확한 매칭 시도
        if key in pattern_prices:
            if self.debug:
                print(f"\nExact pattern match found:")
                print(f"Pattern: {pattern_type} {key}")
                print(f"Price: {pattern_prices[key]:,}")
            return pattern_prices[key]

        # 4. 정확한 매칭이 없는 경우 비슷한 패턴 찾기
        # (기존 비슷한 패턴 찾기 로직 유지)
        for stored_key, (price, total_sample_count) in pattern_prices.items():
            stored_pattern, stored_values, stored_extra = stored_key
            if (stored_pattern == details['pattern'] and  # type: ignore
                stored_extra == details['extra_slots']): # type: ignore
                if self._is_similar_values(stored_values, details['values'], pattern_type): # type: ignore
                    if self.debug:
                        print(f"\nSimilar pattern match found:")
                        print(f"Original pattern: {pattern_type} {key}")
                        print(f"Matched pattern: {pattern_type} {stored_key}")
                        print(f"Price: {price:,}")
                    return (price, total_sample_count)

        if self.debug:
            print(f"No matching pattern found for {pattern_type} {key}")

        return None

    def update_pattern(self, pattern_id: datetime, send_signal: bool = True) -> bool:
        """
        특정 search_cycle의 시장 가격 데이터로 캐시 업데이트
        
        Args:
            pattern_id: 캐시를 생성할 search_cycle의 ID
            send_signal: IPC 신호 발송 여부 (기본값: True)
            
        Returns:
            bool: 캐시 업데이트 성공 여부
        """
        try:
            # 로그 파일 설정
            print(f"Search cycle: {pattern_id.isoformat()}")
            log_filename = f'pattern_log/pattern_calculation_{pattern_id.isoformat().replace(":", "-")}.log'
            
            # pattern_log 디렉토리 생성
            os.makedirs('pattern_log', exist_ok=True)

            with redirect_stdout(log_filename):
                new_patterns = {
                    "dealer": {},
                    "support": {},
                    "bracelet_고대": {},
                    "bracelet_유물": {}
                }

                with self.main_db.get_read_session() as session:
                    # pattern_id가 이미 datetime 객체
                    search_timestamp = pattern_id
                    
                    # 해당 시간에 처음 발견된 데이터가 있는지 확인
                    cycle_info = session.query(AuctionAccessory)\
                        .filter(AuctionAccessory.first_seen_at == search_timestamp)\
                        .first()
                    
                    if not cycle_info:
                        print(f"No data found for search cycle {pattern_id.isoformat()}")
                        return False
                        
                    print(f"Processing data from search cycle at {pattern_id.isoformat()}")
                    
                    # 해당 search_cycle의 데이터 조회
                    start_time = datetime.now()
                    records = session.query(AuctionAccessory)\
                        .filter(AuctionAccessory.first_seen_at == search_timestamp)\
                        .all()
                    query_duration = (datetime.now() - start_time).total_seconds()
                    print(f"DB query duration: {query_duration:.1f}s")
                    print(f"Found {len(records)} acc records in search cycle")
                    start_time = datetime.now()

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
                    classify_duration = (datetime.now() - start_time).total_seconds()
                    print(f"Classifying acc patterns duration: {classify_duration:.1f}s")
                    start_time = datetime.now()

                    # 각 그룹별로 가격 계산
                    for key, items in dealer_groups.items():
                        if len(items) >= 3:  # 최소 3개 이상의 데이터가 있는 경우만
                            price_data = self._calculate_group_prices(items, key, "dealer")
                            if price_data:
                                new_patterns["dealer"][key] = price_data

                    for key, items in support_groups.items():
                        if len(items) >= 3:
                            price_data = self._calculate_group_prices(items, key, "support")
                            if price_data:
                                new_patterns["support"][key] = price_data

                    calc_duration = (datetime.now() - start_time).total_seconds()
                    print(f"Calculating acc group prices duration: {calc_duration:.1f}s")

                    # 팔찌 가격 업데이트
                    for grade in ["고대", "유물"]:
                        pattern_key = f"bracelet_{grade}"
                        new_patterns[pattern_key] = self._calculate_bracelet_prices(grade, pattern_id)
                        
                # 새로운 패턴 ID 생성
                new_pattern_id = str(uuid.uuid4())
                start_time = datetime.now()

                with self.pattern_db.get_write_session() as write_session:
                    # 가장 최근 search_cycle인지 확인
                    latest_cycle = write_session.query(AuctionPricePattern.pattern_id)\
                        .order_by(AuctionPricePattern.pattern_id.desc())\
                        .first()  # type: ignore
                    
                    # 테이블이 비어있거나, 현재 cycle이 더 최신인 경우 True
                    is_latest = not latest_cycle or latest_cycle.pattern_id <= pattern_id.isoformat()  # type: ignore
                    
                    print(f"Latest cycle id: {latest_cycle.pattern_id if latest_cycle else 'None'}")
                    print(f"Current pattern id: {pattern_id.isoformat()}")
                    print(f"Is latest: {is_latest}")

                    # 새 패턴 메타데이터 생성
                    new_pattern_entry = AuctionPricePattern(
                        pattern_id=new_pattern_id,
                        pattern_id=pattern_id.isoformat(),  # datetime을 string으로 변환
                        is_active=is_latest
                    )

                    if is_latest:
                        # 기존 활성 패턴 비활성화
                        write_session.query(AuctionPricePattern).filter_by(is_active=True).update(
                            {"is_active": False}
                        )
                    write_session.add(new_pattern_entry)
                    write_session.flush()

                    # 악세서리 패턴 저장
                    for role in ['dealer', 'support']:
                        for pattern_key, pattern_data in new_patterns[role].items():
                            grade, part, level, pattern_key = pattern_key.split(':')
                            
                            acc_pattern = AccessoryPricePattern(
                                pattern_id=new_pattern_id,
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
                        bracelet_data = new_patterns[f'bracelet_{grade}']
                        for pattern_type, patterns in bracelet_data.items():
                            for pattern_key, (price, total_sample_count) in patterns.items():
                                combat_stats, base_stats, extra_slots = pattern_key
                                
                                bracelet_pattern = BraceletPricePattern(
                                    pattern_id=new_pattern_id,
                                    grade=grade,
                                    pattern_type=pattern_type,
                                    combat_stats=combat_stats,
                                    base_stats=base_stats,
                                    extra_slots=extra_slots,
                                    price=price,
                                    total_sample_count=total_sample_count
                                )
                                write_session.add(bracelet_pattern)

                    write_duration = (datetime.now() - start_time).total_seconds()
                    print(f"Writing patterns duration: {write_duration:.1f}s")

                print(f"Pattern collection created with ID {new_pattern_id} for search cycle {pattern_id.isoformat()}")
                
                # 패턴 업데이트 완료 신호 발송 (옵션)
                if send_signal:
                    self._send_pattern_update_signal(pattern_id)
                
                return True

        except Exception as e:
            print(f"Error updating price patterns: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_pattern_key(self, grade: str, part: str, level: int, options: Dict[str, OptionList]) -> Tuple[PatternKey, PatternKey]:
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

    def _calculate_common_option_values(self, items: List[AuctionAccessory], role: Role, quality_prices: QualityPrices) -> CommonOptionValues: 
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

    def _calculate_group_prices(self, items: List[AuctionAccessory], exclusive_key: str, role: Role) -> Optional[AccessoryPatternData]:
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

        result: AccessoryPatternData = {
            'quality_prices': quality_prices,
            'common_option_values': common_option_values,
            'total_sample_count': len(items),
            'last_update': ''  # 이 값은 나중에 설정됨
        }
        return result

    def _calculate_bracelet_prices(self, grade: str, pattern_id: datetime) -> BraceletPatternData:
        """팔찌 패턴별 가격 계산"""
        try:
            print(f"\n=== Calculating Bracelet Prices for {grade} Grade ===")

            with self.main_db.get_read_session() as session:

                start_time = datetime.now()
                search_timestamp = pattern_id
                records = session.query(AuctionBracelet)\
                    .filter(AuctionBracelet.first_seen_at == search_timestamp,
                            AuctionBracelet.grade == grade)\
                    .all()
                bracelet_query_duration = (datetime.now() - start_time).total_seconds()
                print(f"Bracelet DB query duration: {bracelet_query_duration:.1f}s")
                print(f"Found {len(records)} records in search cycle")
                start_time = datetime.now()

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

                bracelet_classify_duration = (datetime.now() - start_time).total_seconds()
                print(f"Classifying bracelet patterns duration: {bracelet_classify_duration:.1f}s")
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

                bracelet_calc_duration = (datetime.now() - start_time).total_seconds()
                print(f"Calculting bracelet group prices duration: {bracelet_calc_duration:.1f}s")
                return result

        except Exception as e:
            print(f"Error calculating bracelet prices: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return {}

    def _classify_bracelet_pattern(self, item_data: BraceletItemData, return_list: bool = False) -> Union[Optional[Tuple[BraceletPatternType, BraceletPatternDetails]], Optional[List[Tuple[BraceletPatternType, BraceletPatternDetails]]]]:
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
                    for v1 in values1:  # type: ignore
                        for v2 in values2:  # type: ignore
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
                    
                    for cv in combat_values:  # type: ignore  # type: ignore
                        for bv in base_values:  # type: ignore  # type: ignore
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
                    for cv in combat_values:  # type: ignore
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
                    for bv in base_values:  # type: ignore
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

    def _is_similar_values(self, stored_values: str, target_values: str, pattern_type: str = None) -> bool:
        """
        값들이 충분히 비슷한지 확인
        전투특성은 10, 기본스탯은 1600 단위로 비교
        """
        try:
            if self.debug:
                print(f"\nComparing values for pattern {pattern_type}:")
                print(f"Stored values: {stored_values}")
                print(f"Target values: {target_values}")

            # 전특1+기본 패턴의 경우
            if pattern_type == "전특1+기본":
                if '+' not in stored_values or '+' not in target_values:
                    return False

                stored_v1, stored_v2 = map(float, stored_values.split('+'))
                target_v1, target_v2 = map(float, target_values.split('+'))

                # 첫 번째 값은 전투특성(10), 두 번째 값은 기본스탯(1600)
                combat_similar = abs(stored_v1 - target_v1) <= 10
                base_similar = abs(stored_v2 - target_v2) <= 1600

                if self.debug:
                    print(f"Combat stat comparison: {stored_v1} vs {target_v1} (diff: {abs(stored_v1 - target_v1)})")
                    print(f"Base stat comparison: {stored_v2} vs {target_v2} (diff: {abs(stored_v2 - target_v2)})")
                    print(f"Results - Combat: {combat_similar}, Base: {base_similar}")

                return combat_similar and base_similar

            # 그 외 패턴들 (전투특성만 있는 경우)
            elif '+' in stored_values and '+' in target_values:
                stored_v1, stored_v2 = map(float, stored_values.split('+'))
                target_v1, target_v2 = map(float, target_values.split('+'))
                return (abs(stored_v1 - target_v1) <= 10 and 
                    abs(stored_v2 - target_v2) <= 10)
            else:
                stored_v = float(stored_values)
                target_v = float(target_values)
                return abs(stored_v - target_v) <= 10

        except Exception as e:
            if self.debug:
                print(f"Error comparing values: {e}")
            return False

    def _send_pattern_update_signal(self, pattern_id: datetime):
        """패턴 업데이트 완료 신호를 item_evaluator에 발송"""
        try:
            from src.common.ipc_utils import notify_pattern_update
            result = notify_pattern_update(pattern_id)
            if result:
                print(f"📡 Pattern update signal sent via IPC: {pattern_id.isoformat()}")
            else:
                print(f"📡 Pattern update signal sent (no active listeners): {pattern_id.isoformat()}")
        except Exception as e:
            print(f"Warning: Failed to send pattern update signal: {e}")
