import time
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from src.database.pattern_database import (
    PatternDatabaseManager, AuctionPricePattern,
    AccessoryPricePattern, BraceletPricePattern
)
from src.common.utils import (
    fix_dup_options, create_accessory_pattern_key, create_bracelet_pattern_key,
    extract_common_option_features
)
from src.common.config import config

class ItemEvaluator:
    def __init__(self):
        self.pattern_db = PatternDatabaseManager()
        
        # 메모리 캐시 (pattern_generator와 동일한 구조)
        self._cached_patterns = {
            "dealer": {},
            "support": {},
            "bracelet": {},
            'pattern_datetime': None
        }
        
        # 초기 패턴 로드
        self._load_active_patterns()
        
    def _load_active_patterns(self):
        """활성 패턴을 메모리에 로드"""
        try:
            with self.pattern_db.get_read_session() as session:
                # 활성 패턴 조회
                active_pattern = session.query(AuctionPricePattern).filter_by(
                    is_active=True
                ).first()
                
                if not active_pattern:
                    return
                
                pattern_datetime = active_pattern.pattern_datetime
                
                # 이미 같은 패턴이 로드되어 있으면 스킵
                if self._cached_patterns['pattern_datetime'] == pattern_datetime:
                    return
                    
                # 캐시 초기화
                self._cached_patterns = {
                    "dealer": {},
                    "support": {},
                    "bracelet": {},
                    'pattern_datetime': pattern_datetime
                }
                
                # 악세서리 패턴 로드
                accessory_patterns = session.query(AccessoryPricePattern).filter_by(
                    pattern_datetime=pattern_datetime
                ).all()
                
                for pattern in accessory_patterns:
                    # SQLAlchemy 객체 대신 필요한 값들만 dictionary로 저장
                    cache_key = f"{pattern.grade}:{pattern.part}:{pattern.level}:{pattern.pattern_key}"
                    cached_pattern = {
                        'model_type': pattern.model_type,
                        'base_price': pattern.base_price,
                        'intercept': pattern.intercept,
                        'coefficients': pattern.coefficients,
                        'feature_names': pattern.feature_names
                    }
                    
                    if pattern.role == "dealer":
                        self._cached_patterns["dealer"][cache_key] = cached_pattern
                    elif pattern.role == "support":
                        self._cached_patterns["support"][cache_key] = cached_pattern
                
                # 팔찌 패턴 로드
                bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                    pattern_datetime=pattern_datetime
                ).all()
                
                for pattern in bracelet_patterns:
                    key = (pattern.grade, pattern.sorted_stats, pattern.extra_slots or '')
                    # SQLAlchemy 객체 대신 필요한 값만 저장
                    cached_pattern = {
                        'price': pattern.price
                    }
                    self._cached_patterns['bracelet'][key] = cached_pattern
                
                    
        except Exception as e:
            print(f"Error loading patterns: {e}")
            import traceback
            traceback.print_exc()
                
    def refresh_patterns(self):
        """패턴 캐시 강제 리프레시"""
        self._load_active_patterns()

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
        """악세서리 평가 - 새로운 multilinear regression 기반"""
        # 기본 검증
        if item["GradeQuality"] < 67:
            return None

        try:
            # 패턴이 없으면 평가 불가
            if not self._cached_patterns['pattern_datetime']:
                return None

            # 역할별로 pattern_key 생성
            dealer_pattern_key = create_accessory_pattern_key(item, "dealer")
            support_pattern_key = create_accessory_pattern_key(item, "support")
            
            # grade, part, level 추출 (가격 계산과 반환값에 필요)
            grade = item["Grade"]
            if "목걸이" in item["Name"]:
                part = "목걸이"
            elif "귀걸이" in item["Name"]:
                part = "귀걸이"
            elif "반지" in item["Name"]:
                part = "반지"
            else:
                part = "unknown"
            level = item["AuctionInfo"]["UpgradeLevel"]
            
            dealer_pattern = self._cached_patterns["dealer"].get(dealer_pattern_key)
            support_pattern = self._cached_patterns["support"].get(support_pattern_key)

            # 가격 계산
            dealer_price = self._calculate_accessory_price(item, [dealer_pattern] if dealer_pattern else [], part, "dealer")
            support_price = self._calculate_accessory_price(item, [support_pattern] if support_pattern else [], part, "support")

            current_price = item["AuctionInfo"]["BuyPrice"]
            
            # 더 높은 가격을 예상 가격으로 사용
            if dealer_price > support_price:
                expected_price = dealer_price
                usage_type = "딜러"
            else:
                expected_price = support_price
                usage_type = "서폿"

            price_ratio = current_price / expected_price if expected_price > 0 else float('inf')
            profit = expected_price - current_price

            # 패턴 정보 추가
            pattern_info = self._get_accessory_pattern_info(
                dealer_pattern_key, support_pattern_key, dealer_pattern, support_pattern, usage_type
            )

            return {
                "type": "accessory",
                "grade": grade,
                "part": part,
                "level": level,
                "current_price": current_price,
                "expected_price": expected_price,
                "price_ratio": price_ratio,
                "profit": profit,
                "usage_type": usage_type,
                "dealer_price": dealer_price,
                "support_price": support_price,
                **pattern_info  # 패턴 정보 추가
            }

        except Exception as e:
            print(f"Error evaluating accessory: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_accessory_price(self, item: Dict, patterns: List, part: str, role: str) -> int:
        """악세서리 가격 계산 - multilinear regression 또는 minimum price"""
        if not patterns:
            return 1000  # 기본값
            
        # 처첫 번째 패턴만 사용 (보통 하나만 있음)
        pattern = patterns[0]
        
        if pattern['model_type'] == 'minimum_price':
            # 최저가 모델
            return pattern['base_price']
        elif pattern['model_type'] == 'multilinear' and pattern['intercept'] is not None:
            # multilinear regression 모델: intercept + Σ(coefficient × feature_value)
            price = pattern['intercept']
            
            # 피처별 가격 추가
            if pattern['coefficients'] and pattern['feature_names']:
                feature_values = extract_common_option_features(item, role)
                for feature_name, coefficient in pattern['coefficients'].items():
                    if feature_name in feature_values:
                        price += coefficient * feature_values[feature_name]
            
            return max(int(price), 1)
        else:
            # fallback
            return pattern['base_price'] if pattern['base_price'] else 1000

    def _get_accessory_pattern_info(self, dealer_key: str, support_key: str, dealer_pattern, support_pattern, usage_type: str) -> Dict:
        """악세서리 패턴 정보 추출"""
        try:
            # 사용된 패턴에 따른 모델 정보
            active_pattern = dealer_pattern if usage_type == "딜러" else support_pattern
            active_key = dealer_key if usage_type == "딜러" else support_key
            
            model_info = self._extract_model_info(active_pattern)
            
            return {
                "dealer_pattern_key": dealer_key,  # 이미 문자열
                "support_pattern_key": support_key,  # 이미 문자열
                "active_pattern_key": active_key,  # 이미 문자열
                "model_type": active_pattern['model_type'] if active_pattern else None,
                "model_info": model_info
            }
        except Exception as e:
            return {
                "dealer_pattern_key": dealer_key,
                "support_pattern_key": support_key,
                "active_pattern_key": "error",
                "model_type": None,
                "model_info": f"error: {e}"
            }

    def _extract_model_info(self, pattern) -> str:
        """패턴 dictionary에서 모델 정보 추출"""
        if not pattern:
            return "none"
            
        model_type = pattern['model_type'] or "unknown"
        
        if model_type == "multilinear" and pattern['coefficients']:
            # 중요한 계수들만 표시 (상위 3개)
            coeffs = pattern['coefficients']
            sorted_coeffs = sorted(coeffs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            coeff_str = ",".join([f"{k}:{v:.1f}" for k, v in sorted_coeffs])
            return f"{model_type}[{coeff_str}]"
        elif model_type == "minimum_price":
            return f"{model_type}[{pattern['base_price']:,}]"
        else:
            return model_type


    def _evaluate_bracelet(self, item: Dict) -> Optional[Dict]:
        """팔찌 평가 - sorted_stats 기반 매칭"""
        grade = item["Grade"]
        current_price = item["AuctionInfo"]["BuyPrice"]

        try:
            # 패턴이 없으면 평가 불가
            if not self._cached_patterns['pattern_datetime']:
                return None
            
            # 팔찌 pattern_key 생성
            cache_key = create_bracelet_pattern_key(item)
            grade, sorted_stats, extra_slots = cache_key.split(':', 2)
            
            # 캐시에서 매칭되는 팔찌 패턴 찾기
            bracelet_key = (grade, sorted_stats, extra_slots)
            bracelet_pattern = self._cached_patterns["bracelet"].get(bracelet_key)

            if not bracelet_pattern:
                return None

            expected_price = bracelet_pattern['price']
            price_ratio = current_price / expected_price if expected_price > 0 else float('inf')
            profit = expected_price - current_price

            return {
                "type": "bracelet",
                "grade": grade,
                "current_price": current_price,
                "expected_price": expected_price,
                "price_ratio": price_ratio,
                "profit": profit,
                "extra_option_count": int(extra_slots) if extra_slots.isdigit() else 0,
                "sorted_stats": sorted_stats,
            }

        except Exception as e:
            print(f"Error evaluating bracelet: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _sigmoid(self, expected_price: int) -> float:
        """수익성 판단을 위한 시그모이드 함수"""
        min_ratio = 0.5
        max_ratio = 0.75
        max_price = 400000
        k3 = 3e-5  # 가장 완만한 기울기
        midpoint3 = max_price*2/3  # 가장 늦은 변곡점
        sigmoid_ratio = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k3 * (expected_price - midpoint3)))
        return expected_price * sigmoid_ratio