from typing import List
from datetime import datetime, timedelta
import asyncio
from src.api.async_api_client import TokenBatchRequester
from src.database.raw_database import *
from src.common.utils import *
from src.common.config import config
from src.common.ipc_utils import notify_collection_completed

class AsyncPriceCollector:
    def __init__(self, db_manager: RawDatabaseManager, tokens: List[str]):
        self.db = db_manager
        self.requester = TokenBatchRequester(tokens)
        self.ITEMS_PER_PAGE = config.items_per_page
        
    async def run(self, immediate=False, once=False, noupdate=False):
        """메인 실행 함수"""
        first_run = True
        
        while True:
            try:
                # 첫 실행시 immediate 옵션 확인
                if first_run and immediate:
                    print("즉시 가격 수집을 시작합니다...")
                elif not first_run:
                    # 수집 완료 후 고정 간격 대기
                    wait_minutes = config.time_settings.get("price_collection_interval_minutes", 2)
                    wait_seconds = wait_minutes * 60
                    print(f"{wait_minutes}분 대기 후 다음 수집을 시작합니다...")
                    await asyncio.sleep(wait_seconds)

                # 가격 수집 실행                
                collection_end_time = await self.collect_prices()
                
                # IPC 신호 발송 (패턴 생성 요청)
                if not noupdate:
                    print(f"\n📡 Sending collection completion signal to pattern generator...")
                    result = notify_collection_completed(collection_end_time)
                    if result:
                        print(f"Signal sent successfully")
                    else:
                        print(f"No pattern generator service listening (this is normal if running standalone)")
                else:
                    print(f"Pattern generation skipped (noupdate=True)")
                
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
        """비동기 가격 수집 (순차 처리)"""
        try:            
            start_time = datetime.now()
            print(f"Starting price collection at {start_time}")
            
            # 수집 시작 시간을 DB에 전달하기 위해 저장
            self.collection_start_time = start_time
            # 장신구 수집 준비
            grades = ["고대", "유물"]
            accessory_parts = ["목걸이", "귀걸이", "반지"]
            enhancement_levels = [0, 1, 2, 3]
            fixed_slots_list = [1, 2]
            extra_slots_list = [1, 2]
            
            # 순차적으로 데이터 수집 실행
            total_tasks = len(grades) * len(accessory_parts) * len(enhancement_levels) + len(grades) * len(fixed_slots_list) * len(extra_slots_list)
            print(f"Starting {total_tasks} collection tasks sequentially...")
            
            results = []
            task_count = 0
            
            for grade in grades:
                # 1. 목걸이/귀걸이/반지 순차 수집
                for part in accessory_parts:
                    for enhancement_level in enhancement_levels:
                        task_count += 1
                        print(f"[{task_count:>2}/{total_tasks:>2}] Collecting {grade} {part:>4} {enhancement_level}연마", end='')
                        try:
                            result = await self._collect_and_save_accessory_data(grade, part, enhancement_level)
                            results.append(result)
                        except Exception as e:
                            print(f" - Failed: {e}")
                            results.append(e)
                
                # 2. 팔찌 순차 수집
                bonus_slots = 1 if grade == "고대" else 0
                for fixed_slots in fixed_slots_list:
                    for extra_slots in extra_slots_list:
                        task_count += 1
                        total_slots = extra_slots + bonus_slots
                        print(f"[{task_count}/{total_tasks}] Collecting {grade} {'팔찌':>4} {fixed_slots}고정+{total_slots}부여", end='')
                        try:
                            result = await self._collect_and_save_bracelet_data(grade, fixed_slots, total_slots)
                            results.append(result)
                        except Exception as e:
                            print(f" - Failed: {e}")
                            results.append(e)
            
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
            
            # 사라진 아이템들의 상태 업데이트 (수집 시작 시간 전달)
            print("\nUpdating status for missing items...")
            update_stats = await self.db.update_missing_items_status(self.collection_start_time)
            print(f"Updated item status - SOLD: {update_stats['sold']}, EXPIRED: {update_stats['expired']}")
            
            end_time = datetime.now()
            duration = end_time - start_time
            print(f"Completed price collection at {end_time}")
            print(f"Duration: {duration}")
            
            return end_time  # 완료 시간 반환
                
        except Exception as e:
            print(f"Error in price collection: {e}")
            import traceback
            traceback.print_exc()
            return datetime.now()  # 오류 발생 시에도 현재 시간 반환

    # 더 이상 사용하지 않는 메서드 (2분 고정 간격으로 변경)
    # def _get_next_run_time(self) -> datetime:
    #     """Calculate the next run time (every 10 minutes)"""

    async def _collect_and_save_accessory_data(self, grade: str, part: str, enhancement_level: int) -> int:
        """악세서리 데이터 수집과 저장을 하나의 파이프라인으로 처리"""
        try:
            # 1. API 요청 생성 및 실행
            search_data = create_basic_search_request(grade, part, enhancement_level)
            
            # 페이지 수 확인을 위한 첫 요청
            results = await self.requester.process_requests([search_data])
            if not results[0]:
                print(f"Failed to get initial data for {grade} {part:>4} +{enhancement_level}연마")
                return 0
                
            total_count = results[0].get('TotalCount', 0)
            total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
            print(f": {total_count:>5} items ({total_pages:>4} pages)...", end='', flush=True)

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
                stats = await self.db.bulk_save_accessories(all_raw_items)
                print(f"{len(all_raw_items):>5} valid total, {stats['existing_updated']:>5} updated, {stats['new_items_added']:>5} new")
                return stats['new_items_added']
            else:
                print(f"0 valid total, 0 updated, 0 new")
                return 0
                
        except Exception as e:
            print(f" - Error: {e}")
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
            print(f": {total_count:>5} items ({total_pages:>4} pages)...", end='', flush=True)

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
                stats = await self.db.bulk_save_bracelets(all_raw_items)
                print(f"{len(all_raw_items):>5} valid total, {stats['existing_updated']:>5} updated, {stats['new_items_added']:>5} new")
                return stats['new_items_added']
            else:
                print(f"0 valid total, 0 updated, 0 new")
                return 0
                
        except Exception as e:
            print(f" - Error: {e}")
            return 0


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='로스트아크 가격 수집기')
    parser.add_argument('--immediate', action='store_true', 
                       help='즉시 첫 번째 가격 수집 실행')
    parser.add_argument('--once', action='store_true',
                       help='한 번만 실행 후 종료')
    parser.add_argument('--noupdate', action='store_true',
                       help='패턴 업데이트 하지 않음')
    args = parser.parse_args()
    
    db_manager = RawDatabaseManager()   
    collector = AsyncPriceCollector(db_manager, tokens=config.price_tokens)
    await collector.run(immediate=args.immediate, once=args.once, noupdate=args.noupdate)

if __name__ == "__main__":
    asyncio.run(main())