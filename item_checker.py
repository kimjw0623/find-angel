import os
import time
import threading
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from database import *
from utils import *
from market_price_cache import MarketPriceCache
from sqlalchemy.orm import aliased
from discord_utils import send_discord_message
from item_evaluator import ItemEvaluator
from config import config

class MarketScanner:
    def __init__(self, evaluator, tokens):
        self.evaluator = evaluator
        self.token_manager = TokenManager(tokens)
        self.webhook1 = os.getenv("WEBHOOK1")
        self.webhook2 = os.getenv("WEBHOOK2")

        # 마지막 체크 시간 초기화
        self.last_expireDate_3day = None
        self.last_expireDate_1day = None
        self.last_page_index_1day = None

    def scan_market(self):
        """시장 스캔 실행"""
        try:
            # 3일 만료 매물 스캔
            self._scan_items(days=3)
            # 1일 만료 매물 스캔
            self._scan_items(days=1)
        except Exception as e:
            print(f"Error in market scan: {e}")

    def _scan_items(self, days: int):
        """매물 스캔 및 실시간 평가"""
        current_time = datetime.now()
        # 매물 카운트
        count = 0
        # 1일/3일 매물 구분에 따른 초기화
        if days == 3:
            if not self.last_expireDate_3day:
                self.last_expireDate_3day = (
                    current_time + timedelta(days=3) - timedelta(minutes=3)
                )
            # print(f"3일 검색 시작, expire cut {self.last_expireDate_3day}")
            last_expireDate = self.last_expireDate_3day
            page_no = 1
        else:  # 1일 매물
            current_expireDate = current_time + timedelta(days=1)
            if not self.last_expireDate_1day:
                self.last_expireDate_1day = current_expireDate - timedelta(minutes=1)
            if not self.last_page_index_1day:
                self.last_page_index_1day = 747  # 초기 추정치

            # 적절한 시작 페이지 찾기
            page_no = self._find_starting_page(
                self.last_page_index_1day, current_expireDate
            )
            last_expireDate = self.last_expireDate_1day
            # print(f"1일 검색 시작, 현재 시간 {current_time}, expire cut {self.last_expireDate_1day}, starts at page {page_no}")

        # 이번 검색 사이클의 첫 매물 시간을 저장할 변수
        next_expire_date = None
        next_last_page_index_1day = None
        
        while True:
            try:
                response = self.token_manager.do_search(self._create_search_data(page_no))
                data = response.json()

                if not data["Items"]:
                    break
                
                # 각 아이템 실시간 평가
                for item in data["Items"]:                  
                    end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
                    
                    # 1일 매물인 경우 current_expireDate보다 작은지 추가 확인
                    if days == 1 and end_time >= current_expireDate:
                        continue
                    
                    # 첫 매물의 시간 저장 (아직 저장된 적 없는 경우에만)
                    if next_expire_date is None:
                        next_expire_date = end_time
                    if days == 1 and next_last_page_index_1day is None:
                        next_last_page_index_1day = page_no
                    
                    # 이전에 체크한 시간보다 이후에 등록된 매물만 확인. 즉 여기 들어오면 해당사이클의 끝
                    if end_time <= last_expireDate:
                        # 1일 매물인 경우 마지막 페이지 인덱스 업데이트
                        if days == 1:
                            self.last_page_index_1day = next_last_page_index_1day
                             # 왜인지 모르겠는데 짧은 시간 안에 같은 페이지 로드하면 그냥 같은 결과 뱉는 듯. 웹 API 업데이트가 느린 듯 함.
                            # self.last_page_index_1day = next_last_page_index_1day - 2
                        # 마지막 확인 시간 업데이트 (첫 번째 매물 시간으로)
                        if days == 3:
                            self.last_expireDate_3day = next_expire_date
                        else:
                            self.last_expireDate_1day = next_expire_date
                        # print(f"... {count}개 검색 완료")
                        return
                    
                    count += 1
                    # 즉시 평가 및 처리
                    evaluation = self.evaluator.evaluate_item(item)
                    if evaluation and evaluation["is_notable"]:
                        send_discord_message(self.webhook1, item, evaluation, url2=self.webhook2)

                page_no += 1

            except Exception as e:
                print(f"Error scanning page {page_no}: {e}")
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

    def _find_starting_page(
        self, last_page_index: int, current_expireDate: datetime
    ) -> int:
        """적절한 시작 페이지 찾기"""
        page_no = last_page_index
        response = self.token_manager.do_search(self._create_search_data(page_no))
        data = response.json()

        if not data["Items"]:
            return page_no

        first_item = data["Items"][0]
        last_item = data["Items"][-1]

        first_item_end_time = datetime.fromisoformat(first_item["AuctionInfo"]["EndDate"])
        last_item_end_time = datetime.fromisoformat(last_item["AuctionInfo"]["EndDate"])
        # Case 1: 페이지가 너무 이름 (page_no가 커져야 함)
        page_step = 1
        if (
            first_item_end_time > current_expireDate
            and last_item_end_time > current_expireDate
        ):
            while True:
                page_no += page_step
                response = self.token_manager.do_search(self._create_search_data(page_no))
                data = response.json()

                if not data["Items"]:
                    return max(1, page_no - page_step)

                last_item = data["Items"][-1]
                end_time = datetime.strptime(
                    last_item["AuctionInfo"]["EndDate"].split(".")[0],
                    "%Y-%m-%dT%H:%M:%S",
                )

                if end_time < current_expireDate:
                    return max(1, page_no - page_step)

        # Case 2: 페이지가 너무 늦음 (page_no가 작아져야 함)
        elif (
            first_item_end_time < current_expireDate
            and last_item_end_time < current_expireDate
        ):
            page_no = max(1, page_no - page_step)
            while page_no > 0:
                response = self.token_manager.do_search(self._create_search_data(page_no))
                data = response.json()

                if not data["Items"]:
                    return page_no + page_step

                last_item = data["Items"][-1]
                end_time = datetime.strptime(
                    last_item["AuctionInfo"]["EndDate"].split(".")[0],
                    "%Y-%m-%dT%H:%M:%S",
                )

                if end_time > current_expireDate:
                    return page_no

                page_no -= page_step

            return 1

        # Case 3: 현재 페이지가 적절함
        return page_no

class MarketMonitor:
    def __init__(self, db_manager, tokens, debug=False):
        price_cache = MarketPriceCache(db_manager, debug=debug)
        self.evaluator = ItemEvaluator(price_cache, debug=debug)
        self.scanner = MarketScanner(self.evaluator, tokens=tokens)

    def run(self):
        """모니터링 실행"""
        print(f"Starting market monitoring at {datetime.now()}")

        while True:
            try:
                self.scanner.scan_market()
                time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping market monitoring...")
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(5)

def main():
    db_manager = init_database()  # DatabaseManager() 대신 init_database() 사용
    monitor = MarketMonitor(db_manager, tokens=config.monitor_tokens, debug=False)
    monitor.run()

if __name__ == "__main__":  
    main()
  
