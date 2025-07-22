"""
패턴 생성 전용 클래스 - DB에 패턴 데이터 저장만 담당
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
import numpy as np
from scipy.optimize import nnls
import os
from contextlib import contextmanager

from src.database.raw_database import (
    RawDatabaseManager, AuctionAccessory, AuctionBracelet, 
    AuctionStatus, 
    BraceletCombatStat, BraceletBaseStat
)
from src.database.pattern_database import (
    PatternDatabaseManager, AuctionPricePattern, 
    AccessoryPricePattern, BraceletPricePattern
)
from src.common.config import config
from src.common.utils import calculate_base_stat_ratio, calculate_reasonable_price, extract_common_option_features

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

        # 레거시 설정들 (config로 이동됨)
        self.MIN_SAMPLES = config.pattern_generator_settings["min_regression_samples"]
        self.SOLD_ITEMS_WINDOW = timedelta(days=7)  # SOLD 상태 아이템 조회 기간  
        self.SOLD_PRICE_WEIGHT = 0.95  # SOLD 상태 아이템 가격 가중치
        
        # Config에서 설정 가져오기
        self.EXCLUSIVE_OPTIONS = config.exclusive_options
        self.COMMON_OPTIONS = config.common_options

    def update_pattern(self, pattern_datetime: Optional[datetime] = None, send_signal: bool = True) -> bool:
        """
        현재 시각 기준으로 시장 가격 데이터로 캐시 업데이트
        
        Args:
            pattern_datetime: 패턴 생성 기준 시각 (None이면 현재 시각 사용)
            send_signal: IPC 신호 발송 여부 (기본값: True)
            
        Returns:
            bool: 캐시 업데이트 성공 여부
        """
        try:
            # pattern_datetime이 None인 경우 현재 시각 사용
            if pattern_datetime is None:
                pattern_datetime = datetime.now()
                print(f"Using current time for pattern generation: {pattern_datetime.isoformat()}")
            
            # 오래된 로그파일 정리 (3일 이상)
            cleanup_old_logs('pattern_log', days=3)
            
            # 로그 파일 설정
            print(f"\nUpdating pattern at {pattern_datetime.isoformat()}")
            log_filename = f'pattern_log/pattern_calculation_{pattern_datetime.isoformat().replace(":", "-")}.log'

            with redirect_stdout(log_filename):
                new_pattern = {
                    "dealer": {},
                    "support": {},
                    "bracelet": {}
                }
                
                # 1. 악세서리 읽기 및 패턴 만들기
                start_time = datetime.now()
                print(f"Starting accessory pattern generation...")
                
                dealer_patterns, support_patterns = self._calculate_accessory_prices(pattern_datetime)
                new_pattern["dealer"] = dealer_patterns
                new_pattern["support"] = support_patterns
                
                accessory_duration = (datetime.now() - start_time).total_seconds()
                print(f"Calculating acc patterns duration: {accessory_duration:.1f}s")

                # 2. 팔찌 읽기 및 패턴 만들기
                start_time = datetime.now()
                print(f"Starting bracelet pattern generation...")
                
                bracelet_patterns = self._calculate_bracelet_prices(pattern_datetime)
                new_pattern["bracelet"] = bracelet_patterns

                bracelet_duration = (datetime.now() - start_time).total_seconds()
                print(f"Calculating bracelet patterns duration: {bracelet_duration:.1f}s")
                total_bracelet_patterns = len(bracelet_patterns)
                print(f"Generated {total_bracelet_patterns} total bracelet patterns")

                # 3. pattern DB에 한 번에 쓰기
                start_time = datetime.now()
                print(f"Writing all patterns to database...")
                
                with self.pattern_db.get_write_session() as write_session:
                    # 기존 활성 패턴 확인
                    latest_cycle = write_session.query(AuctionPricePattern)\
                        .order_by(AuctionPricePattern.pattern_datetime.desc())\
                        .first()
                    
                    # 테이블이 비어있거나, 현재 패턴이 더 최신인 경우 True
                    is_latest = latest_cycle is None or latest_cycle.pattern_datetime <= pattern_datetime
                    
                    print(f"Latest pattern datetime: {latest_cycle.pattern_datetime if latest_cycle else 'None'}")
                    print(f"Current pattern datetime: {pattern_datetime.isoformat()}")
                    print(f"Is latest: {is_latest}")

                    # 새 패턴 메타데이터 생성
                    new_pattern_entry = AuctionPricePattern(
                        pattern_datetime=pattern_datetime,
                        is_active=is_latest
                    )

                    if is_latest: # type: ignore
                        # 기존 활성 패턴 비활성화
                        write_session.query(AuctionPricePattern).filter_by(is_active=True).update(
                            {"is_active": False}
                        )

                    write_session.add(new_pattern_entry)

                    # 악세서리 패턴 저장
                    for role in ['dealer', 'support']:
                        for cache_key, pattern_data in new_pattern[role].items():
                            grade, part, level, pattern_key = cache_key.split(':', 3)

                            acc_pattern = AccessoryPricePattern(
                                pattern_datetime=pattern_datetime,
                                grade=grade,
                                part=part,
                                level=int(level),
                                pattern_key=pattern_key,
                                role=role,
                                # Multilinear regression 데이터
                                intercept=pattern_data['intercept'],
                                coefficients=pattern_data['coefficients'],
                                feature_names=pattern_data['feature_names'],
                                total_sample_count=pattern_data['total_sample_count']
                            )
                            write_session.add(acc_pattern)

                    # 팔찌 패턴 저장
                    for cache_key, pattern_data in new_pattern["bracelet"].items():
                        # cache_key 예시: "고대:(('신속', 80), ('치명', 90)):2"
                        parts = cache_key.split(':', 2)
                        grade = parts[0]
                        sorted_stats = parts[1]  # 모든 스탯 정보
                        extra_slots = parts[2]

                        bracelet_pattern = BraceletPricePattern(
                            pattern_datetime=pattern_datetime,
                            grade=grade,
                            sorted_stats=sorted_stats,
                            extra_slots=extra_slots,
                            price=pattern_data['price'],
                            total_sample_count=pattern_data['total_sample_count']
                        )
                        write_session.add(bracelet_pattern)

                write_duration = (datetime.now() - start_time).total_seconds()
                print(f"Writing patterns duration: {write_duration:.1f}s")

            completion_time = datetime.now()
            total_duration = (completion_time - start_time).total_seconds()
            print(f"Pattern generation completed at {completion_time.isoformat()}")
            print(f"Total pattern generation duration: {total_duration:.1f}s")
            print(f"Pattern collection created for datetime: {pattern_datetime.isoformat()}")
            
            # 패턴 업데이트 완료 신호 발송 (옵션)
            if send_signal:
                self._send_pattern_update_signal(pattern_datetime, completion_time)
            
            return True

        except Exception as e:
            print(f"Error updating price patterns: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _calculate_accessory_prices(self, pattern_datetime: datetime) -> tuple[Dict, Dict]:
        """악세서리 패턴별 가격 계산"""
        with self.main_db.get_read_session() as read_session:
            active_accessories = (
                read_session.query(AuctionAccessory)
                .filter(
                    (AuctionAccessory.status == AuctionStatus.ACTIVE)
                    | (
                        (AuctionAccessory.status == AuctionStatus.SOLD)
                        & (
                            AuctionAccessory.sold_at
                            >= pattern_datetime - timedelta(days=7)
                        )
                    )
                )
                .all()
            )

            print(f"Found {len(active_accessories)} accessory records for pattern generation")

            # 딜러용/서포터용 데이터 그룹화
            dealer_groups = {}
            support_groups = {}

            for accessory in active_accessories:
                dealer_key, support_key = self._classify_accessory_patterns(accessory)

                # 딜러용 그룹 추가
                if dealer_key not in dealer_groups:
                    dealer_groups[dealer_key] = []
                dealer_groups[dealer_key].append(accessory)

                # 서포터용 그룹 추가
                if support_key not in support_groups:
                    support_groups[support_key] = []
                support_groups[support_key].append(accessory)

            # 각 그룹별로 가격 계산
            dealer_patterns = {}
            for key, items in dealer_groups.items():
                price_data = self._calculate_accessory_group_prices(items, key, "dealer")
                if price_data:
                    dealer_patterns[key] = price_data

            support_patterns = {}
            for key, items in support_groups.items():
                price_data = self._calculate_accessory_group_prices(items, key, "support")
                if price_data:
                    support_patterns[key] = price_data

        return dealer_patterns, support_patterns

    def _calculate_bracelet_prices(self, pattern_datetime: datetime) -> Dict:
        """팔찌 패턴별 가격 계산"""
        with self.main_db.get_read_session() as session:
            bracelets = (
                session.query(AuctionBracelet)
                .filter(
                    (AuctionBracelet.status == AuctionStatus.ACTIVE)
                    | (
                        (AuctionBracelet.status == AuctionStatus.SOLD)
                        & (
                            AuctionBracelet.sold_at
                            >= pattern_datetime - timedelta(days=7)
                        )
                    )
                )
                .all()
            )

            print(f"Found {len(bracelets)} bracelet records for pattern generation")

            # 팔찌 그룹화
            bracelet_groups = {}

            for bracelet in bracelets:
                cache_key = self._classify_bracelet_patterns(bracelet)

                # 그룹 추가
                if cache_key not in bracelet_groups:
                    bracelet_groups[cache_key] = []
                bracelet_groups[cache_key].append(bracelet)

            # 각 그룹별로 가격 계산
            result = {}
            for key, items in bracelet_groups.items():
                price_data = self._calculate_bracelet_group_prices(items, key)
                if price_data:
                    result[key] = price_data

            print(f"Generated {len(result)} total bracelet patterns")

        return result

    def _classify_accessory_patterns(self, accessory: AuctionAccessory) -> tuple[str, str]:
        """악세서리의 옵션을 분석하여 딜러용/서포터용 cache_key를 생성"""
        dealer_options = []
        support_options = []
        
        if accessory.part not in self.EXCLUSIVE_OPTIONS:
            # 기본 키 생성
            base_key = f"{accessory.grade}:{accessory.part}:{accessory.level}:base"
            return base_key, base_key
        
        part_options = self.EXCLUSIVE_OPTIONS[accessory.part] # type: ignore
        
        for option in accessory.raw_options:
            option_name = option.option_name
            option_value = option.option_value
            
            # 딜러용 옵션 확인
            if "dealer" in part_options and option_name in part_options["dealer"]:
                dealer_options.append((option_name, option_value))
            
            # 서포터용 옵션 확인
            if "support" in part_options and option_name in part_options["support"]:
                support_options.append((option_name, option_value))
        
        # 키 생성
        dealer_key = f"{accessory.grade}:{accessory.part}:{accessory.level}:{sorted(dealer_options)}" if dealer_options else f"{accessory.grade}:{accessory.part}:{accessory.level}:base"
        support_key = f"{accessory.grade}:{accessory.part}:{accessory.level}:{sorted(support_options)}" if support_options else f"{accessory.grade}:{accessory.part}:{accessory.level}:base"
        
        return dealer_key, support_key

    def _classify_bracelet_patterns(self, bracelet: AuctionBracelet) -> str:
        """팔찌 패턴 분류 및 cache_key 생성 (새로운 분류 체계)"""
        
        # 유효 스탯들 정의
        valid_combat_stats = ["치명", "특화", "신속"]
        jeinsuk_stats = ["제압", "인내", "숙련"]
        valid_base_stats = ["힘", "민첩", "지능"]
        
        # 전투 특성 분류
        valid_combat = []  # 유효한 전투 특성
        jeinsuk_combat = []  # 제압/인내/숙련
        invalid_combat = []  # 잡옵
        
        for stat in bracelet.combat_stats:
            stat_value = float(stat.value) if stat.value is not None else 0.0
            if stat_value > 0:  # 값이 있는 것만 고려
                if stat.stat_type in valid_combat_stats:
                    valid_combat.append((stat.stat_type, stat_value))
                elif stat.stat_type in jeinsuk_stats:
                    jeinsuk_combat.append((stat.stat_type, stat_value))
                else:
                    invalid_combat.append((stat.stat_type, stat_value))
        
        # 기본 스탯 분류
        valid_base = []
        for stat in bracelet.base_stats:
            stat_value = float(stat.value) if stat.value is not None else 0.0
            if stat_value > 0 and stat.stat_type in valid_base_stats:
                valid_base.append((stat.stat_type, stat_value))
        
        # 공격속도 효과 확인 및 값 추출
        speed_value = 0
        if bracelet.special_effects:
            for effect in bracelet.special_effects:
                if "공격 및 이동 속도 증가" in str(effect.effect_type):
                    # 공격속도 값이 있다면 사용, 없으면 1
                    if hasattr(effect, 'value') and effect.value:
                        speed_value = float(effect.value)
                    else:
                        speed_value = 1
                    break
        
        # 정렬된 스탯 리스트 생성 (키 유일성 확보)
        all_stats = []
        
        # 유효한 전투 특성 추가 (반올림 적용)
        for stat_name, stat_value in valid_combat:
            rounded_value = self._round_combat_stat(bracelet.grade, stat_value)
            all_stats.append((stat_name, rounded_value))
        
        # 유효한 기본 특성 추가 (반올림 적용)
        for stat_name, stat_value in valid_base:
            rounded_value = self._round_base_stat(bracelet.grade, stat_value)
            all_stats.append((stat_name, rounded_value))
        
        # 공격속도 추가 (실제 값 사용)
        if speed_value > 0:
            all_stats.append(("공이속", int(speed_value)))
        
        # 제인숙 스탯 추가 (모두 "제인숙"으로 통합, 값은 0)
        for stat_name, _ in jeinsuk_combat:
            all_stats.append(("제인숙", 0))
        
        # 잡옵 스탯 추가 (값은 0으로 통일)
        for stat_name, _ in invalid_combat:
            all_stats.append(("잡옵", 0))
        
        # 정렬: 스탯명 기준으로 정렬 (값이 동일할 때 일관성 확보)
        sorted_stats = tuple(sorted(all_stats, key=lambda x: (x[0], x[1])))
        
        # cache_key 생성: "grade:sorted_stats:extra_slots"
        cache_key = f"{bracelet.grade}:{sorted_stats}:{bracelet.extra_option_count}"
        
        return cache_key

    def _calculate_accessory_group_prices(self, items: List[AuctionAccessory], exclusive_key: str, role: str) -> Optional[Dict]:
        """그룹의 가격 통계 계산 - Multilinear Regression 모델"""
        if not items:
            return None
        
        _, part, _, *_ = exclusive_key.split(':')
        
        print(f"\n=== Calculating Multilinear Regression for {exclusive_key} ({role}) ===")
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

        # 역할별 관련 옵션 가져오기 (피처 순서 정의)
        feature_names = config.role_related_options[role]
        print(f"Feature names for {role}: {feature_names}")

        # 피처 벡터와 타겟 가격 데이터 수집
        X = []  # 피처 매트릭스
        y = []  # 타겟 가격 벡터
        
        for item in filtered_items:
            if item.price and item.status in [AuctionStatus.ACTIVE, AuctionStatus.SOLD]:
                # 피처 벡터 추출
                features = extract_common_option_features(item, role, config)
                
                # feature_names 순서대로 피처 벡터 생성
                feature_vector = []
                for feature_name in feature_names:
                    feature_vector.append(features.get(feature_name, 0.0))
                
                X.append(feature_vector)
                y.append(float(item.price))
        
        min_samples = config.pattern_generator_settings["min_regression_samples"]
        if len(X) < min_samples:
            print(f"Multilinear regression: 데이터 부족 ({len(X)}개)")
            return None
        
        # Multilinear regression using numpy
        X_array = np.array(X)
        y_array = np.array(y)
        
        print(f"Feature matrix shape: {X_array.shape}")
        print(f"Target vector shape: {y_array.shape}")
        
        # 상수항을 위한 1의 열 추가
        X_with_intercept = np.column_stack([np.ones(X_array.shape[0]), X_array])
        
        # Non-negative Least Squares (NNLS) 사용
        try:
            # NNLS: 모든 계수가 0 이상이 되도록 제약하면서 최소자승법 수행
            coefficients_nnls, residual = nnls(X_with_intercept, y_array)
            
            intercept = float(coefficients_nnls[0])
            coefficients = coefficients_nnls[1:].tolist()
            
            # 계수를 딕셔너리로 변환
            coeff_dict = {}
            for i, feature_name in enumerate(feature_names):
                coeff_dict[feature_name] = float(coefficients[i])
            
            print(f"Non-negative Least Squares (NNLS) results:")
            print(f"  Intercept: {intercept:.2f}")
            for feature_name, coeff in coeff_dict.items():
                print(f"  {feature_name}: {coeff:.2f}")
            print(f"  Samples: {len(X)}")
            
            # 모델 성능 평가 (R-squared)
            y_pred = X_with_intercept @ coefficients_nnls
            ss_tot = np.sum((y_array - np.mean(y_array)) ** 2)
            ss_res = np.sum((y_array - y_pred) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            print(f"  R-squared: {r_squared:.4f}")
            print(f"  Residual: {residual:.2f}")
            
            return {
                'intercept': intercept,
                'coefficients': coeff_dict,
                'feature_names': feature_names,
                'total_sample_count': len(items),
                'r_squared': r_squared
            }
            
        except Exception as e:
            print(f"Non-negative Least Squares failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_common_option_values(self, items: List[AuctionAccessory], role: str, base_price: int, slope: float) -> Dict: 
        """
        레거시 메서드 - multilinear regression에서는 사용하지 않음
        
        각 Common 옵션 값의 추가 가치를 계산 (Linear regression 모델 기반)
        이 메서드는 기존 방식과의 호환성을 위해 보존됨
        """
        print("Warning: _calculate_common_option_values is deprecated in multilinear regression mode")
        return {}

    def _calculate_bracelet_group_prices(self, items: List[AuctionBracelet], cache_key: str) -> Optional[Dict]:
        """팔찌 그룹의 가격 통계 계산"""
        if not items:
            return None
        
        print(f"\n=== Calculating Bracelet Group Prices for {cache_key} ===")
        print(f"Total items in group: {len(items)}")
        
        # 가격 필터링 (0보다 큰 가격만)
        valid_items = [item for item in items if item.price is not None and item.price > 0]
        
        if not valid_items:
            print("No valid items with price > 0")
            return None
        
        # 가격 정렬 및 계산
        prices = sorted([int(item.price) for item in valid_items])
        reasonable_price = calculate_reasonable_price(prices)
        
        if reasonable_price and reasonable_price > 0:
            return {
                'price': reasonable_price,
                'total_sample_count': len(valid_items)
            }
        
        return None

    def _send_pattern_update_signal(self, pattern_datetime: datetime, completion_time: datetime = None):
        """패턴 업데이트 완료 신호를 item_evaluator에 발송"""
        try:
            from src.common.ipc_utils import notify_pattern_update
            result = notify_pattern_update(pattern_datetime)
            
            if completion_time:
                time_display = completion_time.isoformat()
            else:
                time_display = pattern_datetime.isoformat()
            
            if result:
                print(f"📡 Pattern update signal sent via IPC at {time_display}")
            else:
                print(f"📡 Pattern update signal sent (no active listeners) at {time_display}")
        except Exception as e:
            print(f"Warning: Failed to send pattern update signal: {e}")

    def _round_combat_stat(self, grade: str, value: float) -> int:
        """전투 특성 값을 기준값으로 내림"""
        thresholds = [40, 50, 60, 70, 80, 90]
        combat_stat_bonus = 20 if grade == "고대" else 0
        adjusted_thresholds = [t + combat_stat_bonus for t in thresholds]

        # 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]

    def _round_base_stat(self, grade: str, value: float) -> int:
        """기본스탯 값을 기준값으로 내림"""
        thresholds = [6400, 8000, 9600, 11200]
        base_stat_bonus = 3200 if grade == "고대" else 0
        adjusted_thresholds = [t + base_stat_bonus for t in thresholds]

        # 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]
    
    def run_service(self):
        """IPC 서비스 모드로 실행 (무한 대기)"""
        import time
        import signal
        from src.common.ipc_utils import IPCServer, MessageTypes
        
        print("Starting Pattern Generator Service...")
        
        # IPC 서버 설정
        ipc_server = IPCServer()
        
        def handle_collection_completed(message):
            """데이터 수집 완료 신호 처리"""
            try:
                completion_time_str = message['data']['completion_datetime']
                completion_time = datetime.fromisoformat(completion_time_str)
                
                print(f"Received collection completion signal: {completion_time.isoformat()}")
                
                # 패턴 생성 실행
                success = self.update_pattern(
                    pattern_datetime=completion_time,
                    send_signal=True
                )
                
                if success:
                    print(f"Pattern generation completed successfully")
                    return {'status': 'success', 'message': 'Pattern generated'}
                else:
                    print(f"Pattern generation failed")
                    return {'status': 'error', 'message': 'Pattern generation failed'}
                    
            except Exception as e:
                print(f"Error handling collection completion: {e}")
                import traceback
                traceback.print_exc()
                return {'status': 'error', 'message': str(e)}
        
        def handle_health_check(message):
            """헬스체크 처리"""
            return {
                'status': 'healthy',
                'service': 'pattern_generator',
                'timestamp': datetime.now().isoformat()
            }
        
        # 핸들러 등록
        ipc_server.register_handler(MessageTypes.COLLECTION_COMPLETED, handle_collection_completed)
        ipc_server.register_handler(MessageTypes.HEALTH_CHECK, handle_health_check)
        
        # 종료 신호 핸들러
        is_running = [True]  # 리스트로 감싸서 nonlocal 문제 해결
        
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}")
            is_running[0] = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # IPC 서버 시작
        try:
            ipc_server.start_server()
            print("IPC server started")
            print("Pattern Generator Service is ready!")
            print("Waiting for collection completion signals...")
            
            # 메인 루프
            while is_running[0]:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nReceived interrupt signal")
        finally:
            print("Stopping Pattern Generator Service...")
            ipc_server.stop_server()
            print("Service stopped")


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='로스트아크 패턴 생성기')
    parser.add_argument('--datetime', type=str, 
                       help='패턴 생성 기준 시각 (ISO format, 기본값: 현재 시각)')
    parser.add_argument('--service', action='store_true',
                       help='IPC 서비스 모드로 실행 (무한 대기)')
    args = parser.parse_args()
    
    # DB 매니저 초기화
    from src.database.raw_database import RawDatabaseManager
    db_manager = RawDatabaseManager()
    generator = PatternGenerator(db_manager)
    
    if args.service:
        # 서비스 모드
        print("=== Pattern Generator Service Mode ===")
        generator.run_service()
    else:
        # 일회성 실행 모드
        print("=== Pattern Generation Only Mode ===")
        start_time = datetime.now()
        
        # 기준 시각 설정
        if args.datetime:
            try:
                pattern_datetime = datetime.fromisoformat(args.datetime)
                print(f"Using specified datetime: {pattern_datetime.isoformat()}")
            except ValueError:
                print(f"Invalid datetime format: {args.datetime}")
                print("Using current time instead")
                pattern_datetime = None
        else:
            pattern_datetime = None
        
        # 패턴 생성 실행
        success = generator.update_pattern(pattern_datetime)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if success:
            print(f"Pattern generation completed! Duration: {duration:.1f}s")
        else:
            print(f"Pattern generation failed! Duration: {duration:.1f}s")


if __name__ == "__main__":
    main()