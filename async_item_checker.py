from typing import Dict, Optional, List
import asyncio
from datetime import datetime, timedelta
from async_api_client import TokenBatchRequester
from database import DatabaseManager
from market_price_cache import MarketPriceCache
from discord_manager import send_discord_message, init_discord_manager
import multiprocessing as mp
from utils import *
from config import config
import os
from item_evaluator import ItemEvaluator
from dotenv import load_dotenv


class AsyncMarketScanner:
    def __init__(self, evaluator, tokens: List[str], msg_queue: mp.Queue):
        self.evaluator = evaluator
        self.requester = TokenBatchRequester(tokens)
        self.webhook = os.getenv("WEBHOOK1")
        self.msg_queue = msg_queue
        
        # 마지막 체크 시간 초기화
        self.last_expireDate_3day = None
        self.last_expireDate_1day = None
        self.last_page_index_1day = None
        
    async def scan_market(self):
        """시장 스캔 실행"""
        try:
            # 3일 만료와 1일 만료 매물 스캔을 동시에 실행
            await asyncio.gather(
                self._scan_items(days=3),
                self._scan_items(days=1)
            )
        except Exception as e:
            print(f"Error in market scan: {e}")

    async def _scan_items(self, days: int):
            """매물 스캔 및 실시간 평가 - 배치 처리 방식"""
            current_time = datetime.now()
            count = 0
            BATCH_SIZE = 5

            # 1일/3일 매물 구분에 따른 초기화
            if days == 3:
                if not self.last_expireDate_3day:
                    self.last_expireDate_3day = (
                        current_time + timedelta(days=3) - timedelta(minutes=3)
                    )
                last_expireDate = self.last_expireDate_3day
                start_page = 1
                BATCH_SIZE = 5  # 한 번에 처리할 페이지 수
            else:  # 1일 매물
                current_expireDate = current_time + timedelta(days=1)
                if not self.last_expireDate_1day:
                    self.last_expireDate_1day = current_expireDate - timedelta(minutes=1)
                if not self.last_page_index_1day:
                    self.last_page_index_1day = 500
                
                # 이전 페이지 인덱스 기준으로 시작
                start_page = max(1, self.last_page_index_1day - BATCH_SIZE)
                last_expireDate = self.last_expireDate_1day
                BATCH_SIZE = 10  # 한 번에 처리할 페이지 수

            next_expire_date = None
            next_last_page_index_1day = None

            while True:
                try:
                    # 배치 요청 생성
                    batch_requests = [
                        self._create_search_data(p) 
                        for p in range(start_page, start_page + BATCH_SIZE)
                    ]
                    
                    # 배치 처리
                    responses = await self.requester.process_requests(batch_requests)
                    
                    if not responses or all(not r or not r.get("Items") for r in responses):
                        break

                    # 페이지별로 처리
                    for page_offset, response in enumerate(responses):
                        if not response or not response.get("Items"):
                            continue
                            
                        current_page = start_page + page_offset
                        
                        for item in response["Items"]:
                            end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
                            
                            if days == 1 and end_time >= current_expireDate: # 아직 1일차 매물이 아님(3일차가 1일차 근처로 내려온 거임)
                                continue
                            
                            if next_expire_date is None:
                                next_expire_date = end_time
                            if days == 1 and next_last_page_index_1day is None:
                                print(f"첫 템 정해짐: {end_time}이 1일차 검색의 다음 expire_date, 현재 시간과 차이 {(datetime.now() + timedelta(days=1) - end_time).total_seconds():.3f}")
                                next_last_page_index_1day = current_page
                            
                            if end_time <= last_expireDate:
                                if days == 1:
                                    self.last_page_index_1day = next_last_page_index_1day
                                    self.last_expireDate_1day = next_expire_date
                                    print(f"1일차 검색: {count}개 아이템 검색됨")
                                if days == 3:
                                    self.last_expireDate_3day = next_expire_date
                                return
                            
                            count += 1
                            evaluation = self.evaluator.evaluate_item(item)
                            if evaluation and evaluation["is_notable"]:
                                send_discord_message(self.webhook, item, evaluation)
                                self.msg_queue.put((item, evaluation))

                    # 다음 배치로 이동
                    start_page += BATCH_SIZE

                except Exception as e:
                    print(f"Error scanning pages {start_page}-{start_page + BATCH_SIZE - 1}: {e}")
                    break

    def _create_search_data(self, page_no: int) -> Dict:
        """검색 데이터 생성"""
        return {
            "ItemLevelMin": 0,
            "ItemLevelMax": 1800,
            "ItemGradeQuality": None,
            "Sort": "EXPIREDATE",
            "CategoryCode": 200000,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": "",
            "PageNo": page_no,
            "SortCondition": "DESC",
            "EtcOptions": [
                {
                    "FirstOption": "",
                    "SecondOption": "",
                    "MinValue": "",
                    "MaxValue": "",
                },
            ],
        }

class AsyncMarketMonitor:
    def __init__(self, db_manager: DatabaseManager, msg_queue: mp.Queue, tokens: List[str], debug: bool = False):
        price_cache = MarketPriceCache(db_manager, debug=debug)
        self.evaluator = ItemEvaluator(price_cache, debug=debug)
        self.scanner = AsyncMarketScanner(self.evaluator, tokens, msg_queue)

    async def run(self):
        """비동기 모니터링 실행"""
        print(f"Starting market monitoring at {datetime.now()}")

        while True:
            try:
                await self.scanner.scan_market()
                await asyncio.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopping market monitoring...")
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)

async def main():
    try:
        db_manager = DatabaseManager()    
        msg_queue = mp.Queue()
        
        monitor = AsyncMarketMonitor(db_manager, msg_queue, tokens=config.monitor_tokens, debug=False)
        terminator = init_discord_manager(msg_queue)

        await monitor.run()

    finally:
        terminator()

if __name__ == "__main__":
    asyncio.run(main())