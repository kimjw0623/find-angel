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
    def __init__(self, debug=False):
        self.debug = debug
        self.pattern_db = PatternDatabaseManager()
        
        # 메모리 캐시
        self._cached_patterns = {
            'accessory': {},  # {(grade, part, level, role, pattern_key): pattern}
            'bracelet': {},   # {(grade, sorted_stats, extra_slots): pattern}
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
                    if self.debug:
                        print("No active pattern found")
                    return
                
                pattern_datetime = active_pattern.pattern_datetime
                
                # 이미 같은 패턴이 로드되어 있으면 스킵
                if self._cached_patterns['pattern_datetime'] == pattern_datetime:
                    return
                    
                if self.debug:
                    print(f"Loading patterns for {pattern_datetime}")
                
                # 캐시 초기화
                self._cached_patterns = {
                    'accessory': {},
                    'bracelet': {},
                    'pattern_datetime': pattern_datetime
                }
                
                # 악세서리 패턴 로드
                accessory_patterns = session.query(AccessoryPricePattern).filter_by(
                    pattern_datetime=pattern_datetime
                ).all()
                
                for pattern in accessory_patterns:
                    key = (pattern.grade, pattern.part, pattern.level, pattern.role, pattern.pattern_key)
                    self._cached_patterns['accessory'][key] = pattern
                
                # 팔찌 패턴 로드
                bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                    pattern_datetime=pattern_datetime
                ).all()
                
                for pattern in bracelet_patterns:
                    key = (pattern.grade, pattern.sorted_stats, pattern.extra_slots or '')
                    self._cached_patterns['bracelet'][key] = pattern
                
                if self.debug:
                    print(f"Loaded {len(accessory_patterns)} accessory patterns, {len(bracelet_patterns)} bracelet patterns")
                    
        except Exception as e:
            if self.debug:
                print(f"Error loading patterns: {e}")
                import traceback
                traceback.print_exc()
                
    def refresh_patterns(self):
        """패턴 캐시 강제 리프레시"""
        if self.debug:
            print("Refreshing pattern cache...")
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
                if self.debug:
                    print("No active pattern found")
                return None

            # 역할별로 pattern_key 생성 및 grade, part, level 추출
            dealer_pattern_key = create_accessory_pattern_key(item, "dealer")
            support_pattern_key = create_accessory_pattern_key(item, "support")
            
            # pattern_key에서 grade, part, level 추출
            # 형식: "grade:part:level:options" 또는 "grade:part:level:base"
            dealer_parts = dealer_pattern_key.split(":")
            grade, part, level = dealer_parts[0], dealer_parts[1], int(dealer_parts[2])
            
            # 캐시에서 패턴 조회
            dealer_key = (grade, part, level, "dealer", dealer_pattern_key)
            support_key = (grade, part, level, "support", support_pattern_key)
            
            dealer_pattern = self._cached_patterns['accessory'].get(dealer_key)
            support_pattern = self._cached_patterns['accessory'].get(support_key)

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
                "usage_type": usage_type,
                "dealer_price": dealer_price,
                "support_price": support_price,
                "is_notable": self._is_notable_accessory(level, current_price, expected_price, price_ratio)
            }

        except Exception as e:
            if self.debug:
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
        
        if pattern.model_type == 'minimum_price':
            # 최저가 모델
            return pattern.base_price
        elif pattern.model_type == 'multilinear' and pattern.intercept is not None:
            # multilinear regression 모델: intercept + Σ(coefficient × feature_value)
            price = pattern.intercept
            
            # 피처별 가격 추가
            if pattern.coefficients and pattern.feature_names:
                feature_values = extract_common_option_features(item, role)
                for feature_name, coefficient in pattern.coefficients.items():
                    if feature_name in feature_values:
                        price += coefficient * feature_values[feature_name]
            
            return max(int(price), 1)
        else:
            # fallback
            return pattern.base_price if pattern.base_price else 1000


    def _evaluate_bracelet(self, item: Dict) -> Optional[Dict]:
        """팔찌 평가 - sorted_stats 기반 매칭"""
        grade = item["Grade"]
        current_price = item["AuctionInfo"]["BuyPrice"]

        try:
            # 패턴이 없으면 평가 불가
            if not self._cached_patterns['pattern_datetime']:
                if self.debug:
                    print("No active pattern found for bracelet")
                return None
            
            # 팔찌 pattern_key 생성
            cache_key = create_bracelet_pattern_key(item)
            grade, sorted_stats, extra_slots = cache_key.split(':', 2)
            
            # 캐시에서 매칭되는 팔찌 패턴 찾기
            bracelet_key = (grade, sorted_stats, extra_slots)
            bracelet_pattern = self._cached_patterns['bracelet'].get(bracelet_key)

            if not bracelet_pattern:
                # 매칭되는 패턴이 없으면 높은 가격일 때만 로그
                if current_price > 5000:
                    if self.debug:
                        print(f"{grade} {item['Name']} | {current_price:,}골드 vs ?? | 만료 {item['AuctionInfo']['EndDate']} | {sorted_stats}")
                return None

                expected_price = bracelet_pattern.price
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
                    "is_notable": self._is_notable_bracelet(current_price, expected_price, price_ratio),
                }

        except Exception as e:
            if self.debug:
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

    def _is_notable_accessory(
        self, level: int, current_price: int, expected_price: int, price_ratio: float
    ) -> bool:
        """악세서리가 주목할 만한지 판단"""
        if expected_price > 20000 and current_price < self._sigmoid(expected_price):
            return True
        return False

    def _is_notable_bracelet(self, current_price: int, expected_price: int, price_ratio: float) -> bool:
        """팔찌가 주목할 만한지 판단"""
        if expected_price > 20000 and current_price < self._sigmoid(expected_price):
            return True
        return False