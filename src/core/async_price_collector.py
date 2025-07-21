from typing import List
from datetime import datetime, timedelta
import asyncio
from src.api.async_api_client import TokenBatchRequester
from src.core.pattern_generator import PatternGenerator
from src.database.raw_database import *
from src.common.utils import *
from src.common.config import config
from src.common.utils import create_basic_search_request, add_search_option

class AsyncPriceCollector:
    def __init__(self, db_manager: RawDatabaseManager, tokens: List[str]):
        self.db = db_manager
        self.generator = PatternGenerator(self.db)
        self.requester = TokenBatchRequester(tokens)
        self.ITEMS_PER_PAGE = config.items_per_page
        
    async def run(self, immediate=False, once=False):
        """메인 실행 함수"""
        first_run = True
        
        while True:
            try:
                # 첫 실행시 immediate 옵션 확인
                if first_run and immediate:
                    print("즉시 가격 수집을 시작합니다...")
                else:
                    # 다음 실행 시간까지 대기
                    next_run = self._get_next_run_time()
                    wait_seconds = (next_run - datetime.now()).total_seconds() + config.time_settings["safety_buffer_seconds"]
                    if wait_seconds > 0:
                        print(f"다음 실행 시간: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"대기 중... ({int(wait_seconds)}초)")
                        await asyncio.sleep(wait_seconds)

                # 가격 수집 실행
                start_time = datetime.now()
                print(f"Starting price collection at {start_time}")
                
                await self.collect_prices()
                
                end_time = datetime.now()
                duration = end_time - start_time
                print(f"Completed price collection at {end_time}")
                print(f"Duration: {duration}")
                
                # once 옵션이면 한 번만 실행 후 종료
                if once:
                    print("한 번만 실행 옵션이 설정되어 종료합니다.")
                    break
                    
                first_run = False
                
            except KeyboardInterrupt:
                print("\n프로그램이 중단되었습니다.")
                break
            except Exception as e:
                print(f"Error in collection cycle: {e}")
                await asyncio.sleep(config.time_settings["error_retry_delay"])
                if once:
                    print("에러 발생 후 once 옵션으로 종료합니다.")
                    break
                    
        # 프로그램 종료 시 리소스 정리
        await self.requester.close()
        print("리소스 정리 완료")

    async def collect_prices(self):
        """비동기 가격 수집 (파이프라인 방식)"""
        try:            
            # 모든 수집 작업 생성
            collection_tasks = []
            
            # 장신구 수집 준비
            grades = ["고대", "유물"]
            accessory_parts = ["목걸이", "귀걸이", "반지"]
            enhancement_levels = [0, 1, 2, 3]
            fixed_slots_list = [1, 2]
            extra_slots_list = [1, 2]
            
            for grade in grades:
                # 1. 목걸이/귀걸이/반지 수집 작업 생성
                for part in accessory_parts:
                    for enhancement_level in enhancement_levels:
                        task = self._collect_and_save_accessory_data(grade, part, enhancement_level)
                        collection_tasks.append(task)
                
                # 2. 팔찌 수집 작업 생성
                bonus_slots = 1 if grade == "고대" else 0
                for fixed_slots in fixed_slots_list:
                    for extra_slots in extra_slots_list:
                        task = self._collect_and_save_bracelet_data(grade, fixed_slots, extra_slots + bonus_slots)
                        collection_tasks.append(task)

            # 모든 작업을 파이프라인 방식으로 실행
            print(f"Starting {len(collection_tasks)} collection tasks in pipeline...")
            results = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            # 결과 집계
            total_collected = 0
            for result in results:
                if isinstance(result, Exception):
                    print(f"Collection task failed: {result}")
                elif isinstance(result, int):
                    total_collected += result
                else:
                    print(f"Unexpected result type: {type(result)}, value: {result}")

            print(f"Total collected items: {total_collected}")
            
            if total_collected > 0:
                # 캐시 업데이트
                print(f"\nStarting pattern update...")
                update_start = datetime.now()
                
                current_cycle_id = datetime.now()
                success = self.generator.update_pattern(current_cycle_id)
                
                update_end = datetime.now()
                update_duration = (update_end - update_start).total_seconds()
                
                if success:
                    print(f"Pattern update completed! Duration: {update_duration:.1f}s")
                else:
                    print(f"Pattern update failed! Duration: {update_duration:.1f}s")
                
        except Exception as e:
            print(f"Error in price collection: {e}")

    async def _collect_accessory_data(self, grade: str, part: str, enhancement_level: int) -> int:
        """특정 등급/부위/연마 단계의 장신구 데이터 수집"""
        total_collected = 0

        # 1. 전체 페이지 수 확인
        search_data = create_basic_search_request(grade, part, enhancement_level)
        
        # 페이지 수 확인을 위한 첫 요청
        results = await self.requester.process_requests([search_data])
        if not results[0]:
            print(f"Failed to get initial data for {grade} {part} +{enhancement_level}연마")
            return 0
            
        total_count = results[0].get('TotalCount', 0)
        total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        print(f"{grade} {part} {enhancement_level}연마: {total_count} items ({total_pages} pages)")

        # 2. 모든 페이지 요청 생성
        all_requests = [
            create_basic_search_request(grade, part, enhancement_level, page_no=page)
            for page in range(1, total_pages + 1)
        ]

        # 3. 모든 요청 처리
        results = await self.requester.process_requests(all_requests)

        # 4-5. 원시 응답에서 모든 아이템 수집하여 DB에 저장
        all_raw_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                data = result
                if data.get("Items"):
                    search_timestamp = result.get('search_timestamp')
                    # 유효한 아이템만 필터링
                    valid_items = [
                        (item, search_timestamp) for item in data["Items"]
                        if item["AuctionInfo"]["BuyPrice"] and item["GradeQuality"] >= 67
                    ]
                    all_raw_items.extend(valid_items)

        if all_raw_items:
            print(f"Processing {grade} {part} {enhancement_level}연마 {len(all_raw_items)} items...")
            stats = await self.db.bulk_save_accessories(all_raw_items)
            total_collected = stats['new_items_added']
            print(f"Stats: {stats['total_items']} total, {stats['existing_updated']} updated, {stats['new_items_added']} new")
        else:
            total_collected = 0

        return total_collected

    async def _collect_bracelet_data(self, grade: str, fixed_slots: int, extra_slots: int) -> int:
        """특정 등급의 팔찌 데이터 수집 (고정/부여 효과 수량별)"""
        
        # 1. 전체 페이지 수 확인
        search_data = create_basic_search_request(grade, "팔찌")
        search_data["EtcOptions"] = [
            add_search_option("팔찌 옵션 수량", "고정 효과 수량", fixed_slots),
            add_search_option("팔찌 옵션 수량", "부여 효과 수량", extra_slots)
        ]
        
        # 페이지 수 확인을 위한 첫 요청
        results = await self.requester.process_requests([search_data])
        if not results[0]:
            print(f"Failed to get initial data for {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여")
            return 0
            
        total_count = results[0].get('TotalCount', 0)
        total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        print(f"{grade} 팔찌 {fixed_slots}고정 {extra_slots}부여: {total_count} items ({total_pages} pages)")

        # 2. 모든 페이지 요청 생성  
        bracelet_etc_options = [
            add_search_option("팔찌 옵션 수량", "고정 효과 수량", fixed_slots),
            add_search_option("팔찌 옵션 수량", "부여 효과 수량", extra_slots)
        ]
        
        all_requests = []
        for page in range(1, total_pages + 1):
            search_data = create_basic_search_request(grade, "팔찌", page_no=page)
            search_data["EtcOptions"] = bracelet_etc_options
            all_requests.append(search_data)

        # 3. 모든 요청 처리
        results = await self.requester.process_requests(all_requests)

        # 4-5. 원시 응답에서 모든 아이템 수집하여 DB에 저장
        all_raw_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                data = result
                if data.get("Items"):
                    search_timestamp = result.get('search_timestamp')
                    # 유효한 아이템만 필터링
                    valid_items = [
                        (item, search_timestamp) for item in data["Items"]
                        if item["AuctionInfo"]["BuyPrice"]
                    ]
                    all_raw_items.extend(valid_items)

        if all_raw_items:
            print(f"Processing {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여 {len(all_raw_items)} items...")
            stats = await self.db.bulk_save_bracelets(all_raw_items)
            total_collected = stats['new_items_added']
            print(f"Stats: {stats['total_items']} total, {stats['existing_updated']} updated, {stats['new_items_added']} new")
        else:
            total_collected = 0

        return total_collected

    def _get_next_run_time(self) -> datetime:
        """Calculate the next run time (every 30 minutes)"""
        now = datetime.now()
        
        if now.minute >= 30:
            # If it's past 30 minutes, go to the next hour
            next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            # Otherwise, go to the next 30 minutes
            next_run = now.replace(minute=30, second=0, microsecond=0)
            
        if next_run <= now:
            # If the next run time is in the past, go to the next 30 minutes
            next_run += timedelta(minutes=30)
            
        return next_run

    async def _collect_and_save_accessory_data(self, grade: str, part: str, enhancement_level: int) -> int:
        """악세서리 데이터 수집과 저장을 하나의 파이프라인으로 처리"""
        try:
            # 1. API 요청 생성 및 실행
            search_data = create_basic_search_request(grade, part, enhancement_level)
            
            # 페이지 수 확인을 위한 첫 요청
            results = await self.requester.process_requests([search_data])
            if not results[0]:
                print(f"Failed to get initial data for {grade} {part} +{enhancement_level}연마")
                return 0
                
            total_count = results[0].get('TotalCount', 0)
            total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
            print(f"{grade} {part} {enhancement_level}연마: {total_count} items ({total_pages} pages)")

            # 2. 모든 페이지 요청 생성 및 실행
            all_requests = [
                create_basic_search_request(grade, part, enhancement_level, page_no=page)
                for page in range(1, total_pages + 1)
            ]

            # 3. 요청 처리와 동시에 데이터 수집
            results = await self.requester.process_requests(all_requests)
            all_raw_items = []
            
            for result in results:
                if result and not isinstance(result, Exception):
                    data = result
                    if data.get("Items"):
                        search_timestamp = result.get('search_timestamp')
                        valid_items = [
                            (item, search_timestamp) for item in data["Items"]
                            if item["AuctionInfo"]["BuyPrice"] and item["GradeQuality"] >= 67
                        ]
                        all_raw_items.extend(valid_items)

            # 4. 데이터 저장 (요청과 병렬로 처리됨)
            if all_raw_items:
                print(f"Processing {grade} {part} {enhancement_level}연마 {len(all_raw_items)} items...")
                stats = await self.db.bulk_save_accessories(all_raw_items)
                print(f"Stats: {stats['total_items']} total, {stats['existing_updated']} updated, {stats['new_items_added']} new")
                return stats['new_items_added']
            else:
                return 0
                
        except Exception as e:
            print(f"Error collecting {grade} {part} {enhancement_level}연마: {e}")
            return 0

    async def _collect_and_save_bracelet_data(self, grade: str, fixed_slots: int, extra_slots: int) -> int:
        """팔찌 데이터 수집과 저장을 하나의 파이프라인으로 처리"""
        try:
            # 1. API 요청 생성 및 실행
            search_data = create_basic_search_request(grade, "팔찌")
            search_data["EtcOptions"] = [
                add_search_option("팔찌 옵션 수량", "고정 효과 수량", fixed_slots),
                add_search_option("팔찌 옵션 수량", "부여 효과 수량", extra_slots)
            ]
            
            # 페이지 수 확인을 위한 첫 요청
            results = await self.requester.process_requests([search_data])
            if not results[0]:
                print(f"Failed to get initial data for {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여")
                return 0
                
            total_count = results[0].get('TotalCount', 0)
            total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
            print(f"{grade} 팔찌 {fixed_slots}고정 {extra_slots}부여: {total_count} items ({total_pages} pages)")

            # 2. 모든 페이지 요청 생성 및 실행
            bracelet_etc_options = [
                add_search_option("팔찌 옵션 수량", "고정 효과 수량", fixed_slots),
                add_search_option("팔찌 옵션 수량", "부여 효과 수량", extra_slots)
            ]
            
            all_requests = []
            for page in range(1, total_pages + 1):
                search_data = create_basic_search_request(grade, "팔찌", page_no=page)
                search_data["EtcOptions"] = bracelet_etc_options
                all_requests.append(search_data)

            # 3. 요청 처리와 동시에 데이터 수집
            results = await self.requester.process_requests(all_requests)
            all_raw_items = []
            
            for result in results:
                if result and not isinstance(result, Exception):
                    data = result
                    if data.get("Items"):
                        search_timestamp = result.get('search_timestamp')
                        valid_items = [
                            (item, search_timestamp) for item in data["Items"]
                            if item["AuctionInfo"]["BuyPrice"]
                        ]
                        all_raw_items.extend(valid_items)

            # 4. 데이터 저장 (요청과 병렬로 처리됨)
            if all_raw_items:
                print(f"Processing {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여 {len(all_raw_items)} items...")
                stats = await self.db.bulk_save_bracelets(all_raw_items)
                print(f"Stats: {stats['total_items']} total, {stats['existing_updated']} updated, {stats['new_items_added']} new")
                return stats['new_items_added']
            else:
                return 0
                
        except Exception as e:
            print(f"Error collecting {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여: {e}")
            return 0


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='로스트아크 가격 수집기')
    parser.add_argument('--immediate', action='store_true', 
                       help='즉시 첫 번째 가격 수집 실행')
    parser.add_argument('--once', action='store_true',
                       help='한 번만 실행 후 종료')
    args = parser.parse_args()
    
    db_manager = RawDatabaseManager()   
    collector = AsyncPriceCollector(db_manager, tokens=config.price_tokens)
    await collector.run(immediate=args.immediate, once=args.once)

if __name__ == "__main__":
    asyncio.run(main())