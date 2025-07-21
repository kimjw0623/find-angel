"""
패턴 생성 전용 클래스 - DB에 패턴 데이터 저장만 담당
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import sys
import uuid
import json
import numpy as np
import os
from contextlib import contextmanager

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
    OptionList, OptionTuple, QualityPrices, CommonOptionValues,
    BraceletPatternType, BraceletPatternKey, BraceletPriceInfo,
    BraceletPatternDetails, BraceletItemData, Role
)

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

def cleanup_old_logs(log_dir='pattern_log', days=3):
    """days일 이상 지난 로그 파일 삭제"""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        return
        
    cutoff = datetime.now() - timedelta(days=days)
    
    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if os.path.getmtime(filepath) < cutoff.timestamp():
            os.remove(filepath)

class PatternGenerator:
    """패턴 생성 전용 클래스"""
    
    def __init__(self, main_db_manager: RawDatabaseManager, debug: bool = False):
        self.main_db = main_db_manager  # 기존 DB (데이터 읽기용)
        self.pattern_db = PatternDatabaseManager()  # 패턴 데이터베이스
        self.debug = debug

        self.MIN_SAMPLES = 3  # 최소 샘플 수
        self.SOLD_ITEMS_WINDOW = timedelta(days=7)  # SOLD 상태 아이템 조회 기간
        self.SOLD_PRICE_WEIGHT = 0.95  # SOLD 상태 아이템 가격 가중치
        
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
            # 오래된 로그파일 정리 (3일 이상)
            cleanup_old_logs('pattern_log', days=3)
            
            # 로그 파일 설정
            print(f"\nUpdating pattern at {pattern_id}")
            log_filename = f'pattern_log/pattern_calculation_{pattern_id.isoformat().replace(":", "-")}.log'

            with redirect_stdout(log_filename):
                with self.pattern_db.get_write_session() as write_session:
                    # 새 패턴 ID 생성
                    new_pattern_id = str(uuid.uuid4())

                    print(f"Processing search cycle: {pattern_id.isoformat()}")
                    print(f"Generating pattern with ID: {new_pattern_id}")

                    # 기존 활성 패턴 확인
                    latest_cycle = write_session.query(AuctionPricePattern)\
                        .order_by(AuctionPricePattern.pattern_id.desc())\
                        .first()
                    
                    # 테이블이 비어있거나, 현재 cycle이 더 최신인 경우 True
                    is_latest = not latest_cycle or latest_cycle.pattern_id <= pattern_id.isoformat()
                    
                    print(f"Latest cycle id: {latest_cycle.pattern_id if latest_cycle else 'None'}")
                    print(f"Current pattern id: {pattern_id.isoformat()}")
                    print(f"Is latest: {is_latest}")

                    # 새 패턴 메타데이터 생성
                    new_pattern_entry = AuctionPricePattern(
                        pattern_id=new_pattern_id,
                        search_cycle_id=pattern_id.isoformat(),
                        is_active=is_latest
                    )

                    if is_latest: # type: ignore
                        # 기존 활성 패턴 비활성화
                        write_session.query(AuctionPricePattern).filter_by(is_active=True).update(
                            {"is_active": False}
                        )

                    write_session.add(new_pattern_entry)

                    # 악세서리 패턴 생성
                    start_time = datetime.now()
                    print(f"Starting accessory pattern generation...")
                    
                    # 1. 모든 ACTIVE/SOLD 악세서리 한 번에 가져오기
                    with self.main_db.get_read_session() as read_session:
                        active_accessories = (
                            read_session.query(AuctionAccessory)
                            .filter(
                                (AuctionAccessory.status == AuctionStatus.ACTIVE)
                                | (
                                    (AuctionAccessory.status == AuctionStatus.SOLD)
                                    & (
                                        AuctionAccessory.sold_at
                                        >= datetime.now() - timedelta(days=7)
                                    )
                                )
                            )
                            .all()
                        )

                    print(f"DB query duration: {datetime.now() - start_time}")
                    start_time = datetime.now()
                    print(f"Found {len(active_accessories)} active records at {timestamp_str}")

                    # 딜러용/서포터용 데이터 그룹화
                    dealer_groups = {}
                    support_groups = {}

                    for accessory in active_accessories:
                        dealer_options, support_options = self._classify_accessory_patterns(accessory)

                        # 딜러용/서포터용 키 생성
                        dealer_key = f"{accessory.grade}:{accessory.part}:{accessory.level}:{sorted(dealer_options)}" if dealer_options else f"{accessory.grade}:{accessory.part}:{accessory.level}:base"
                        if dealer_key not in dealer_groups:
                            dealer_groups[dealer_key] = []
                        dealer_groups[dealer_key].append(accessory)

                        support_key = f"{accessory.grade}:{accessory.part}:{accessory.level}:{sorted(support_options)}" if support_options else f"{accessory.grade}:{accessory.part}:{accessory.level}:base"
                        if support_key not in support_groups:
                            support_groups[support_key] = []
                        support_groups[support_key].append(accessory)
                    
                    print(f"Classifying acc patterns duration: {datetime.now() - start_time}")
                    start_time = datetime.now()

                    # 각 그룹별로 가격 계산 및 저장
                    accessory_count = 0
                    for key, items in dealer_groups.items():
                        grade, part, level, pattern_key = key.split(':', 3)
                        price_data = self._calculate_group_prices(items, grade, part, int(level), "dealer")
                        if price_data:
                            acc_pattern = AccessoryPricePattern(
                                pattern_id=new_pattern_id,
                                grade=grade,
                                part=part,
                                level=int(level),
                                pattern_key=pattern_key,
                                role="dealer",
                                quality_prices=price_data['quality_prices'],
                                total_sample_count=price_data['total_sample_count'],
                                common_option_values=price_data['common_option_values']
                            )
                            write_session.add(acc_pattern)
                            accessory_count += 1

                    for key, items in support_groups.items():
                        grade, part, level, pattern_key = key.split(':', 3)
                        price_data = self._calculate_group_prices(items, grade, part, int(level), "support")
                        if price_data:
                            acc_pattern = AccessoryPricePattern(
                                pattern_id=new_pattern_id,
                                grade=grade,
                                part=part,
                                level=int(level),
                                pattern_key=pattern_key,
                                role="support",
                                quality_prices=price_data['quality_prices'],
                                total_sample_count=price_data['total_sample_count'],
                                common_option_values=price_data['common_option_values']
                            )
                            write_session.add(acc_pattern)
                            accessory_count += 1

                    accessory_duration = (datetime.now() - start_time).total_seconds()
                    print(f"Calculating acc group prices duration: {accessory_duration:.1f}s")
                    print(f"Generated {accessory_count} accessory patterns")

                    # 팔찌 패턴 생성
                    start_time = datetime.now()
                    print(f"🔍 Starting bracelet pattern generation...")
                    
                    bracelet_count = 0
                    for grade in ["유물", "고대"]:
                        bracelet_data = self._calculate_bracelet_prices(grade, pattern_id)
                        
                        for pattern_type, pattern_dict in bracelet_data.items():
                            for pattern_key, (price, total_sample_count) in pattern_dict.items():
                                combat_stats, base_stats, extra_slots = pattern_key
                                
                                bracelet_pattern = BraceletPricePattern(
                                    pattern_id=new_pattern_id,
                                    grade=grade,
                                    pattern_type=pattern_type,
                                    combat_stats=combat_stats,
                                    base_stats=base_stats,
                                    extra_slots=extra_slots,
                                    price=price,
                                    total_sample_count=total_sample_count,
                                    pattern_data={pattern_key: (price, total_sample_count)}
                                )
                                write_session.add(bracelet_pattern)
                                bracelet_count += 1

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

    def _get_items_by_filter(self, grade: str, part: str, level: int, role: str) -> List[AuctionAccessory]:
        """조건에 맞는 아이템들 조회"""
        with self.main_db.get_read_session() as session:
            # 기본 필터링
            query = session.query(AuctionAccessory).filter(
                AuctionAccessory.grade == grade,
                AuctionAccessory.part == part,
                AuctionAccessory.level == level,
                AuctionAccessory.quality >= 67,
                AuctionAccessory.price.is_not(None),
                AuctionAccessory.price > 0
            )

            items = query.all()
            
            # 역할별 필터링
            filtered_items = []
            exclusive_options = self.EXCLUSIVE_OPTIONS.get(part, {}).get(role, [])
            
            for item in items:
                has_exclusive = any(
                    opt.option_name in exclusive_options 
                    for opt in item.raw_options
                )
                
                if role == "dealer" and has_exclusive:
                    filtered_items.append(item)
                elif role == "support" and has_exclusive:
                    filtered_items.append(item)
            
            return filtered_items

    def _calculate_group_prices(self, items: List[AuctionAccessory], grade: str, part: str, level: int, role: str) -> Optional[Dict]:
        """그룹의 가격 통계 계산"""
        if not items:
            return None
        
        print(f"\n=== Calculating Group Prices for {grade} {part} {level} ({role}) ===")
        print(f"Total items in group: {len(items)}")
        
        filtered_items = []
        excluded_option_names = set()

        # 현재 역할이 아닌 다른 역할의 exclusive 옵션 수집
        for group_role in ["dealer", "support"]:
            if group_role != role and part in self.EXCLUSIVE_OPTIONS:
                for exc_opt in self.EXCLUSIVE_OPTIONS[part].get(group_role, []):
                    excluded_option_names.add(exc_opt)

        # 아이템별로 옵션 검사
        for item in items:
            has_excluded_option = False
            for option in item.raw_options:
                if option.option_name in excluded_option_names:
                    has_excluded_option = True
                    break
            if not has_excluded_option:
                filtered_items.append(item)

        print(f"Items after exclusive option filtering: {len(filtered_items)}")

        # Calculate prices for each quality threshold
        quality_prices = {}
        quality_thresholds = [60, 70, 80, 90]

        for threshold in quality_thresholds:
            # 품질 범위 필터링 (SQLAlchemy 컬럼이 아닌 Python 값으로 비교)
            active_items = []
            for item in filtered_items:
                item_quality = int(item.quality) if item.quality else 60
                if threshold <= item_quality < threshold + 10 and item.status == AuctionStatus.ACTIVE:
                    active_items.append(item)
            
            # ACTIVE 아이템이 10개 미만이면 SOLD 아이템 추가
            if len(active_items) < 10:
                sold_items = []
                for item in filtered_items:
                    item_quality = int(item.quality) if item.quality else 60
                    if threshold <= item_quality < threshold + 10 and item.status == AuctionStatus.SOLD:
                        sold_items.append(item)
                
                # SOLD 아이템 정렬 (sold_at이 None인 경우 처리)
                sold_items.sort(key=lambda x: x.sold_at or datetime.min, reverse=True)
                needed_items = 10 - len(active_items)
                added_sold = min(needed_items, len(sold_items))
                matching_items = active_items + sold_items[:needed_items]
                if sold_items:
                    last_sold_at = matching_items[-1].sold_at or "Unknown"
                    first_sold_at = sold_items[0].sold_at or "Unknown"
                    print(f"품질분석 [{threshold}+] | ACTIVE: {len(active_items)}개 | SOLD 추가: +{added_sold}개, SOLD 아이템 기간: {last_sold_at} ~ {first_sold_at}")
                else:
                    print(f"품질분석 [{threshold}+] | ACTIVE: {len(active_items)}개 | SOLD 추가: +0개")
            else:
                matching_items = active_items
                print(f"품질분석 [{threshold}+] | ACTIVE: {len(active_items)}개")
                
            prices = sorted([int(item.price) for item in matching_items if item.price])
            base_price = calculate_reasonable_price(prices)
            if base_price:
                quality_prices[threshold] = base_price
            
        if not quality_prices:
            return None

        # Calculate common option values using items with quality >= 60
        common_option_values = self._calculate_common_option_values(filtered_items, role, quality_prices)

        return {
            'quality_prices': quality_prices,
            'common_option_values': common_option_values,
            'total_sample_count': len(items)
        }

    def _calculate_common_option_values(self, items: List[AuctionAccessory], role: str, quality_prices: Dict[int, int]) -> Dict: 
        """각 Common 옵션 값의 추가 가치를 계산"""
        MIN_SAMPLE = 10

        role_related_options = {
            "dealer": ["깡공", "깡무공"],
            "support": ["깡무공", "최생", "최마", "아군회복", "아군보호막"]
        }

        values = {}
        for opt_name in role_related_options[role]:
            if opt_name in self.COMMON_OPTIONS:
                values[opt_name] = {}

                for target_value in self.COMMON_OPTIONS[opt_name]:
                    # ACTIVE 아이템 필터링
                    active_items = []
                    for item in items:
                        if item.status == AuctionStatus.ACTIVE:
                            for opt in item.raw_options:
                                if opt.option_name == opt_name and opt.option_value == target_value:
                                    active_items.append(item)
                                    break

                    # ACTIVE 아이템이 10개 미만이면 SOLD 아이템 추가
                    if len(active_items) < MIN_SAMPLE:
                        sold_items = []
                        for item in items:
                            if item.status == AuctionStatus.SOLD:
                                for opt in item.raw_options:
                                    if opt.option_name == opt_name and opt.option_value == target_value:
                                        sold_items.append(item)
                                        break
                        
                        # 최신 SOLD 아이템부터 정렬 (sold_at이 None인 경우 처리)
                        sold_items.sort(key=lambda x: x.sold_at or datetime.min, reverse=True)
                        needed_sold = min(MIN_SAMPLE - len(active_items), len(sold_items))
                        matching_items = active_items + sold_items[:needed_sold]
                        if sold_items:
                            last_sold_at = matching_items[-1].sold_at or "Unknown"
                            first_sold_at = sold_items[0].sold_at or "Unknown"
                            print(f"부가옵션분석 [{opt_name} {target_value}] | ACTIVE: {len(active_items)}개 | SOLD 추가: +{needed_sold}개, SOLD 아이템 기간: {last_sold_at} ~ {first_sold_at}")
                        else:
                            print(f"부가옵션분석 [{opt_name} {target_value}] | ACTIVE: {len(active_items)}개 | SOLD 추가: +0개")
                    else:
                        matching_items = active_items
                        print(f"부가옵션분석 [{opt_name} {target_value}] | ACTIVE: {len(active_items)}개")

                    additional_values = []
                    for item in matching_items:
                        item_quality = int(item.quality) if item.quality else 60
                        quality_cut = 90 if item_quality >= 90 else (item_quality // 10) * 10
                        valid_cutoffs = [qc for qc in quality_prices.keys() if int(qc) <= quality_cut]
                        if valid_cutoffs:
                            actual_quality_cut = max(valid_cutoffs)
                            base_price = quality_prices[actual_quality_cut]
                            item_price = int(item.price) if item.price else 0
                            added_value = max(item_price - base_price, 0)
                            additional_values.append(added_value)

                    if additional_values:
                        sorted_values = sorted(additional_values)
                        additional_value = calculate_reasonable_price(sorted_values)
                        
                        if additional_value is not None and additional_value >= 0:
                            values[opt_name][target_value] = additional_value

        return values

    def _round_combat_stat(self, value: float) -> int:
        """전투 특성 반올림 (10 단위)"""
        return round(value / 10) * 10

    def _round_base_stat(self, value: float) -> int:
        """기본 특성 반올림 (1000 단위)"""
        return round(value / 1000) * 1000

    def _classify_bracelet_pattern(self, combat_stats: List[BraceletCombatStat], 
                                 base_stats: List[BraceletBaseStat]) -> str:
        """팔찌 패턴 분류"""
        combat_values = []
        for stat in combat_stats:
            stat_value = float(stat.value) if stat.value else 0.0
            if stat_value >= 50:
                combat_values.append(self._round_combat_stat(stat_value))
        
        base_values = []
        for stat in base_stats:
            stat_value = float(stat.value) if stat.value else 0.0
            if stat_value >= 3000:
                base_values.append(self._round_base_stat(stat_value))
        
        high_combat_count = len([v for v in combat_values if v >= 80])
        high_base_count = len([v for v in base_values if v >= 10000])
        
        if high_combat_count >= 2:
            return "전특2"
        elif high_combat_count == 1:
            if high_base_count >= 1:
                return "전특1+기본"
            elif any(v >= 70 for v in combat_values if v < 80):
                return "전특1+공이속"
            else:
                return "전특1+잡옵"
        elif high_base_count >= 2:
            return "기본+공이속"
        else:
            return "전특1"

    def _calculate_bracelet_prices(self, grade: str) -> Dict:
        """팔찌 가격 계산"""
        with self.main_db.get_read_session() as session:
            bracelets = session.query(AuctionBracelet).filter(
                AuctionBracelet.grade == grade,
                AuctionBracelet.price.is_not(None),
                AuctionBracelet.price > 0
            ).all()

        pattern_data = {}
        
        for bracelet in bracelets:
            # 패턴 분류
            pattern_type = self._classify_bracelet_pattern(
                bracelet.combat_stats, 
                bracelet.base_stats
            )
            
            # 패턴 키 생성 (반올림된 스탯 값들 사용)
            combat_values = []
            for stat in bracelet.combat_stats:
                stat_value = float(stat.value) if stat.value else 0.0
                if stat_value >= 50:
                    combat_values.append(self._round_combat_stat(stat_value))
            combat_values = tuple(sorted(combat_values, reverse=True))
            
            base_values = []
            for stat in bracelet.base_stats:
                stat_value = float(stat.value) if stat.value else 0.0
                if stat_value >= 3000:
                    base_values.append(self._round_base_stat(stat_value))
            base_values = tuple(sorted(base_values, reverse=True))
            
            pattern_key = (combat_values, base_values, bracelet.extra_option_count)
            
            if pattern_type not in pattern_data:
                pattern_data[pattern_type] = {}
            
            if pattern_key not in pattern_data[pattern_type]:
                pattern_data[pattern_type][pattern_key] = (bracelet.price, 1)
            else:
                old_price, old_count = pattern_data[pattern_type][pattern_key]
                new_price = (old_price * old_count + bracelet.price) // (old_count + 1)
                pattern_data[pattern_type][pattern_key] = (new_price, old_count + 1)

        return pattern_data

    def _classify_accessory_patterns(self, accessory: AuctionAccessory) -> tuple[List[str], List[str]]:
        """악세서리의 옵션을 분석하여 딜러용/서포터용 옵션을 구분합니다."""
        dealer_options = []
        support_options = []
        
        if accessory.part not in self.EXCLUSIVE_OPTIONS:
            return dealer_options, support_options
        
        part_options = self.EXCLUSIVE_OPTIONS[accessory.part]
        
        for option in accessory.raw_options:
            option_name = option.option_name
            
            # 딜러용 옵션 확인
            if "dealer" in part_options and option_name in part_options["dealer"]:
                dealer_options.append(option_name)
            
            # 서포터용 옵션 확인
            if "support" in part_options and option_name in part_options["support"]:
                support_options.append(option_name)
        
        return dealer_options, support_options