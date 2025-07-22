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
from src.common.utils import (
    normalize_base_stat_value, calculate_reasonable_price, extract_common_option_features,
    create_accessory_pattern_key, create_bracelet_pattern_key
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
        self.is_generating = False  # 패턴 생성 중 플래그
        
        # 15분 간격 스케줄링을 위한 변수들
        self.collection_signal_received = False  # 데이터 수집 완료 신호 플래그
        self.last_collection_time = None         # 마지막 데이터 수집 시간
       
        # Config에서 설정 가져오기
        self.EXCLUSIVE_OPTIONS = config.exclusive_options

    def update_pattern(self, pattern_datetime: Optional[datetime] = None, send_signal: bool = True) -> bool:
        """
        현재 시각 기준으로 시장 가격 데이터로 캐시 업데이트
        
        Args:
            pattern_datetime: 패턴 생성 기준 시각 (None이면 현재 시각 사용)
            send_signal: IPC 신호 발송 여부 (기본값: True)
            
        Returns:
            bool: 캐시 업데이트 성공 여부
        """
        # 중복 실행 방지
        if self.is_generating:
            print(f"Pattern generation already in progress, skipping...")
            return False
            
        self.is_generating = True
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
                                # 공통 필드
                                model_type=pattern_data['model_type'],
                                base_price=pattern_data['base_price'],
                                total_sample_count=pattern_data['total_sample_count'],
                                r_squared=pattern_data.get('r_squared'),
                                success_rate=pattern_data.get('success_rate'),
                                sold_count=pattern_data.get('sold_count'),
                                expired_count=pattern_data.get('expired_count'),
                                # Multilinear regression 데이터 (필요시에만)
                                intercept=pattern_data.get('intercept'),
                                coefficients=pattern_data.get('coefficients'),
                                feature_names=pattern_data.get('feature_names')
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
                            total_sample_count=pattern_data['total_sample_count'],
                            success_rate=pattern_data.get('success_rate'),
                            sold_count=pattern_data.get('sold_count'),
                            expired_count=pattern_data.get('expired_count')
                        )
                        write_session.add(bracelet_pattern)

                write_duration = (datetime.now() - start_time).total_seconds()
                print(f"Writing patterns duration: {write_duration:.1f}s")

            completion_time = datetime.now()
            total_duration = (completion_time - pattern_datetime).total_seconds()
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
        finally:
            self.is_generating = False

    def _calculate_accessory_prices(self, pattern_datetime: datetime) -> tuple[Dict, Dict]:
        """악세서리 패턴별 가격 계산"""
        with self.main_db.get_read_session() as read_session:
            # 패턴 생성용: ACTIVE + 7일 이내 SOLD
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
            
            # 판매 성공률 계산용: 최근 30일 이내 SOLD + EXPIRED
            success_rate_window_days = config.pattern_generator_settings.get("success_rate_window_days", 30)
            historical_accessories = (
                read_session.query(AuctionAccessory)
                .filter(
                    (
                        (AuctionAccessory.status == AuctionStatus.SOLD)
                        & (
                            AuctionAccessory.sold_at
                            >= pattern_datetime - timedelta(days=success_rate_window_days)
                        )
                    )
                    | (
                        (AuctionAccessory.status == AuctionStatus.EXPIRED)
                        & (
                            AuctionAccessory.last_seen_at
                            >= pattern_datetime - timedelta(days=success_rate_window_days)
                        )
                    )
                )
                .all()
            )

            print(f"Found {len(active_accessories)} accessory records for pattern generation")

            # 딜러용/서포터용 데이터 그룹화 (가격 계산용)
            dealer_groups = {}
            support_groups = {}

            for accessory in active_accessories:
                dealer_key = create_accessory_pattern_key(accessory, "dealer")
                support_key = create_accessory_pattern_key(accessory, "support")

                # 딜러용 그룹 추가
                if dealer_key not in dealer_groups:
                    dealer_groups[dealer_key] = []
                dealer_groups[dealer_key].append(accessory)

                # 서포터용 그룹 추가
                if support_key not in support_groups:
                    support_groups[support_key] = []
                support_groups[support_key].append(accessory)

            # 판매 성공률 계산용 그룹화
            dealer_historical_groups = {}
            support_historical_groups = {}

            for accessory in historical_accessories:
                dealer_key = create_accessory_pattern_key(accessory, "dealer")
                support_key = create_accessory_pattern_key(accessory, "support")

                # 딜러용 그룹 추가
                if dealer_key not in dealer_historical_groups:
                    dealer_historical_groups[dealer_key] = []
                dealer_historical_groups[dealer_key].append(accessory)

                # 서포터용 그룹 추가
                if support_key not in support_historical_groups:
                    support_historical_groups[support_key] = []
                support_historical_groups[support_key].append(accessory)

            # 각 그룹별로 가격 계산 (판매 성공률 포함)
            dealer_patterns = {}
            for key, items in dealer_groups.items():
                historical_items = dealer_historical_groups.get(key, [])
                price_data = self._calculate_accessory_group_prices(items, key, "dealer", historical_items)
                if price_data:
                    dealer_patterns[key] = price_data

            support_patterns = {}
            for key, items in support_groups.items():
                historical_items = support_historical_groups.get(key, [])
                price_data = self._calculate_accessory_group_prices(items, key, "support", historical_items)
                if price_data:
                    support_patterns[key] = price_data

        return dealer_patterns, support_patterns

    def _calculate_bracelet_prices(self, pattern_datetime: datetime) -> Dict:
        """팔찌 패턴별 가격 계산"""
        with self.main_db.get_read_session() as session:
            # 패턴 생성용: ACTIVE + 7일 이내 SOLD
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
            
            # 판매 성공률 계산용: 최근 30일 이내 SOLD + EXPIRED
            success_rate_window_days = config.pattern_generator_settings.get("success_rate_window_days", 30)
            historical_bracelets = (
                session.query(AuctionBracelet)
                .filter(
                    (
                        (AuctionBracelet.status == AuctionStatus.SOLD)
                        & (
                            AuctionBracelet.sold_at
                            >= pattern_datetime - timedelta(days=success_rate_window_days)
                        )
                    )
                    | (
                        (AuctionBracelet.status == AuctionStatus.EXPIRED)
                        & (
                            AuctionBracelet.last_seen_at
                            >= pattern_datetime - timedelta(days=success_rate_window_days)
                        )
                    )
                )
                .all()
            )

            print(f"Found {len(bracelets)} bracelet records for pattern generation")

            # 팔찌 그룹화 (가격 계산용)
            bracelet_groups = {}
            for bracelet in bracelets:
                cache_key = create_bracelet_pattern_key(bracelet)
                if cache_key not in bracelet_groups:
                    bracelet_groups[cache_key] = []
                bracelet_groups[cache_key].append(bracelet)

            # 판매 성공률 계산용 그룹화
            bracelet_historical_groups = {}
            for bracelet in historical_bracelets:
                cache_key = create_bracelet_pattern_key(bracelet)
                if cache_key not in bracelet_historical_groups:
                    bracelet_historical_groups[cache_key] = []
                bracelet_historical_groups[cache_key].append(bracelet)

            # 각 그룹별로 가격 계산 (판매 성공률 포함)
            result = {}
            for key, items in bracelet_groups.items():
                historical_items = bracelet_historical_groups.get(key, [])
                price_data = self._calculate_bracelet_group_prices(items, key, historical_items)
                if price_data:
                    result[key] = price_data

            print(f"Generated {len(result)} total bracelet patterns")

        return result

    def _calculate_accessory_group_prices(self, items: List[AuctionAccessory], exclusive_key: str, role: str, historical_items: List[AuctionAccessory] = None) -> Optional[Dict]:
        """그룹의 가격 통계 계산 - Multilinear Regression 모델"""
        if not items:
            return None
        
        _, part, _, *_ = exclusive_key.split(':')
        
        print(f"\n=== Calculating Multilinear Regression for {exclusive_key} ({role}) ===")
        print(f"Total items in group: {len(items)}")
        
        filtered_items = []
        excluded_option_names = set()

        # exclusive_key에서 현재 패턴에 포함된 옵션들 추출
        current_pattern_options = set()
        if ':' in exclusive_key:
            pattern_part = exclusive_key.split(':', 3)[-1]  # "base" 또는 옵션 리스트
            if pattern_part != "base":
                try:
                    # 예: "[('적주피', 1.2), ('추피', 1.6)]" -> {"적주피", "추피"}
                    import ast
                    option_list = ast.literal_eval(pattern_part)
                    if isinstance(option_list, list):
                        current_pattern_options = {opt_name for opt_name, _ in option_list}
                except:
                    pass  # 파싱 실패 시 빈 set 유지
        
        # 다른 역할의 exclusive 옵션들 중 현재 패턴에 포함된 것들은 제외하지 않음
        for group_role in ["dealer", "support"]:
            if group_role != role and part in self.EXCLUSIVE_OPTIONS:
                for exc_opt in self.EXCLUSIVE_OPTIONS[part].get(group_role, []):
                    # 현재 패턴에 포함된 옵션이 아닌 경우만 제외 대상에 추가
                    if exc_opt not in current_pattern_options:
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
        all_feature_names = config.role_related_options[role]
        print(f"Available features for {role}: {all_feature_names}")

        # 피처 벡터와 타겟 가격 데이터 수집
        X_all = []  # 전체 피처 매트릭스
        y = []  # 타겟 가격 벡터
        
        for item in filtered_items:
            if item.price and item.status in [AuctionStatus.ACTIVE, AuctionStatus.SOLD]:
                # 피처 벡터 추출
                features = extract_common_option_features(item, role)
                
                # feature_names 순서대로 피처 벡터 생성
                feature_vector = []
                for feature_name in all_feature_names:
                    feature_vector.append(features.get(feature_name, 0.0))
                
                X_all.append(feature_vector)
                y.append(float(item.price))
        
        min_samples = config.pattern_generator_settings["min_regression_samples"]
        if len(X_all) < min_samples:
            print(f"Multilinear regression: 데이터 부족 ({len(X_all)}개)")
            return None
        
        X_all_array = np.array(X_all)
        y_array = np.array(y)
        
        # 각 피처별로 개별 상관관계 분석
        print(f"Analyzing individual feature correlations:")
        valid_features = []
        valid_feature_indices = []
        min_correlation = config.pattern_generator_settings.get("min_feature_correlation", 0.1)
        
        for i, feature_name in enumerate(all_feature_names):
            # 해당 피처가 0이 아닌 샘플들로 상관관계 계산
            feature_values = X_all_array[:, i]
            non_zero_mask = feature_values > 0
            
            if np.sum(non_zero_mask) < 5:  # 최소 5개 샘플 필요
                print(f"  {feature_name}: Skip (insufficient non-zero samples: {np.sum(non_zero_mask)})")
                continue
            
            # 피어슨 상관계수 계산 (분산 체크 포함)
            feature_subset = feature_values[non_zero_mask]
            price_subset = y_array[non_zero_mask]
            
            # 분산이 0인지 체크 (모든 값이 동일한 경우)
            if np.var(feature_subset) == 0 or np.var(price_subset) == 0:
                print(f"  {feature_name}: Skip (zero variance)")
                continue
            
            correlation = np.corrcoef(feature_subset, price_subset)[0, 1]
            
            if np.isnan(correlation):
                print(f"  {feature_name}: Skip (correlation is NaN)")
                continue
            
            abs_correlation = abs(correlation)
            if abs_correlation >= min_correlation:
                valid_features.append(feature_name)
                valid_feature_indices.append(i)
                print(f"  {feature_name}: Include (correlation: {correlation:.3f})")
            else:
                print(f"  {feature_name}: Skip (low correlation: {correlation:.3f})")
        
        if not valid_features:
            print(f"No valid features found - using minimum price model")
            min_price = int(np.min(y_array))
            return {
                'model_type': 'minimum_price',
                'base_price': min_price,
                'total_sample_count': len(filtered_items),
                'r_squared': 0.0,
                'intercept': None,
                'coefficients': None,
                'feature_names': None
            }
        
        # 유효한 피처만으로 새로운 매트릭스 구성
        X = X_all_array[:, valid_feature_indices]
        feature_names = valid_features
        
        print(f"Selected features: {feature_names}")
        print(f"Final feature matrix shape: {X.shape}")
        print(f"Target vector shape: {y_array.shape}")
        
        # 상수항을 위한 1의 열 추가
        X_with_intercept = np.column_stack([np.ones(X.shape[0]), X])
        
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
            
            # 모델 성능 평가
            y_pred = X_with_intercept @ coefficients_nnls
            ss_tot = np.sum((y_array - np.mean(y_array)) ** 2)
            ss_res = np.sum((y_array - y_pred) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            # 추가 성능 지표 계산
            mae = np.mean(np.abs(y_array - y_pred))  # 평균 절대 오차
            mape = np.mean(np.abs((y_array - y_pred) / y_array)) * 100  # 평균 절대 백분율 오차
            rmse = np.sqrt(np.mean((y_array - y_pred) ** 2))  # RMSE
            
            # 가격 범위 정보
            price_min, price_max = int(np.min(y_array)), int(np.max(y_array))
            price_mean = int(np.mean(y_array))
            
            print(f"  R-squared: {r_squared:.4f}")
            print(f"  MAPE (평균 오차율): {mape:.1f}%")
            print(f"  MAE (평균 오차): {mae:,.0f} gold")
            print(f"  Price range: {price_min:,} ~ {price_max:,} gold (평균: {price_mean:,})")
            
            # 모델 품질 판정
            if mape <= 15:
                quality = "Excellent"
            elif mape <= 25:
                quality = "Good"
            elif mape <= 35:
                quality = "Fair"
            else:
                quality = "Poor"
            print(f"  Model Quality: {quality} (MAPE 기준)")
            
            # 판매 성공률 계산
            success_rate_result = self._calculate_success_rate(historical_items or [])
            if success_rate_result is not None:
                success_rate, sold_count, expired_count = success_rate_result
                print(f"  Success Rate: {success_rate:.1f}% (SOLD: {sold_count}, EXPIRED: {expired_count})")
            
            # R-squared 기반 모델 선택
            min_r_squared = config.pattern_generator_settings.get("min_r_squared_threshold", 0.5)
            
            if r_squared < min_r_squared:
                # R-squared가 낮으면 단순 최저가 모델 사용
                min_price = int(np.min(y_array))
                print(f"  ⚠️  Low R-squared ({r_squared:.3f}) - using minimum price model: {min_price:,} gold")
                
                result = {
                    'model_type': 'minimum_price',
                    'base_price': min_price,
                    'total_sample_count': len(items),
                    'r_squared': r_squared,
                    # multilinear 필드들은 None으로 설정
                    'intercept': None,
                    'coefficients': None,
                    'feature_names': None
                }
                
                # 판매 성공률 및 개수 추가 (있는 경우만)
                if success_rate_result is not None:
                    success_rate, sold_count, expired_count = success_rate_result
                    result['success_rate'] = success_rate
                    result['sold_count'] = sold_count
                    result['expired_count'] = expired_count
                
                return result
            else:
                # R-squared가 충분하면 multilinear regression 모델 사용
                print(f"  ✅ Good R-squared ({r_squared:.3f}) - using multilinear model")
                
                result = {
                    'model_type': 'multilinear',
                    'intercept': intercept,
                    'coefficients': coeff_dict,
                    'feature_names': feature_names,
                    'total_sample_count': len(items),
                    'r_squared': r_squared,
                    # 최저가 정보도 같이 저장
                    'base_price': int(np.min(y_array))
                }
                
                # 판매 성공률 및 개수 추가 (있는 경우만)
                if success_rate_result is not None:
                    success_rate, sold_count, expired_count = success_rate_result
                    result['success_rate'] = success_rate
                    result['sold_count'] = sold_count
                    result['expired_count'] = expired_count
                
                return result
            
        except Exception as e:
            print(f"Non-negative Least Squares failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_bracelet_group_prices(self, items: List[AuctionBracelet], cache_key: str, historical_items: List[AuctionBracelet] = None) -> Optional[Dict]:
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
        
        # 판매 성공률 계산
        success_rate_result = self._calculate_bracelet_success_rate(historical_items or [])
        if success_rate_result is not None:
            success_rate, sold_count, expired_count = success_rate_result
            print(f"  Success Rate: {success_rate:.1f}% (SOLD: {sold_count}, EXPIRED: {expired_count})")
        
        if reasonable_price and reasonable_price > 0:
            result = {
                'price': reasonable_price,
                'total_sample_count': len(valid_items)
            }
            
            # 판매 성공률 및 개수 추가 (있는 경우만)
            if success_rate_result is not None:
                success_rate, sold_count, expired_count = success_rate_result
                result['success_rate'] = success_rate
                result['sold_count'] = sold_count
                result['expired_count'] = expired_count
                
            return result
        
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

    def _calculate_success_rate(self, historical_items: List[AuctionAccessory]) -> Optional[tuple[float, int, int]]:
        """악세서리 판매 성공률 계산: SOLD / (SOLD + EXPIRED)
        
        Returns:
            tuple[float, int, int] | None: (success_rate, sold_count, expired_count) 또는 None
        """
        if not historical_items:
            return None
        
        sold_count = sum(1 for item in historical_items if item.status == AuctionStatus.SOLD)
        expired_count = sum(1 for item in historical_items if item.status == AuctionStatus.EXPIRED)
        total_count = sold_count + expired_count
        
        if total_count == 0:
            return None
        
        success_rate = (sold_count / total_count) * 100
        return success_rate, sold_count, expired_count

    def _calculate_bracelet_success_rate(self, historical_items: List[AuctionBracelet]) -> Optional[tuple[float, int, int]]:
        """팔찌 판매 성공률 계산: SOLD / (SOLD + EXPIRED)
        
        Returns:
            tuple[float, int, int] | None: (success_rate, sold_count, expired_count) 또는 None
        """
        if not historical_items:
            return None
        
        sold_count = sum(1 for item in historical_items if item.status == AuctionStatus.SOLD)
        expired_count = sum(1 for item in historical_items if item.status == AuctionStatus.EXPIRED)
        total_count = sold_count + expired_count
        
        if total_count == 0:
            return None
        
        success_rate = (sold_count / total_count) * 100
        return success_rate, sold_count, expired_count

    def _round_combat_stat(self, grade: str, value: float) -> int:
        """전투 특성 값을 기준값으로 내림"""
        thresholds = config.bracelet_settings["combat_stat_thresholds"]
        combat_stat_bonus = config.bracelet_settings["ancient_combat_stat_bonus"] if grade == "고대" else 0
        adjusted_thresholds = [t + combat_stat_bonus for t in thresholds]

        # 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]

    def _round_base_stat(self, grade: str, value: float) -> int:
        """기본스탯 값을 기준값으로 내림"""
        thresholds = config.bracelet_settings["base_stat_thresholds"]
        base_stat_bonus = config.bracelet_settings["ancient_base_stat_bonus"] if grade == "고대" else 0
        adjusted_thresholds = [t + base_stat_bonus for t in thresholds]

        # 가장 가까운 하위 threshold 반환
        for threshold in adjusted_thresholds:
            if value < threshold:
                return adjusted_thresholds[max(0, adjusted_thresholds.index(threshold) - 1)]
        return adjusted_thresholds[-1]
    
    def _get_next_15min_schedule(self) -> datetime:
        """다음 15분 간격 스케줄 시간 계산 (정각 기준)"""
        now = datetime.now()
        # 현재 시간에서 분을 15분 단위로 올림
        minutes = now.minute
        next_15min = ((minutes // 15) + 1) * 15
        
        if next_15min >= 60:
            # 다음 시간
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            # 같은 시간
            next_time = now.replace(minute=next_15min, second=0, microsecond=0)
        
        return next_time
    
    def _copy_latest_pattern(self, new_pattern_datetime: datetime) -> bool:
        """가장 최근 패턴을 복사해서 새 시간으로 저장"""
        try:
            with self.pattern_db.get_write_session() as session:
                # 가장 최근 활성 패턴 찾기
                latest_pattern = session.query(AuctionPricePattern).filter_by(
                    is_active=True
                ).order_by(AuctionPricePattern.pattern_datetime.desc()).first()
                
                if not latest_pattern:
                    print("No existing pattern to copy")
                    return False
                
                print(f"Copying latest pattern from {latest_pattern.pattern_datetime} to {new_pattern_datetime}")
                
                # 기존 활성 패턴들을 비활성화
                session.query(AuctionPricePattern).filter_by(is_active=True).update({'is_active': False})
                
                # 새 메인 패턴 생성
                new_pattern = AuctionPricePattern(
                    pattern_datetime=new_pattern_datetime,
                    is_active=True
                )
                session.add(new_pattern)
                session.flush()
                
                # 악세서리 패턴들 복사
                accessory_patterns = session.query(AccessoryPricePattern).filter_by(
                    pattern_datetime=latest_pattern.pattern_datetime
                ).all()
                
                for old_pattern in accessory_patterns:
                    new_accessory_pattern = AccessoryPricePattern(
                        pattern_datetime=new_pattern_datetime,
                        grade=old_pattern.grade,
                        part=old_pattern.part,
                        level=old_pattern.level,
                        pattern_key=old_pattern.pattern_key,
                        role=old_pattern.role,
                        model_type=old_pattern.model_type,
                        base_price=old_pattern.base_price,
                        total_sample_count=old_pattern.total_sample_count,
                        r_squared=old_pattern.r_squared,
                        success_rate=old_pattern.success_rate,
                        sold_count=old_pattern.sold_count,
                        expired_count=old_pattern.expired_count,
                        intercept=old_pattern.intercept,
                        coefficients=old_pattern.coefficients,
                        feature_names=old_pattern.feature_names
                    )
                    session.add(new_accessory_pattern)
                
                # 팔찌 패턴들 복사
                bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                    pattern_datetime=latest_pattern.pattern_datetime
                ).all()
                
                for old_pattern in bracelet_patterns:
                    new_bracelet_pattern = BraceletPricePattern(
                        pattern_datetime=new_pattern_datetime,
                        grade=old_pattern.grade,
                        sorted_stats=old_pattern.sorted_stats,
                        extra_slots=old_pattern.extra_slots,
                        price=old_pattern.price,
                        total_sample_count=old_pattern.total_sample_count,
                        success_rate=old_pattern.success_rate,
                        sold_count=old_pattern.sold_count,
                        expired_count=old_pattern.expired_count
                    )
                    session.add(new_bracelet_pattern)
                
                session.commit()
                print(f"Pattern copied successfully: {len(accessory_patterns)} accessory + {len(bracelet_patterns)} bracelet patterns")
                return True
                
        except Exception as e:
            print(f"Error copying latest pattern: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _scheduled_pattern_update(self):
        """15분 간격 스케줄에 따른 패턴 업데이트"""
        try:
            update_time = datetime.now()
            
            if self.collection_signal_received and self.last_collection_time:
                print(f"[{update_time.strftime('%H:%M')}] Collection signal detected, running full pattern generation...")
                
                # 실제 패턴 생성
                success = self.update_pattern(send_signal=True)
                
                if success:
                    print(f"Pattern generation completed successfully")
                else:
                    print(f"Pattern generation failed")
                
                # 플래그 리셋
                self.collection_signal_received = False
                self.last_collection_time = None
                
            else:
                print(f"[{update_time.strftime('%H:%M')}] No collection signal, copying latest pattern...")
                
                # 최근 패턴 복사
                success = self._copy_latest_pattern(update_time)
                
                if success:
                    # 패턴 업데이트 신호 발송
                    self._send_pattern_update_signal(update_time, update_time)
                    print(f"Latest pattern copied successfully")
                else:
                    print(f"Failed to copy latest pattern")
                    
        except Exception as e:
            print(f"Error in scheduled pattern update: {e}")
            import traceback
            traceback.print_exc()
    
    def run_service(self):
        """IPC 서비스 모드로 실행 (무한 대기)"""
        import time
        import signal
        from src.common.ipc_utils import IPCServer, MessageTypes
        
        print("Starting Pattern Generator Service...")
        
        # IPC 서버 설정
        ipc_server = IPCServer(service_name="pattern_generator")
        
        def handle_collection_completed(message):
            """데이터 수집 완료 신호 처리 - 15분 스케줄링 방식"""
            try:
                completion_time_str = message['data']['completion_datetime']
                completion_time = datetime.fromisoformat(completion_time_str)
                
                print(f"Received collection completion signal: {completion_time.isoformat()}")
                print("Signal queued for next scheduled update (every 15 minutes)")
                
                # 플래그 설정 (즉시 실행하지 않음)
                self.collection_signal_received = True
                self.last_collection_time = completion_time
                
                # 다음 스케줄 시간 출력
                next_schedule = self._get_next_15min_schedule()
                print(f"Next scheduled update: {next_schedule.strftime('%H:%M')}")
                
                return {
                    'status': 'queued', 
                    'message': 'Collection signal queued for next scheduled update',
                    'next_schedule': next_schedule.isoformat()
                }
                    
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
            print("15-minute scheduled pattern updates enabled")
            
            # 다음 스케줄 시간 계산
            next_schedule_time = self._get_next_15min_schedule()
            print(f"Next scheduled update: {next_schedule_time.strftime('%H:%M')}")
            
            # 메인 루프 - 15분 간격 스케줄링
            while is_running[0]:
                current_time = datetime.now()
                
                # 스케줄 시간이 되었는지 체크 (1분 여유)
                if current_time >= next_schedule_time:
                    print(f"\n=== Scheduled Update Trigger ({current_time.strftime('%H:%M')}) ===")
                    
                    # 스케줄된 패턴 업데이트 실행
                    self._scheduled_pattern_update()
                    
                    # 다음 스케줄 시간 계산
                    next_schedule_time = self._get_next_15min_schedule()
                    print(f"Next scheduled update: {next_schedule_time.strftime('%H:%M')}")
                    print("=== Waiting for signals ===\n")
                
                time.sleep(30)  # 30초마다 체크
                
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
            print(f"Pattern generation completed! Duration: {duration}s")
        else:
            print(f"Pattern generation failed! Duration: {duration}s")


if __name__ == "__main__":
    main()