from src.database.raw_database import RawDatabaseManager, PriceRecord
from src.database.pattern_database import PatternDatabaseManager, MarketPriceCache
from datetime import datetime, timedelta
import time
from src.core.price_pattern_analyzer import PricePatternAnalyzer

def main():
    db_manager = RawDatabaseManager()
    cache_db = PatternDatabaseManager()
    analyzer = PricePatternAnalyzer(db_manager, debug=False)

    # search_cycle_id로만 조회하고 정렬
    with db_manager.get_read_session() as session:
        search_cycles = session.query(
            PriceRecord.search_cycle_id
        ).distinct().order_by(
            PriceRecord.search_cycle_id.desc()  # ID 역순 정렬
        ).all()

        total_cycles = len(search_cycles)
        print(f"Total {total_cycles} search cycles found")

        # 각 search_cycle에 대해 캐시 생성
        for i, (cycle_id,) in enumerate(search_cycles, 1):
            print(f"\nChecking cache for search cycle {cycle_id} ({i}/{total_cycles})")
            
            # 해당 search_cycle_id의 캐시가 있는지 확인
            with cache_db.get_read_session() as cache_session:
                existing_cache = cache_session.query(MarketPriceCache).filter_by(
                    search_cycle_id=cycle_id
                ).first()
                
                if existing_cache:
                    print(f"Cache already exists for cycle {cycle_id}, skipping...")
                    continue
            
            print(f"Creating cache for search cycle {cycle_id}")
            analyzer.update_cache(cycle_id)
            time.sleep(1)  # DB 부하 방지를 위한 짧은 대기

if __name__ == "__main__":
    main()