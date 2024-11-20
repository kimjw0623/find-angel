from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from database import *
import pickle
import time
import os
import sys
import threading
from contextlib import contextmanager, nullcontext

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

class DoubleBufferCache:
    def __init__(self, cache_name: str):
        """
        Double buffering cache initialization
        cache_name: 캐시 파일의 기본 이름 (예: 'market_price')
        """
        self.cache_name = cache_name
        self.cache_files = [f"{cache_name}_0.pkl", f"{cache_name}_1.pkl"]
        self.active_index_file = f"{cache_name}_active.txt"  # 현재 활성화된 캐시 인덱스
        self.lock_file_path = f"{cache_name}_active.lock"  # 현재 활성화된 캐시 인덱스의 락 파일
        self._initialize_cache_files()

    def _initialize_cache_files(self):
        """캐시 파일이 없는 경우 빈 캐시로 초기화"""
        empty_cache = {
            'data': {},
            'last_update': None
        }
        for file in self.cache_files:
            if not os.path.exists(file):
                with open(file, 'wb') as f:
                    pickle.dump(empty_cache, f)

        # active_index_file 초기화
        if not os.path.exists(self.active_index_file):
            with open(self.active_index_file, 'w') as f:
                f.write('0|None')

    def get_active_cache(self) -> tuple[Any, Optional[datetime]]:
        """현재 활성화된 캐시 데이터와 마지막 업데이트 시간 반환"""
        self._acquire_lock()
        try:
            with open(self.active_index_file, 'r') as f:
                active_index, last_update_str = f.read().strip().split('|')
                active_index = int(active_index)
                if last_update_str == 'None':
                    last_update = None
                else:
                    last_update = datetime.fromisoformat(last_update_str)
            active_file = self.cache_files[active_index]
            try:
                with open(active_file, 'rb') as f:
                    cache_data = pickle.load(f)
                return cache_data['data'], last_update
            except Exception as e:
                print(f"Error reading active cache: {e}")
                return {}, None
        finally:
            self._release_lock()

    def update_cache(self, new_data: Any) -> bool:
        """
        새로운 데이터로 캐시 업데이트
        1. 비활성 캐시에 새 데이터 쓰기
        2. 성공하면 활성 캐시 전환
        """
        self._acquire_lock()
        try:
            with open(self.active_index_file, 'r') as f:
                active_index, _ = f.read().strip().split('|')
                active_index = int(active_index)
            pending_index = 1 - active_index
            pending_file = self.cache_files[pending_index]

            try:
                # 새 데이터를 비활성 캐시에 쓰기
                cache_data = {
                    'data': new_data,
                    'last_update': datetime.now()
                }
                with open(pending_file, 'wb') as f:
                    pickle.dump(cache_data, f)

                # 캐시 전환
                with open(self.active_index_file, 'w') as f:
                    f.write(f"{pending_index}|{cache_data['last_update'].isoformat()}")
                return True

            except Exception as e:
                print(f"Error updating cache: {e}")
                return False
        finally:
            self._release_lock()

    def get_last_update_time(self) -> Optional[datetime]:
        """현재 활성화된 캐시의 마지막 업데이트 시간 반환"""
        self._acquire_lock()
        try:
            with open(self.active_index_file, 'r') as f:
                active_index, last_update_str = f.read().strip().split('|')
                if last_update_str == 'None':
                    return None
                else:
                    return datetime.fromisoformat(last_update_str)
        finally:
            self._release_lock()

    def cleanup(self):
        """캐시 파일 정리 (필요한 경우)"""
        try:
            for file in self.cache_files:
                if os.path.exists(file):
                    os.remove(file)
            if os.path.exists(self.active_index_file):
                os.remove(self.active_index_file)
        except Exception as e:
            print(f"Error cleaning up cache files: {e}")

    def _acquire_lock(self):
        while True:
            try:
                with open(self.lock_file_path, 'x'):  # 파일이 존재하지 않을 때만 생성
                    return
            except FileExistsError:
                time.sleep(0.1)

    def _release_lock(self):
        os.remove(self.lock_file_path)

