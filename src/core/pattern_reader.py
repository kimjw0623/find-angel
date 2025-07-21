"""
패턴 조회 전용 클래스 - DB에서 직접 패턴 데이터 조회
"""
from typing import Dict, Optional, Tuple, Any
from datetime import datetime
from src.database.pattern_database import (
    PatternDatabaseManager, AuctionPricePattern, 
    AccessoryPricePattern, BraceletPricePattern
)

class PatternReader:
    """패턴 데이터 조회 전용 클래스"""
    
    def __init__(self, debug: bool = False):
        self.pattern_db = PatternDatabaseManager()
        self.debug = debug
        self._last_update_time = None
    
    def get_last_update_time(self) -> Optional[datetime]:
        """최신 패턴 업데이트 시간 조회"""
        try:
            with self.pattern_db.get_read_session() as session:
                latest_pattern = session.query(AuctionPricePattern).filter_by(
                    is_active=True
                ).order_by(AuctionPricePattern.pattern_id.desc()).first()
                
                if latest_pattern:
                    # pattern_id는 datetime의 isoformat이므로 파싱
                    self._last_update_time = datetime.fromisoformat(latest_pattern.pattern_id)
                    return self._last_update_time
                
        except Exception as e:
            if self.debug:
                print(f"Error getting last update time: {e}")
                
        return None
    
    def get_price_data(self, grade: str, part: str, level: int, reference_options: Dict) -> Dict[str, Any]:
        """악세서리 가격 데이터 조회"""
        try:
            with self.pattern_db.get_read_session() as session:
                # 활성 패턴에서 해당 조건의 데이터 조회
                active_pattern = session.query(AuctionPricePattern).filter_by(
                    is_active=True
                ).first()
                
                if not active_pattern:
                    if self.debug:
                        print("No active pattern found")
                    return self._get_default_price_data()
                
                # 딜러/서포터용 데이터 조회
                dealer_data = self._get_accessory_pattern_data(
                    session, active_pattern.pattern_id, grade, part, level, "dealer"
                )
                support_data = self._get_accessory_pattern_data(
                    session, active_pattern.pattern_id, grade, part, level, "support"
                )
                
                return {
                    "dealer": dealer_data,
                    "support": support_data
                }
                
        except Exception as e:
            if self.debug:
                print(f"Error getting price data: {e}")
            return self._get_default_price_data()
    
    def _get_accessory_pattern_data(self, session, pattern_id: str, grade: str, 
                                  part: str, level: int, role: str) -> Dict[str, Any]:
        """악세서리 패턴 데이터 조회"""
        try:
            # 해당 조건의 패턴 데이터들 조회
            patterns = session.query(AccessoryPricePattern).filter_by(
                pattern_id=pattern_id,
                grade=grade,
                part=part, 
                level=level,
                role=role
            ).all()
            
            if not patterns:
                return self._get_default_accessory_data()
            
            # 품질별 가격과 공통 옵션 값들을 병합
            quality_prices = {}
            common_option_values = {}
            
            for pattern in patterns:
                if pattern.quality_prices:
                    quality_prices.update(pattern.quality_prices)
                if pattern.common_option_values:
                    common_option_values.update(pattern.common_option_values)
            
            return {
                "quality_prices": quality_prices,
                "common_option_values": common_option_values
            }
            
        except Exception as e:
            if self.debug:
                print(f"Error getting {role} data for {grade} {part} level {level}: {e}")
            return self._get_default_accessory_data()
    
    def get_bracelet_price(self, grade: str, item_data: Dict) -> Optional[Tuple[int, int]]:
        """팔찌 가격 조회"""
        try:
            with self.pattern_db.get_read_session() as session:
                # 활성 패턴에서 팔찌 데이터 조회
                active_pattern = session.query(AuctionPricePattern).filter_by(
                    is_active=True
                ).first()
                
                if not active_pattern:
                    if self.debug:
                        print("No active pattern found for bracelet")
                    return None
                
                # 팔찌 패턴들 조회
                bracelet_patterns = session.query(BraceletPricePattern).filter_by(
                    pattern_id=active_pattern.pattern_id,
                    grade=grade
                ).all()
                
                if not bracelet_patterns:
                    if self.debug:
                        print(f"No bracelet patterns found for {grade}")
                    return None
                
                # 아이템 데이터와 매칭되는 패턴 찾기
                # (기존 _classify_bracelet_pattern 로직을 여기서 사용해야 함)
                # 일단 간단하게 첫 번째 패턴 가격 반환
                first_pattern = bracelet_patterns[0]
                if first_pattern.pattern_data:
                    pattern_prices = first_pattern.pattern_data
                    if pattern_prices:
                        first_price_info = next(iter(pattern_prices.values()))
                        if isinstance(first_price_info, (list, tuple)) and len(first_price_info) >= 2:
                            return (first_price_info[0], first_price_info[1])
                        elif isinstance(first_price_info, int):
                            return (first_price_info, 1)
                
                return None
                
        except Exception as e:
            if self.debug:
                print(f"Error getting bracelet price: {e}")
            return None
    
    def _get_default_price_data(self) -> Dict[str, Any]:
        """기본 가격 데이터"""
        return {
            "dealer": self._get_default_accessory_data(),
            "support": self._get_default_accessory_data()
        }
    
    def _get_default_accessory_data(self) -> Dict[str, Any]:
        """기본 악세서리 데이터"""
        return {
            "quality_prices": {
                60: 1000, 70: 2000, 80: 5000, 90: 10000, 100: 20000
            },
            "common_option_values": {}
        }