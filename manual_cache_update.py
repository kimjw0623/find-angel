from database import DatabaseManager
from cache_database import init_cache_database
from datetime import datetime, timedelta
import time
from market_price_cache import DBMarketPriceCache

def main():
    db_manager = DatabaseManager()
    cache = DBMarketPriceCache(db_manager, debug=False)

    # # 2024년 1월 1일부터 2시간 간격으로
    # start_time = datetime(2024, 11, 30, 21, 10)
    # cache.update_cache(start_time)

    start_time = datetime(2024, 11, 18, 3, 10)
    end_time = datetime(2024, 11, 30, 23, 10)
    
    current_time = start_time
    while current_time < end_time:
        print(f"\nProcessing cache for {current_time}")
        cache.update_cache(current_time)
        current_time += timedelta(hours=2)
        time.sleep(1)  # DB 부하 방지를 위한 짧은 대기

if __name__ == "__main__":
    main()