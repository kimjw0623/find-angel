from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime
import json
from src.database.pattern_database import *
from src.database.pattern_database import AccessoryPricePattern, BraceletPricePattern
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

def parse_search_cycle_id(search_cycle_id: str) -> datetime:
    """YYYYMMDD_HHMM 형식의 search_cycle_id를 datetime으로 변환"""
    return datetime.strptime(search_cycle_id, "%Y%m%d_%H%M")

def get_search_cycle_id_range(range_str: str) -> str:
    """시간 범위에 따른 search_cycle_id 기준값 계산"""
    now = datetime.now()
    if range_str == "1d":
        start_time = now - timedelta(days=1)
    elif range_str == "1w":
        start_time = now - timedelta(weeks=1)
    elif range_str == "1m":
        start_time = now - timedelta(days=30)
    else:  # all
        start_time = datetime(2000, 1, 1)
    
    return start_time.strftime("%Y%m%d_%H%M")

class DataService:
    def __init__(self):
        self.cache_db = CacheDBManager()

    def get_price_trends(self, 
                        role: Optional[str] = None, 
                        grade: Optional[str] = None,
                        part: Optional[str] = None,
                        time_range: str = "1d") -> Dict:
        """가격 추이 데이터 조회"""
        with self.cache_db.get_read_session() as session:
            # search_cycle_id 범위 설정
            start_search_cycle_id = get_search_cycle_id_range(time_range)
            
            # 기본 쿼리 구성
            cache_entries = session.query(MarketPriceCache)\
                .filter(MarketPriceCache.search_cycle_id >= start_search_cycle_id)\
                .order_by(MarketPriceCache.search_cycle_id.asc())\
                .all()

            trends = {}
            for cache in cache_entries:
                # search_cycle_id를 datetime으로 변환 후 타임스탬프로
                timestamp = int(parse_search_cycle_id(cache.search_cycle_id).timestamp() * 1000)
                
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
                    
                    # quality_prices를 JSON에서 변환
                    quality_prices = json.loads(pattern.quality_prices)
                    
                    # 시계열 데이터 포인트 추가
                    trends[key].append({
                        'timestamp': timestamp,
                        'quality_prices': quality_prices,
                        'sample_count': pattern.total_sample_count,
                        'common_option_values': json.loads(pattern.common_option_values)  # 이 부분 추가
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
        if len(data) <= 1000:  # 임계값
            return data

        # 시간 간격 기반 다운샘플링
        result = []
        window_size = len(data) // 1000 + 1
        
        for i in range(0, len(data), window_size):
            window = data[i:i + window_size]
            # 윈도우 내 데이터의 평균값 계산
            
            # 품질별 가격의 평균 계산
            avg_quality_prices = {}
            for quality in window[0]['quality_prices'].keys():
                prices = [p['quality_prices'][quality] for p in window]
                avg_quality_prices[quality] = sum(prices) / len(prices)
            
            avg_point = {
                'timestamp': window[len(window)//2]['timestamp'],  # 중간 시점 사용
                'quality_prices': avg_quality_prices,
                'sample_count': sum(p['sample_count'] for p in window) / len(window)
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
                # JSON 데이터 파싱
                quality_prices = json.loads(pattern.quality_prices)
                common_option_values = json.loads(pattern.common_option_values)
                
                pattern_data = {
                    'grade': pattern.grade,
                    'part': pattern.part,
                    'level': pattern.level,
                    'pattern': pattern.pattern_key,
                    'quality_prices': quality_prices,
                    'common_option_values': common_option_values,
                    'sample_count': pattern.total_sample_count
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
                    'price': pattern.price,
                    'sample_count': pattern.total_sample_count
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

@app.get("/api/bracelet-trends")
async def bracelet_trends(
    grade: Optional[str] = Query(None, enum=['고대', '유물']),
    time_range: str = Query("1d", enum=["1d", "1w", "1m", "3m"])
):
    """팔찌 가격 추이 데이터 API"""
    try:
        with data_service.cache_db.get_read_session() as session:
            # search_cycle_id 범위 설정
            start_search_cycle_id = get_search_cycle_id_range(time_range)
            
            # 기본 쿼리 구성
            cache_entries = session.query(MarketPriceCache)\
                .filter(MarketPriceCache.search_cycle_id >= start_search_cycle_id)\
                .order_by(MarketPriceCache.search_cycle_id.asc())\
                .all()

            trends = {}
            for cache in cache_entries:
                timestamp = int(parse_search_cycle_id(cache.search_cycle_id).timestamp() * 1000)

                # 패턴별 가격 데이터 조회
                patterns = session.query(BraceletPricePattern)\
                    .filter_by(cache_id=cache.cache_id)
                
                if grade:
                    patterns = patterns.filter_by(grade=grade)

                for pattern in patterns:
                    pattern_key = f"{pattern.grade}:{pattern.pattern_type}:{pattern.combat_stats or ''}:{pattern.base_stats or ''}:{pattern.extra_slots}"
                    
                    if pattern_key not in trends:
                        trends[pattern_key] = []
                    
                    # 패턴의 시계열 데이터 추가
                    trends[pattern_key].append({
                        'timestamp': timestamp,
                        'price': pattern.price,
                        'sample_count': pattern.total_sample_count
                    })
            
            return trends

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bracelet-patterns")
async def bracelet_patterns(
    grade: Optional[str] = Query(None, enum=['고대', '유물'])
):
    """팔찌 패턴과 현재 가격 데이터 API"""
    try:
        with data_service.cache_db.get_read_session() as session:
            # 가장 최근의 활성 캐시 조회
            active_cache = session.query(MarketPriceCache)\
                .filter_by(is_active=True)\
                .first()
            
            if not active_cache:
                raise HTTPException(status_code=404, detail="No active cache found")

            # 패턴 조회 쿼리 구성
            patterns_query = session.query(BraceletPricePattern)\
                .filter_by(cache_id=active_cache.cache_id)
            
            if grade:
                patterns_query = patterns_query.filter_by(grade=grade)

            # 결과 생성
            patterns = {}
            for pattern in patterns_query:
                pattern_key = f"{pattern.grade}:{pattern.pattern_type}:{pattern.combat_stats or ''}:{pattern.base_stats or ''}:{pattern.extra_slots}"
                
                patterns[pattern_key] = {
                    'grade': pattern.grade,
                    'type': pattern.pattern_type,
                    'combat_stats': pattern.combat_stats,
                    'base_stats': pattern.base_stats,
                    'special_effects': pattern.extra_slots,  # 부여 효과는 special_effects로 매핑
                    'fixed_option_count': int(pattern.pattern_type.split()[1]) if pattern.pattern_type else None,
                    'extra_option_count': int(pattern.extra_slots.split()[1]) if pattern.extra_slots else None,
                    'current_price': pattern.price,
                    'sample_count': pattern.total_sample_count
                }

            return patterns

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)