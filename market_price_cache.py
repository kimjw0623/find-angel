from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from database import *
import pickle
import time
import os
import sys
from contextlib import contextmanager, nullcontext

@contextmanager
def redirect_stdout(file_path):
    """stdout을 파일로 임시 리다이렉트하는 컨텍스트 매니저"""
    original_stdout = sys.stdout
    with open(file_path, 'a', encoding='utf-8') as f:
        sys.stdout = f
        try:
            yield
        finally:
            sys.stdout = original_stdout

class MarketPriceCache:
    def __init__(self, db_manager, debug=False):
        self.db = db_manager
        self.debug = debug
        self.cache_file_path = 'market_price_cache.pkl'
        self.lock_file_path = 'market_price_cache.lock'
        
        # 캐시 초기화
        self.cache = {
            "dealer": {},
            "support": {}
        }
        self.last_update = None
        
        # 파일에서 캐시 로드 시도
        self._load_cache()

        self.COMMON_OPTIONS = {
            # 딜러용 부가 옵션
            "깡공": [80.0, 195.0, 390.0],
            "깡무공": [195.0, 480.0, 960.0],
            # 서포터용 부가 옵션
            "최생": [1300.0, 3250.0, 6500.0],
            "최마": [6.0, 15.0, 30.0],
            "아군회복": [0.95, 2.1, 3.5],
            "아군보호막": [0.95, 2.1, 3.5]
        }

    # -----------------------------
    # Cache Management Methods
    # -----------------------------
    
    def _acquire_lock(self):
        """파일 락 획득"""
        while True:
            try:
                with open(self.lock_file_path, 'x'):  # 파일이 존재하지 않을 때만 생성
                    return
            except FileExistsError:
                time.sleep(0.1)

    def _release_lock(self):
        """파일 락 해제"""
        try:
            os.remove(self.lock_file_path)
        except FileNotFoundError:
            pass

    def _load_cache(self):
        """파일에서 캐시 데이터 로드"""
        try:
            self._acquire_lock()
            if os.path.exists(self.cache_file_path):
                with open(self.cache_file_path, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.cache = cache_data.get('cache', self.cache)
                    self.last_update = cache_data.get('last_update', None)
                    
                    if self.debug:
                        print(f"Cache loaded from file. Last update: {self.last_update}")
                        print(f"Dealer cache entries: {len(self.cache['dealer'])}")
                        print(f"Support cache entries: {len(self.cache['support'])}")
        except Exception as e:
            if self.debug:
                print(f"Error loading cache: {e}")
        finally:
            self._release_lock()

    def _save_cache(self):
        """캐시 데이터를 파일에 저장"""
        try:
            self._acquire_lock()
            cache_data = {
                'cache': self.cache,
                'last_update': self.last_update
            }
            with open(self.cache_file_path, 'wb') as f:
                pickle.dump(cache_data, f)
                
            if self.debug:
                print(f"Cache saved to file at {datetime.now()}")
        except Exception as e:
            if self.debug:
                print(f"Error saving cache: {e}")
        finally:
            self._release_lock()

    # -----------------------------
    # Public Interface Methods
    # -----------------------------

    def get_price_data(self, grade: str, part: str, level: int, 
                      options: Dict[str, List[Tuple[str, float]]]) -> Dict[str, Optional[Dict]]:
        """가격 데이터 조회"""
        current_time = datetime.now()
        
        # 캐시가 없거나 1시간 이상 지난 경우 업데이트
        if (not self.last_update or 
            current_time - self.last_update > timedelta(hours=1)):
            if self.debug:
                print(f"\nUpdating cache because it's {'missing' if not self.last_update else 'old'}")
                if self.last_update:
                    print(f"Last update: {self.last_update}")
                    print(f"Time since last update: {current_time - self.last_update}")
            self.update_cache()
            
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
            if self.debug:
                start_time = datetime.now()

            new_cache = {
                "dealer": {},
                "support": {}
            }

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
                    
                    # 부위 확인
                    if "목걸이" in record.name:
                        part = "목걸이"
                        dealer_options = [("추피", opt.option_value) for opt in record.raw_options if opt.option_name == "추피"]
                        dealer_options.extend([("적주피", opt.option_value) for opt in record.raw_options if opt.option_name == "적주피"])
                        support_options = [("아덴게이지", opt.option_value) for opt in record.raw_options if opt.option_name == "아덴게이지"]
                        support_options.extend([("낙인력", opt.option_value) for opt in record.raw_options if opt.option_name == "낙인력"])
                    elif "귀걸이" in record.name:
                        part = "귀걸이"
                        dealer_options = [("공퍼", opt.option_value) for opt in record.raw_options if opt.option_name == "공퍼"]
                        dealer_options.extend([("무공퍼", opt.option_value) for opt in record.raw_options if opt.option_name == "무공퍼"])
                        support_options = []  # 귀걸이는 서폿 전용옵 없음
                    elif "반지" in record.name:
                        part = "반지"
                        dealer_options = [("치적", opt.option_value) for opt in record.raw_options if opt.option_name == "치적"]
                        dealer_options.extend([("치피", opt.option_value) for opt in record.raw_options if opt.option_name == "치피"])
                        support_options = [("아공강", opt.option_value) for opt in record.raw_options if opt.option_name == "아공강"]
                        support_options.extend([("아피강", opt.option_value) for opt in record.raw_options if opt.option_name == "아피강"])
                    else:
                        continue

                    # 딜러용/서포터용 키 생성
                    if dealer_options:
                        dealer_key = f"{record.grade}:{part}:{record.level}:{sorted(dealer_options)}"
                        if dealer_key not in dealer_groups:
                            dealer_groups[dealer_key] = []
                        dealer_groups[dealer_key].append(record)

                    if support_options:
                        support_key = f"{record.grade}:{part}:{record.level}:{sorted(support_options)}"
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

            self.cache = new_cache
            self.last_update = datetime.now()
            
            # 캐시 파일 저장
            self._save_cache()

            if self.debug:
                end_time = datetime.now()
                print(f"Cache update completed in {(end_time - start_time).total_seconds():.2f} seconds")
                print(f"Dealer cache entries: {len(new_cache['dealer'])}")
                print(f"Support cache entries: {len(new_cache['support'])}")

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
        
        dealer_key = f"{grade}:{part}:{level}:{dealer_exclusive}" if dealer_exclusive else None
        support_key = f"{grade}:{part}:{level}:{support_exclusive}" if support_exclusive else None
        
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
        """전투특성 값을 가까운 기준값으로 반올림"""
        thresholds = [40, 50, 60, 70, 80, 90]
        return min(thresholds, key=lambda x: abs(x - value))

    def _round_base_stat(self, value: float) -> int:
        """기본스탯 값을 가까운 기준값으로 반올림"""
        thresholds = [6400, 8000, 9600, 11200]
        return min(thresholds, key=lambda x: abs(x - value))

    def _calculate_common_option_values(self, items: List[PriceRecord], exclusive_key: str, role: str):
        """각 Common 옵션 값의 추가 가치를 계산"""
        MIN_SAMPLES = 3
        if len(items) < MIN_SAMPLES:
            if self.debug:
                print(f"\n=== Common Option Value Calculation for {exclusive_key} ({role}) ===")
                print(f"Insufficient initial samples: {len(items)} < {MIN_SAMPLES}")
                print("Extending time range to 48 hours...")
            
            # 시간 범위를 48시간으로 확장하여 데이터 추가 조회
            with self.db.get_read_session() as session:
                extended_time = datetime.now() - timedelta(hours=48)
                if self.debug:
                    print(f"Querying data since: {extended_time}")

                additional_items = session.query(PriceRecord).filter(
                    PriceRecord.timestamp >= extended_time,
                    PriceRecord.grade == exclusive_key.split(':')[0],
                    PriceRecord.part == exclusive_key.split(':')[1],
                    PriceRecord.level == int(exclusive_key.split(':')[2])
                ).all()
                
                items.extend([item for item in additional_items if item not in items])
                
                if self.debug:
                    print(f"After 48h extension: {len(items)} samples")

                # 48시간으로 확장해도 샘플이 부족하면 72시간까지 확장
                if len(items) < MIN_SAMPLES:
                    print("Still insufficient samples, extending to 72 hours...")
                    extended_time = datetime.now() - timedelta(hours=72)
                    if self.debug:
                        print(f"Querying data since: {extended_time}")

                    additional_items = session.query(PriceRecord).filter(
                        PriceRecord.timestamp >= extended_time,
                        PriceRecord.grade == exclusive_key.split(':')[0],
                        PriceRecord.part == exclusive_key.split(':')[1],
                        PriceRecord.level == int(exclusive_key.split(':')[2])
                    ).all()
                    
                    items.extend([item for item in additional_items if item not in items])
                    if self.debug:
                        print(f"After 72h extension: {len(items)} samples")

        # 여전히 샘플이 부족하면 빈 딕셔너리 반환
        if len(items) < MIN_SAMPLES:
            if self.debug:
                print("Still insufficient samples after time extension. Returning empty values.")
            return {}
        
        # 역할별 관련 옵션 정의
        role_related_options = {
            "dealer": ["깡공", "깡무공"],
            "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
        }

        # Base 가격 계산 (해당 역할의 common 옵션이 없는 아이템들의 최저값)
        with self.db.get_read_session() as session:
            if self.debug:
                print("\nCalculating base price:")
                print(f"Total items to process: {len(items)}")

            # 아이템들의 ID 목록을 만들고
            item_ids = [item.id for item in items]
            
            # ID로 아이템들을 다시 조회
            fresh_items = session.query(PriceRecord).filter(
                PriceRecord.id.in_(item_ids)
            ).all()

            # base_items 계산
            base_items = [item for item in fresh_items 
                        if not any(opt.option_name in role_related_options[role] 
                                for opt in item.raw_options)]

            if self.debug:
                print(f"Items without common options: {len(base_items)}")

            # base_price 계산
            if not base_items:
                if self.debug:
                    print("No pure base items found, using all items for base price calculation")
                prices = np.array([item.price for item in fresh_items])
                sorted_prices = np.sort(prices)
                base_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]
            else:
                if self.debug:
                    print(f"Using {len(base_items)} pure base items for calculation")
                prices = np.array([item.price for item in base_items])
                sorted_prices = np.sort(prices)
                base_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]

            if self.debug:
                print(f"Selected base price: {base_price:,}")

            values = {}
            # 역할별 관련 옵션에 대해서만 계산
            for opt_name in role_related_options[role]:
                if opt_name in self.COMMON_OPTIONS:
                    if self.debug:
                        print(f"\nProcessing option: {opt_name}")
                    
                    values[opt_name] = {}
                    for value in self.COMMON_OPTIONS[opt_name]:
                        matching_items = [item for item in fresh_items 
                                        if any(opt.option_name == opt_name and 
                                            abs(opt.option_value - value) < 0.1 
                                            for opt in item.raw_options)]
                        
                        if self.debug:
                            print(f"  {opt_name} {value}: Found {len(matching_items)} matching items")
                        
                        if matching_items:
                            matching_prices = np.array([item.price for item in matching_items])
                            sorted_matching_prices = np.sort(matching_prices)
                            min_price = sorted_matching_prices[1] if len(sorted_matching_prices) > 1 else sorted_matching_prices[0]
                            additional_value = min_price - base_price
                            
                            if self.debug:
                                print(f"    Price range: {np.min(matching_prices):,} ~ {np.max(matching_prices):,}")
                                print(f"    Selected min price: {min_price:,}")
                                print(f"    Additional value: {additional_value:,}")
                            
                            if additional_value > 0:
                                values[opt_name][value] = additional_value

            if self.debug:
                print("\nFinal common option values:")
                for opt_name, opt_values in values.items():
                    print(f"{opt_name}:")
                    for value, additional in opt_values.items():
                        print(f"  {value}: +{additional:,}")

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
            elif opt.option_name in ["최생", "최마"]:
                support_options.append((opt.option_name, opt.option_value))

        return support_options

    def _calculate_group_prices(self, items: List[PriceRecord], exclusive_key: str, role: str) -> Optional[Dict]:
        """그룹의 가격 통계 계산"""
        if not items:
            return None
        
        # debug 모드일 때 로그 파일로 출력 리다이렉트
        # debug_context = (redirect_stdout('price_calculation.log') if self.debug else nullcontext())
        # 그냥, 항상 파일로 출력 리다이렉트
        debug_context = redirect_stdout('price_calculation.log')
        
        with debug_context:
            if self.debug:
                print(f"\n=== Calculating Group Prices for {exclusive_key} ({role}) ===")
                print(f"Total items in group: {len(items)}")
            
            role_related_options = {
                "dealer": ["깡공", "깡무공"],
                "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
            }

            # 기본 가격 계산 (common 옵션 제외)
            base_items = [item for item in items 
                        if not any(opt.option_name in role_related_options[role] 
                                for opt in item.raw_options)]
            
            if self.debug:
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
            target_items = base_items if base_items else items
            if self.debug and not base_items:
                print("\nNo pure base items found, using all items for base calculation")
            
            for item in target_items:
                prices.append(item.price)
                qualities.append(item.quality)
                trade_counts.append(item.trade_count)

            # 첫 번째 단계: 두 번째로 낮은 가격을 base 가격으로 설정
            prices = np.array(prices)
            sorted_prices = np.sort(prices)
            
            if self.debug:
                print(f"\nStep 1 - Before filtering:")
                print(f"- Initial price range: {np.min(prices):,} ~ {np.max(prices):,}")
                print(f"- Lowest prices (sorted): {sorted_prices[:5]}")  # 가장 낮은 5개 가격 출력
            
            # base 가격 계산 (두 번째로 낮은 가격)
            base_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]
            
            if self.debug:
                print(f"\nBase price calculation:")
                print(f"- Second lowest price selected as base: {base_price:,}")

            # 두 번째 단계: base 가격의 일정 배수 초과 제외
            MAX_PRICE_MULTIPLIER = 5.0
            mask = prices <= base_price * MAX_PRICE_MULTIPLIER
            filtered_prices = prices[mask]
            filtered_qualities = np.array(qualities)[mask]
            filtered_trade_counts = np.array(trade_counts)[mask]

            if self.debug:
                print(f"\nStep 2 - After removing prices > {base_price * MAX_PRICE_MULTIPLIER:,.0f} (base_price * {MAX_PRICE_MULTIPLIER}):")
                print(f"- Final remaining samples: {len(filtered_prices)}/{len(prices)}")
                print(f"- Final price range: {np.min(filtered_prices):,} ~ {np.max(filtered_prices):,}")
                print(f"- Quality range: {np.min(filtered_qualities)} ~ {np.max(filtered_qualities)}")
                print(f"- Trade count range: {np.min(filtered_trade_counts)} ~ {np.max(filtered_trade_counts)}")
        
            if len(filtered_prices) < 3:
                if self.debug:
                    print("\nInsufficient samples after filtering")
                return None

            # 계수 계산
            quality_coefficient = self._calculate_quality_coefficient(filtered_prices, filtered_qualities)
            trade_coefficient = self._calculate_trade_coefficient(filtered_prices, filtered_trade_counts)

            if self.debug:
                print("\nCalculated coefficients:")
                print(f"- Quality coefficient: {quality_coefficient:,.2f}")
                print(f"- Trade count coefficient: {trade_coefficient:,.2f}")

            # Common 옵션 값 계산
            common_option_values = self._calculate_common_option_values(items, exclusive_key, role)

            if self.debug:
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
            # debug 모드일 때 로그 파일로 출력 리다이렉트
            # debug_context = (redirect_stdout('price_calculation.log') if self.debug else nullcontext())
            # 그냥, 항상 파일로 출력 리다이렉트
            debug_context = redirect_stdout('price_calculation.log')
                
            with debug_context:
                if self.debug:
                    print(f"\n=== Calculating Bracelet Prices for {grade} Grade ===")
                
                with self.db.get_read_session() as session:
                    recent_time = datetime.now() - timedelta(hours=24)
                    
                    records = session.query(BraceletPriceRecord).filter(
                        BraceletPriceRecord.timestamp >= recent_time,
                        BraceletPriceRecord.grade == grade
                    ).all()

                    if self.debug:
                        print(f"Found {len(records)} records in last 24 hours")

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
                        if self.debug:
                            print("\nProcessing record:")
                            print(f"Fixed options: {record.fixed_option_count}")
                            print(f"Extra options: {record.extra_option_count}")
                            print(f"Combat stats: {item_data['combat_stats']}")
                            print(f"Base stats: {item_data['base_stats']}")
                            print(f"Special effects: {item_data['special_effects']}")

                        pattern_info = self._classify_bracelet_pattern(item_data)
                        if not pattern_info:
                            if self.debug:
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
                    if self.debug:
                        print("\nPattern counts:")
                        for pattern_type, count in pattern_counts.items():
                            print(f"{pattern_type}: {count}")

                    # 최종 가격 계산
                    result = {}
                    for pattern_type, patterns in pattern_prices.items():
                        if self.debug:
                            print(f"\nProcessing {pattern_type} patterns:")
                            
                        result[pattern_type] = {}
                        for key, prices in patterns.items():
                            if len(prices) >= 2:
                                sorted_prices = sorted(prices)
                                selected_price = sorted_prices[1]
                                
                                if self.debug:
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
        current_time = datetime.now()
        
        # 캐시가 없거나 1시간 이상 지난 경우 업데이트
        if (not self.last_update or 
            current_time - self.last_update > timedelta(hours=1)):
            if self.debug:
                print(f"\nUpdating cache because it's {'missing' if not self.last_update else 'old'}")
                if self.last_update:
                    print(f"Last update: {self.last_update}")
                    print(f"Time since last update: {current_time - self.last_update}")
            self.update_cache()

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
                if self._is_similar_values(cached_values, details['values']):
                    if self.debug:
                        print(f"\nSimilar pattern match found:")
                        print(f"Original pattern: {pattern_type} {key}")
                        print(f"Matched pattern: {pattern_type} {cached_key}")
                        print(f"Price: {price:,}")
                    return price

        if self.debug:
            print(f"No matching pattern found for {pattern_type} {key}")
        return None

    def _is_similar_values(self, cached_values: str, target_values: str) -> bool:
        """값들이 충분히 비슷한지 확인"""
        try:
            if '+' in cached_values and '+' in target_values:
                cached_v1, cached_v2 = map(float, cached_values.split('+'))
                target_v1, target_v2 = map(float, target_values.split('+'))
                return (abs(cached_v1 - target_v1) <= 10 and 
                    abs(cached_v2 - target_v2) <= 10)
            else:
                cached_v = float(cached_values)
                target_v = float(target_values)
                return abs(cached_v - target_v) <= 10
        except:
            return False