class MarketPriceCache:
    def __init__(self, db_manager, debug=False):
        self.db = db_manager
        self.debug = debug

        # Double Buffer 캐시 초기화
        self.cache_manager = DoubleBufferCache('market_price_cache')
        
        # 초기 캐시 데이터 구조
        self.cache_structure = {
            "dealer": {},
            "support": {},
            "bracelet_고대": {},
            "bracelet_유물": {}
        }
        
        # 캐시 로드
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

    # -----------------------------
    # Cache Management Methods
    # -----------------------------
    
    def _load_cache(self):
        """캐시 데이터 로드"""
        self.cache, self.last_update = self.cache_manager.get_active_cache()
        if not self.cache:  # 캐시가 비어있으면 기본 구조로 초기화
            self.cache = self.cache_structure.copy()
            
        if self.debug:
            print(f"Cache loaded. Last update: {self.last_update}")
            print(f"Dealer cache entries: {len(self.cache['dealer'])}")
            print(f"Support cache entries: {len(self.cache['support'])}")
            print(f"고대 팔찌 cache entries: {len(self.cache['bracelet_고대'])}")
            print(f"유물 팔찌 cache entries: {len(self.cache['bracelet_유물'])}")

    def get_last_update_time(self) -> Optional[datetime]:
        """캐시의 마지막 업데이트 시간 확인"""
        return self.cache_manager.get_last_update_time()

    # -----------------------------
    # Public Interface Methods
    # -----------------------------

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

    def update_cache(self):
        """시장 가격 데이터 업데이트"""
        try:
            print("\nUpdating price cache...")
            start_time = datetime.now()
            timestamp = start_time.strftime("%Y%m%d_%H%M%S")
            log_filename = f'price_log/price_calculation_{timestamp}.log'

            with redirect_stdout(log_filename):
                new_cache = self.cache_structure.copy()

                with self.db.get_read_session() as session:
                    recent_time = datetime.now() - timedelta(hours=24)
                    
                    # 최근 24시간 데이터 조회
                    records = session.query(PriceRecord).filter(
                        PriceRecord.timestamp >= recent_time
                    ).all()

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
                                
                # 팔찌 가격 업데이트
                for grade in ["고대", "유물"]:
                    cache_key = f"bracelet_{grade}"
                    new_cache[cache_key] = self._calculate_bracelet_prices(grade)

            # Double Buffer 캐시 업데이트
            if self.cache_manager.update_cache(new_cache):
                # 업데이트 성공 시 현재 인스턴스의 캐시도 업데이트
                self.cache = new_cache
                self.last_update = datetime.now()
                print(f"Cache update completed in {(datetime.now() - start_time).total_seconds():.2f} seconds")
            else:
                print("Cache update failed")
                
        except Exception as e:
            print(f"Error updating price cache: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()

    def get_cache_key(self, grade: str, part: str, level: int, options: Dict[str, List[Tuple[str, float]]]) -> str:
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

    def _classify_bracelet_pattern(self, item_data: Dict) -> Tuple[str, Dict]:
        """팔찌 패턴 분류 및 키 생성"""
        fixed_count = item_data['fixed_option_count']
        extra_slots = item_data['extra_option_count']
        combat_stats = [(stat, value) for stat, value in item_data['combat_stats']]
        base_stats = [(stat, value) for stat, value in item_data['base_stats']]
        special_effects = [(effect, value) for effect, value in item_data['special_effects']]
        
        # 디버깅을 위한 출력 추가
        if self.debug:
            print("\nClassifying bracelet pattern:")
            print(f"Fixed count: {fixed_count}")
            print(f"Combat stats: {combat_stats}")
            print(f"Base stats: {base_stats}")
            print(f"Special effects: {special_effects}")
            print(f"Extra slots: {extra_slots}")
        
        # 고정 효과 2개인 경우
        if fixed_count == 2:
            # 디버깅을 위한 출력
            if self.debug:
                print("Checking fixed count 2 patterns")
                
            if len(combat_stats) == 2:  # 전특 2개
                if self.debug:
                    print("Found 전특2 pattern")
                stats = sorted([(stat, self._round_combat_stat(value)) for stat, value in combat_stats],
                            key=lambda x: x[0])  # 스탯명으로 정렬
                return (
                    "전특2",
                    {
                        "pattern": f"{stats[0][0]}+{stats[1][0]}",
                        "values": f"{stats[0][1]}+{stats[1][1]}",
                        "extra_slots": f"부여{extra_slots}"
                    }
                )
            elif len(combat_stats) == 1 and base_stats:  # 전특1+기본
                if self.debug:
                    print("Found 전특1+기본 pattern")
                combat = (combat_stats[0][0], self._round_combat_stat(combat_stats[0][1]))
                base = (base_stats[0][0], self._round_base_stat(base_stats[0][1]))
                return (
                    "전특1+기본",
                    {
                        "pattern": f"{combat[0]}+{base[0]}",
                        "values": f"{combat[1]}+{base[1]}",
                        "extra_slots": f"부여{extra_slots}"
                    }
                )
            elif len(combat_stats) == 1:  # 전특1+공이속 또는 전특1+잡옵
                if self.debug:
                    print(f"Checking 전특1 patterns with special effects: {special_effects}")
                
                if any(effect.strip() == "공격 및 이동 속도 증가" for (effect, _) in special_effects):
                    if self.debug:
                        print("Found 전특1+공이속 pattern")
                    combat = (combat_stats[0][0], self._round_combat_stat(combat_stats[0][1]))
                    return (
                        "전특1+공이속",
                        {
                            "pattern": combat[0],
                            "values": str(combat[1]),
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )
                else:
                    if self.debug:
                        print("Found 전특1+잡옵 pattern")
                    combat = (combat_stats[0][0], self._round_combat_stat(combat_stats[0][1]))
                    return (
                        "전특1+잡옵",
                        {
                            "pattern": combat[0],
                            "values": str(combat[1]),
                            "extra_slots": f"부여{extra_slots}"
                        }
                    )
        
        # 고정 효과 1개인 경우
        elif fixed_count == 1 and len(combat_stats) == 1:
            if self.debug:
                print("Found 전특1 pattern")
            combat = (combat_stats[0][0], self._round_combat_stat(combat_stats[0][1]))
            return (
                "전특1",
                {
                    "pattern": combat[0],
                    "values": str(combat[1]),
                    "extra_slots": f"부여{extra_slots}"
                }
            )
        
        if self.debug:
            print("No matching pattern found")
        return None

    def _round_combat_stat(self, value: float) -> int:
        """전투특성 값을 기준값으로 내림"""
        thresholds = [40, 50, 60, 70, 80, 90, 100, 110]
        for threshold in thresholds:
            if value < threshold:
                return thresholds[max(0, thresholds.index(threshold) - 1)]
        return thresholds[-1]

    def _round_base_stat(self, value: float) -> int:
        """기본스탯 값을 기준값으로 내림"""
        thresholds = [6400, 8000, 9600, 11200, 12800, 14400]
        for threshold in thresholds:
            if value < threshold:
                return thresholds[max(0, thresholds.index(threshold) - 1)]
        return thresholds[-1]

    def _calculate_common_option_values(self, filtered_items: List[PriceRecord], exclusive_key: str, role: str):
        """각 Common 옵션 값의 추가 가치를 계산"""
        MIN_SAMPLES = 3
        if len(filtered_items) < MIN_SAMPLES:
            print(f"\nInsufficient samples for common option calculation: {len(filtered_items)} < {MIN_SAMPLES}")
            return {}

        # exclusive_key에서 정보 추출
        grade, part, level, *_ = exclusive_key.split(':')
        
        # 역할별 관련 옵션 정의
        role_related_options = {
            "dealer": ["깡공", "깡무공"],
            "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
        }

        # base_items 계산 (common 옵션이 없는 아이템)
        base_items = [item for item in filtered_items 
                    if not any(opt.option_name in role_related_options[role] 
                            for opt in item.raw_options)]

        if not base_items:
            print("\nNo pure base items found, using filtered items for base price")
            prices = [item.price for item in filtered_items]
        else:
            print(f"\nUsing {len(base_items)} pure base items")
            prices = [item.price for item in base_items]

        sorted_prices = sorted(prices)
        base_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]
        print(f"Selected base price: {base_price:,}")

        values = {}
        # 역할별 관련 옵션에 대해서만 계산
        for opt_name in role_related_options[role]:
            if opt_name in self.COMMON_OPTIONS:
                print(f"\nProcessing option: {opt_name}")
                
                values[opt_name] = {}
                for value in self.COMMON_OPTIONS[opt_name]:
                    matching_items = [item for item in filtered_items 
                                    if any(opt.option_name == opt_name and 
                                        abs(opt.option_value - value) < 0.1 
                                        for opt in item.raw_options)]
                    
                    if matching_items:
                        matching_prices = [item.price for item in matching_items]
                        sorted_matching_prices = sorted(matching_prices)
                        # min_price = sorted_matching_prices[1] if len(sorted_matching_prices) > 1 else sorted_matching_prices[0]
                        min_price = sorted_matching_prices[1] if len(sorted_matching_prices) > 3 else base_price # 4개 이상 있어야 계산
                        additional_value = min_price - base_price
                        
                        if additional_value > 0:
                            values[opt_name][value] = additional_value
                            print(f"  {opt_name} {value}: +{additional_value:,} ({len(matching_items)} samples)")

        return values
               
    def _extract_dealer_options(self, record: PriceRecord) -> List[Tuple[str, float]]:
        """딜러용 주요 옵션 추출"""
        dealer_options = []
        
        for opt in record.raw_options:
            if opt.option_name in ["깨달음", "도약"]:
                continue
                
            # 부위별 전용 옵션
            if ((record.part == "목걸이" and opt.option_name in ["추피", "적주피"]) or
                (record.part == "귀걸이" and opt.option_name in ["공퍼", "무공퍼"]) or
                (record.part == "반지" and opt.option_name in ["치적", "치피"])):
                dealer_options.append((opt.option_name, opt.option_value))
                
            # 딜러 공통 옵션
            elif opt.option_name in ["깡무공", "깡공"]:
                dealer_options.append((opt.option_name, opt.option_value))

        return dealer_options

    def _extract_support_options(self, record: PriceRecord) -> List[Tuple[str, float]]:
        """서포터용 주요 옵션 추출"""
        support_options = []
        
        for opt in record.raw_options:
            if opt.option_name in ["깨달음", "도약"]:
                continue
                
            # 부위별 전용 옵션
            if ((record.part == "목걸이" and opt.option_name in ["아덴게이지", "낙인력"]) or
                (record.part == "귀걸이" and opt.option_name in ["무공퍼"]) or
                (record.part == "반지" and opt.option_name in ["아공강", "아피강"])):
                support_options.append((opt.option_name, opt.option_value))
                
            # 서포터 공통 옵션
            elif opt.option_name in ["깡무공", "최생", "최마", "아군보호막", "아군회복"]:
                support_options.append((opt.option_name, opt.option_value))

        return support_options

    def _calculate_group_prices(self, items: List[PriceRecord], exclusive_key: str, role: str) -> Optional[Dict]:
        """그룹의 가격 통계 계산"""
        if not items:
            return None
        print(f"\n=== Calculating Group Prices for {exclusive_key} ({role}) ===")
        print(f"Total items in group: {len(items)}")

        # 중복 제거
        items = self._get_unique_items(items)
        print(f"Total items after deduplication: {len(items)}")
        
        # exclusive_key에서 정보 추출
        grade, part, level, *_ = exclusive_key.split(':')

        with self.db.get_read_session() as session:
            # 아이템들의 ID 목록
            item_ids = [item.id for item in items]
            
            print("\nStarting item filtering:")
            print(f"Initial item count: {len(item_ids)}")

            query = session.query(PriceRecord).filter(
                PriceRecord.id.in_(item_ids)
            )

            initial_count = query.count()
            print(f"Items after initial filter: {initial_count}")

            # 같은 exclusive 그룹의 다른 옵션들이 없는 아이템만 선택
            for group_role in ["dealer", "support"]:
                for exc_opt in self.EXCLUSIVE_OPTIONS[part][group_role]:
                    # 현재 검색 중인 옵션은 건너뛰기
                    if exc_opt in exclusive_key:
                        continue
                    # 다른 exclusive 옵션이 있는 아이템 제외
                    subq = (session.query(ItemOption.price_record_id)
                        .filter(ItemOption.option_name == exc_opt)
                        .scalar_subquery())

                    query = query.filter(~PriceRecord.id.in_(subq))

                    count_after = query.count()
                    print(f"Items after excluding {exc_opt}: {count_after}")

            filtered_items = query.all()
            print(f"\nItems after exclusive option filtering: {len(filtered_items)}")

            role_related_options = {
                "dealer": ["깡공", "깡무공"],
                "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
            }

            # 기본 가격 계산 (common 옵션 제외)
            base_items = [item for item in items 
                        if not any(opt.option_name in role_related_options[role] 
                                for opt in item.raw_options)]
        
            print(f"\nBase items (without common options): {len(base_items)}")
            if base_items:
                print("Sample base items:")
                for item in base_items[:3]:
                    print(f"- Price: {item.price:,}, Quality: {item.quality}, "
                        f"Trade Count: {item.trade_count}")
        
            prices = []
            qualities = []
            trade_counts = []

            # base_items가 있으면 그것만 사용, 없으면 전체 사용
            target_items = base_items if base_items else filtered_items
            if not base_items:
                print("\nNo pure base items found, using all items for base calculation")
        
            for item in target_items:
                prices.append(item.price)
                qualities.append(item.quality)
                trade_counts.append(item.trade_count)

            # 첫 번째 단계: 두 번째로 낮은 가격을 base 가격으로 설정
            prices = np.array(prices)
            sorted_prices = np.sort(prices)
        
            print(f"\nStep 1 - Before filtering:")
            print(f"- Initial price range: {np.min(prices):,} ~ {np.max(prices):,}")
            print(f"- Lowest prices (sorted): {sorted_prices[:5]}")  # 가장 낮은 5개 가격 출력
        
            # base 가격 계산 (두 번째로 낮은 가격)
            base_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]
            print(f"\nBase price calculation:")
            print(f"- Second lowest price selected as base: {base_price:,}")

            # 두 번째 단계: base 가격의 일정 배수 초과 제외
            MAX_PRICE_MULTIPLIER = 5.0
            mask = prices <= base_price * MAX_PRICE_MULTIPLIER
            filtered_prices = prices[mask]
            filtered_qualities = np.array(qualities)[mask]
            filtered_trade_counts = np.array(trade_counts)[mask]

            print(f"\nStep 2 - After removing prices > {base_price * MAX_PRICE_MULTIPLIER:,.0f} (base_price * {MAX_PRICE_MULTIPLIER}):")
            print(f"- Final remaining samples: {len(filtered_prices)}/{len(prices)}")
            print(f"- Final price range: {np.min(filtered_prices):,} ~ {np.max(filtered_prices):,}")
            print(f"- Quality range: {np.min(filtered_qualities)} ~ {np.max(filtered_qualities)}")
            print(f"- Trade count range: {np.min(filtered_trade_counts)} ~ {np.max(filtered_trade_counts)}")
    
            if len(filtered_prices) < 3:
                print("\nInsufficient samples after filtering")
                return None

            # 계수 계산
            quality_coefficient = self._calculate_quality_coefficient(filtered_prices, filtered_qualities)
            trade_coefficient = self._calculate_trade_coefficient(filtered_prices, filtered_trade_counts)

            print("\nCalculated coefficients:")
            print(f"- Quality coefficient: {quality_coefficient:,.2f}")
            print(f"- Trade count coefficient: {trade_coefficient:,.2f}")

            # Common 옵션 값 계산
            common_option_values = self._calculate_common_option_values(filtered_items, exclusive_key, role)

            print("\nFinal price statistics:")
            print(f"- Base price: {np.min(filtered_prices):,}")
            print(f"- Standard deviation: {np.std(filtered_prices):,.2f}")
            print(f"- Sample count: {len(filtered_prices)}")

            return {
                'base_price': np.min(filtered_prices),
                'price_std': np.std(filtered_prices),
                'quality_coefficient': max(0, quality_coefficient),  # 품질 계수는 항상 양수
                'trade_count_coefficient': min(0, trade_coefficient),  # 거래 횟수 계수는 항상 음수
                'common_option_values': common_option_values,
                'sample_count': len(filtered_prices),
                'total_sample_count': len(items),
                'last_update': datetime.now()
            }

    def _calculate_quality_coefficient(self, prices, qualities) -> float:
        """품질에 따른 가격 계수 계산"""
        if len(set(qualities)) <= 1:
            return 0
        slope, _ = np.polyfit(qualities, prices, 1)
        return slope

    def _calculate_trade_coefficient(self, prices, trade_counts) -> float:
        """거래 횟수에 따른 가격 계수 계산"""
        if len(set(trade_counts)) <= 1:
            return 0
        slope, _ = np.polyfit(trade_counts, prices, 1)
        return slope
    
    def _calculate_bracelet_prices(self, grade: str) -> Dict:
        """팔찌 패턴별 가격 계산"""
        try:
            print(f"\n=== Calculating Bracelet Prices for {grade} Grade ===")
            
            with self.db.get_read_session() as session:
                recent_time = datetime.now() - timedelta(hours=24)
                
                records = session.query(BraceletPriceRecord).filter(
                    BraceletPriceRecord.timestamp >= recent_time,
                    BraceletPriceRecord.grade == grade
                ).all()

                print(f"Found {len(records)} records in last 24 hours before deduplication")
                
                # 중복 제거
                records = self._get_unique_items(records)
                print(f"Records after deduplication: {len(records)}")

                pattern_prices = {
                    "전특2": {},
                    "전특1+기본": {},
                    "전특1+공이속": {},
                    "전특1+잡옵": {},
                    "전특1": {}
                }

                # 패턴별 카운트 추가
                pattern_counts = {k: 0 for k in pattern_prices.keys()}

                for record in records:
                    session.refresh(record)
                    
                    item_data = {
                        'fixed_option_count': record.fixed_option_count,
                        'extra_option_count': record.extra_option_count,
                        'combat_stats': [(stat.stat_type, stat.value) for stat in record.combat_stats],
                        'base_stats': [(stat.stat_type, stat.value) for stat in record.base_stats],
                        'special_effects': [(effect.effect_type, effect.value) for effect in record.special_effects]
                    }

                    # 디버깅을 위한 출력 추가
                    print("\nProcessing record:")
                    print(f"Fixed options: {record.fixed_option_count}")
                    print(f"Extra options: {record.extra_option_count}")
                    print(f"Combat stats: {item_data['combat_stats']}")
                    print(f"Base stats: {item_data['base_stats']}")
                    print(f"Special effects: {item_data['special_effects']}")

                    pattern_info = self._classify_bracelet_pattern(item_data)
                    if not pattern_info:
                        print("No pattern found for this record")
                        continue

                    pattern_type, details = pattern_info
                    pattern_counts[pattern_type] += 1  # 패턴 카운트 증가
                    
                    key = (details['pattern'], details['values'], details['extra_slots'])
                    
                    if pattern_type not in pattern_prices:
                        pattern_prices[pattern_type] = {}
                    
                    if key not in pattern_prices[pattern_type]:
                        pattern_prices[pattern_type][key] = []
                    
                    pattern_prices[pattern_type][key].append(record.price)

                # 패턴별 통계 출력
                print("\nPattern counts:")
                for pattern_type, count in pattern_counts.items():
                    print(f"{pattern_type}: {count}")

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
                            
                            result[pattern_type][key] = selected_price

                return result

        except Exception as e:
            print(f"Error calculating bracelet prices: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return {}

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
        for cached_key, price in pattern_prices.items():
            cached_pattern, cached_values, cached_extra = cached_key
            if (cached_pattern == details['pattern'] and 
                cached_extra == details['extra_slots']):
                if self._is_similar_values(cached_values, details['values'], pattern_type):
                    if self.debug:
                        print(f"\nSimilar pattern match found:")
                        print(f"Original pattern: {pattern_type} {key}")
                        print(f"Matched pattern: {pattern_type} {cached_key}")
                        print(f"Price: {price:,}")
                    return price

        if self.debug:
            print(f"No matching pattern found for {pattern_type} {key}")

        return None

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