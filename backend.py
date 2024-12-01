from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime
import json
from cache_database import *
from cache_database import AccessoryPricePattern, BraceletPricePattern
from datetime import datetime, timedelta
from typing import Dict, List

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DataService:
    def __init__(self):
        self.cache_db = init_cache_database()

    def get_time_range(self, range_str: str) -> datetime:
        """시간 범위 문자열을 datetime으로 변환"""
        now = datetime.now()
        if range_str == "1d":
            return now - timedelta(days=1)
        elif range_str == "1w":
            return now - timedelta(weeks=1)
        elif range_str == "1m":
            return now - timedelta(days=30)
        elif range_str == "3m":
            return now - timedelta(days=90)
        else:
            return now - timedelta(days=1)  # 기본값 1일

    def get_price_trends(self, 
                        role: Optional[str] = None, 
                        grade: Optional[str] = None,
                        part: Optional[str] = None,
                        time_range: str = "1d") -> Dict:
        """가격 추이 데이터 조회"""
        with self.cache_db.get_read_session() as session:
            # 시간 범위 설정
            start_time = self.get_time_range(time_range)
            
            # 기본 쿼리 구성
            cache_entries = session.query(MarketPriceCache)\
                .filter(MarketPriceCache.timestamp >= start_time)\
                .order_by(MarketPriceCache.timestamp.asc())\
                .all()

            trends = {}
            for cache in cache_entries:
                # 타임스탬프를 밀리초 단위로 변환 (JavaScript Date 객체용)
                timestamp = int(cache.timestamp.timestamp() * 1000)
                
                # 필터 조건 구성
                filters = {}
                if role:
                    filters['role'] = role
                if grade:
                    filters['grade'] = grade
                if part:
                    filters['part'] = part

                # 패턴 조회
                patterns = session.query(AccessoryPricePattern)\
                    .filter_by(cache_id=cache.cache_id, **filters)\
                    .all()

                for pattern in patterns:
                    key = f"{pattern.grade}:{pattern.part}:{pattern.level}:{pattern.pattern_key}"
                    if key not in trends:
                        trends[key] = []
                    
                    # 시계열 데이터 포인트 추가
                    trends[key].append({
                        'timestamp': timestamp,
                        'base_price': pattern.base_price,
                        'sample_count': pattern.sample_count,
                        'quality_coefficient': pattern.quality_coefficient,
                        'trade_count_coefficient': pattern.trade_count_coefficient
                    })

            # 각 패턴의 데이터 정렬 및 최적화
            for key in trends:
                # 시간순 정렬
                trends[key].sort(key=lambda x: x['timestamp'])
                
                # 데이터 포인트 최적화 (너무 많은 경우)
                if len(trends[key]) > 1000:  # 적절한 임계값 설정
                    optimized_data = self._optimize_time_series(trends[key])
                    trends[key] = optimized_data

            return trends

    def _optimize_time_series(self, data: List[Dict]) -> List[Dict]:
        """시계열 데이터 최적화"""
        # 데이터 포인트가 너무 많을 경우 다운샘플링
        if len(data) <= 1000:  # 임계값
            return data

        # 시간 간격 기반 다운샘플링
        result = []
        window_size = len(data) // 1000 + 1
        
        for i in range(0, len(data), window_size):
            window = data[i:i + window_size]
            # 윈도우 내 데이터의 평균값 계산
            avg_point = {
                'timestamp': window[len(window)//2]['timestamp'],  # 중간 시점 사용
                'base_price': sum(p['base_price'] for p in window) / len(window),
                'sample_count': sum(p['sample_count'] for p in window) / len(window),
                'quality_coefficient': sum(p['quality_coefficient'] for p in window) / len(window),
                'trade_count_coefficient': sum(p['trade_count_coefficient'] for p in window) / len(window)
            }
            result.append(avg_point)

        return result

    def get_all_patterns(self) -> Dict:
        """모든 패턴 데이터 조회"""
        with self.cache_db.get_read_session() as session:
            # 가장 최근의 활성 캐시 조회
            active_cache = session.query(MarketPriceCache)\
                .filter_by(is_active=True)\
                .first()
            
            if not active_cache:
                raise HTTPException(status_code=404, detail="No active cache found")

            dealer_patterns = {}
            support_patterns = {}

            # 패턴 조회 및 정렬 (샘플 수 기준)
            patterns = session.query(AccessoryPricePattern)\
                .filter_by(cache_id=active_cache.cache_id)\
                .all()

            for pattern in patterns:
                pattern_data = {
                    'grade': pattern.grade,
                    'part': pattern.part,
                    'level': pattern.level,
                    'pattern': pattern.pattern_key,
                    'base_price': pattern.base_price,
                    'sample_count': pattern.sample_count,
                    'quality_coefficient': pattern.quality_coefficient,
                    'trade_count_coefficient': pattern.trade_count_coefficient,
                    'total_sample_count': pattern.total_sample_count,
                    'common_option_values': json.loads(pattern.common_option_values)
                }

                full_key = f"{pattern.grade}:{pattern.part}:{pattern.level}:{pattern.pattern_key}"

                if pattern.role == 'dealer':
                    dealer_patterns[full_key] = pattern_data
                else:
                    support_patterns[full_key] = pattern_data

            return {
                'dealer': dealer_patterns,
                'support': support_patterns
            }

    def get_bracelet_patterns(self, grade: Optional[str] = None) -> Dict:
        """팔찌 패턴 데이터 조회"""
        with self.cache_db.get_read_session() as session:
            active_cache = session.query(MarketPriceCache)\
                .filter_by(is_active=True)\
                .first()
            
            if not active_cache:
                return {}

            filters = {'cache_id': active_cache.cache_id}
            if grade:
                filters['grade'] = grade

            patterns = session.query(BraceletPricePattern)\
                .filter_by(**filters)\
                .all()

            result = {}
            for pattern in patterns:
                key = f"{pattern.grade}:{pattern.pattern_type}"
                if key not in result:
                    result[key] = []

                result[key].append({
                    'combat_stats': pattern.combat_stats,
                    'base_stats': pattern.base_stats,
                    'extra_slots': pattern.extra_slots,
                    'price': pattern.price
                })

            return result

# 서비스 인스턴스 생성
data_service = DataService()

@app.get("/api/price-trends")
async def price_trends(
    role: Optional[str] = Query(None, enum=['dealer', 'support']),
    grade: Optional[str] = Query(None, enum=['고대', '유물']),
    part: Optional[str] = Query(None, enum=['목걸이', '귀걸이', '반지']),
    time_range: str = Query("1d", enum=["1d", "1w", "1m", "3m"])
):
    """가격 추이 데이터 API"""
    try:
        return data_service.get_price_trends(role, grade, part, time_range)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/all-patterns")
async def all_patterns():
    """모든 패턴 데이터 API"""
    try:
        return data_service.get_all_patterns()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bracelets")
async def bracelet_patterns(
    grade: Optional[str] = Query(None, enum=['고대', '유물'])
):
    """팔찌 패턴 데이터 API"""
    return data_service.get_bracelet_patterns(grade)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)