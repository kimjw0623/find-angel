from typing import Dict, Optional, List
import asyncio
from datetime import datetime, timedelta
from src.api.async_api_client import TokenBatchRequester
from src.common.utils import create_auction_search_data
from src.common.config import config
from src.core.item_evaluator import ItemEvaluator
from src.common.ipc_utils import IPCServer, MessageTypes, get_ipc_client


class AsyncMarketScanner:
    def __init__(self, evaluator, tokens: List[str]):
        self.evaluator = evaluator
        self.requester = TokenBatchRequester(tokens)
        
        # Config에서 설정값 로드
        self.settings = config.item_checker_settings
        
        # 마지막 체크 시간 초기화
        self.last_expireDate_3day = None
        self.last_expireDate_1day = None
        self.last_page_index_1day = None
        self._initial_1day_page_found = False
    
    def _log_valuable_item(self, item: Dict, evaluation: Dict):
        """가치 있는 아이템 로깅 (20,000골드 이상) - systemd가 stdout 처리"""
        current_price = evaluation.get('current_price', 0)
        expected_price = evaluation.get('expected_price', 0)
        
        # 20,000골드 이상일 때만 로깅
        if current_price >= 20000 or expected_price >= 20000:
            log_message = self._format_item_message(item, evaluation)
            print(f"{log_message}")
        
    async def scan_market(self):
        """시장 스캔 지속 실행"""
        scan_interval = self.settings["scan_interval_seconds"]
        
        while True:
            try:
                # 3일 만료와 1일 만료 매물 스캔을 동시에 실행
                await asyncio.gather(
                    self._scan_items(days=3),
                    self._scan_items(days=1)
                )
                await asyncio.sleep(scan_interval)
            except Exception as e:
                print(f"Error in market scan: {e}")
                await asyncio.sleep(5)

    async def _find_initial_1day_page_index(self) -> int:
        """1일 매물 구간의 초기 페이지 인덱스를 동적으로 찾기"""
        try:
            current_time = datetime.now()
            # 24시간 근처 (23~25시간) 매물을 찾는다
            target_time_min = current_time + timedelta(hours=23)
            target_time_max = current_time + timedelta(hours=25)
            
            print(f"Finding 1-day item page index... Target remaining time: 23h ~ 25h")
            
            page = 1
            step = 20
            max_pages = 1000  # 안전장치
            
            while page <= max_pages:
                # 현재 페이지 스캔
                search_data = create_auction_search_data(page)
                responses = await self.requester.process_requests([search_data])
                
                if not responses or not responses[0] or not responses[0].get("Items"):
                    page += step
                    continue
                
                items = responses[0]["Items"]
                
                # 첫 번째와 마지막 아이템의 시간 확인
                if items:
                    first_end_time = datetime.fromisoformat(items[0]["AuctionInfo"]["EndDate"])
                    last_end_time = datetime.fromisoformat(items[-1]["AuctionInfo"]["EndDate"])
                    
                    # 남은 시간 계산 (시간 단위)
                    first_remaining_hours = (first_end_time - current_time).total_seconds() / 3600
                    last_remaining_hours = (last_end_time - current_time).total_seconds() / 3600
                    
                    print(f"Page {page}: {first_remaining_hours:.1f}h ~ {last_remaining_hours:.1f}h remaining")
                    
                    # 24시간 구간이 이 페이지에 포함되어 있는지 확인
                    if (first_end_time >= target_time_min and last_end_time <= target_time_max) or \
                       (first_end_time <= target_time_max and last_end_time >= target_time_min):
                        print(f"Found 1-day item zone at page {page}")
                        return page
                    
                    # 아직 24시간 구간에 도달하지 못함 (너무 앞쪽)
                    if last_end_time > target_time_max:
                        page += step
                    # 24시간 구간을 지나쳤음 (너무 뒤쪽)
                    elif first_end_time < target_time_min:
                        if step > 1:
                            # 뒤로 돌아가서 스텝을 줄여 정밀 탐색
                            page = max(1, page - step)
                            step = max(1, step // 2)
                        else:
                            break
                    else:
                        page += step
                else:
                    page += step
            
            print(f"Could not find 1-day item zone, using default page {self.settings['start_page_1day']}")
            return self.settings["start_page_1day"]
            
        except Exception as e:
            print(f"Error finding 1-day page index: {e}")
            return self.settings["start_page_1day"]

    async def _scan_items(self, days: int):
            """매물 스캔 및 실시간 평가 - 배치 처리 방식"""
            current_time = datetime.now()
            count = 0

            # 1일/3일 매물 구분에 따른 초기화
            if days == 3:
                if not self.last_expireDate_3day:
                    offset_minutes = self.settings["time_offsets"]["expire_3day_offset_minutes"]
                    self.last_expireDate_3day = (
                        current_time + timedelta(days=3) - timedelta(minutes=offset_minutes)
                    )
                last_expireDate = self.last_expireDate_3day
                start_page = 1
                batch_size = self.settings["batch_size_3day"]
            else:  # 1일 매물
                current_expireDate = current_time + timedelta(days=1)
                if not self.last_expireDate_1day:
                    offset_minutes = self.settings["time_offsets"]["expire_1day_offset_minutes"]
                    self.last_expireDate_1day = current_expireDate - timedelta(minutes=offset_minutes)
                if not self.last_page_index_1day:
                    if not self._initial_1day_page_found:
                        self.last_page_index_1day = await self._find_initial_1day_page_index()
                        self._initial_1day_page_found = True
                    else:
                        self.last_page_index_1day = self.settings["start_page_1day"]
                
                # 이전 페이지 인덱스 기준으로 시작
                batch_size = self.settings["batch_size_1day"]
                start_page = max(1, self.last_page_index_1day - batch_size)
                last_expireDate = self.last_expireDate_1day

            next_expire_date = None
            next_last_page_index_1day = None

            while True:
                try:
                    # 배치 요청 생성
                    batch_requests = [
                        create_auction_search_data(p) 
                        for p in range(start_page, start_page + batch_size)
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
                                # print(f"첫 템 정해짐: {end_time}이 1일차 검색의 다음 expire_date, 현재 시간과 차이 {(datetime.now() + timedelta(days=1) - end_time).total_seconds():.3f}")
                                next_last_page_index_1day = current_page
                            
                            if end_time <= last_expireDate:
                                if days == 1:
                                    self.last_page_index_1day = next_last_page_index_1day
                                    self.last_expireDate_1day = next_expire_date
                                    # print(f"1일차 검색: {count}개 아이템 검색됨")
                                if days == 3:
                                    self.last_expireDate_3day = next_expire_date
                                return
                            
                            count += 1
                            evaluation = self.evaluator.evaluate_item(item)
                            if evaluation:
                                # 가치 있는 아이템 로깅 (20,000골드 이상)
                                self._log_valuable_item(item, evaluation)
                                # formatted_message = self._format_item_message(item, evaluation)
                                # await self._send_to_notification_hub(item, evaluation, formatted_message)

                    # 다음 배치로 이동
                    start_page += batch_size

                except Exception as e:
                    print(f"Error scanning pages {start_page}-{start_page + batch_size - 1}: {e}")
                    break

    async def _send_to_notification_hub(self, item: Dict, evaluation: Dict, formatted_message: str):
        """notification hub로 매물 발견 알림 전송"""
        try:
            # notification_hub에게 알림 전송
            client = get_ipc_client("notification_hub")
            client.send_notification(
                MessageTypes.ITEM_FOUND,
                {
                    'item': item,
                    'evaluation': evaluation,
                    'formatted_message': formatted_message,
                    'timestamp': datetime.now().isoformat()
                }
            )
        except Exception as e:
            print(f"Failed to send notification to hub: {e}")
            # notification hub가 실행 중이지 않을 수 있음
            print(f"Make sure notification hub is running: ./scripts/run_notification_hub.sh")

    
    
    def _format_item_message(self, item: Dict, evaluation: Dict) -> str:
        """아이템 메시지 포맷팅 (간단한 텍스트 형태)"""
        try:
            # 옵션 문자열 생성 (힘민지 개선)
            options_list = []
            base_stat_names = ["힘", "민첩", "지능"]
            base_stat_value = None
            
            # 먼저 힘민지 값 찾기
            for opt in item["Options"]:
                if opt["OptionName"] in base_stat_names:
                    base_stat_value = opt["Value"]
                    break  # 첫 번째로 찾은 값 사용
            
            # 힘민지 옵션 추가
            if base_stat_value is not None:
                options_list.append(f"힘민지{base_stat_value}")
            
            # 다른 옵션들 추가 (힘민지 제외)
            for opt in item["Options"]:
                if opt["OptionName"] in ["깨달음", "도약"] or opt["OptionName"] in base_stat_names:
                    continue
                options_list.append(f"{opt['OptionName']}{opt['Value']}")
            
            options_str = ' '.join(options_list)
            
            end_date = item["AuctionInfo"]["EndDate"]
            
            if evaluation["type"] == "accessory":
                # 패턴 정보는 이제 evaluation에 포함됨
                dealer_key_short = evaluation.get('dealer_pattern_key', '').split(':')[-1]
                support_key_short = evaluation.get('support_pattern_key', '').split(':')[-1]
                model_info = evaluation.get('model_info', 'none')
                
                pattern_info = (f"D[{dealer_key_short}]:{evaluation['dealer_price']:,} | "
                              f"S[{support_key_short}]:{evaluation['support_price']:,} | "
                              f"USE[{evaluation['usage_type']}] | MODEL[{model_info}]")
                
                return (f"{evaluation['grade']} {item['Name']} | "
                    f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
                    f"({evaluation['price_ratio']*100:.1f}%) | "
                    f"{evaluation['level']}연마 | "
                    f"만료 {end_date} | "
                    f"{options_str} | "
                    f"거래 {item['AuctionInfo']['TradeAllowCount']}회 | "
                    f"{pattern_info}")
            else:  # 팔찌
                return (f"{evaluation['grade']} {item['Name']} | "
                    f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
                    f"({evaluation['price_ratio']*100:.1f}%) | "
                    f"부여 {int(evaluation.get('extra_option_count', 0))} | "
                    f"만료 {end_date} | "
                    f"{options_str}")
                    
        except Exception as e:
            print(f"Error formatting item message: {e}")
            return f"매물 발견: {item.get('Name', 'Unknown')} - {evaluation.get('current_price', 0):,}골드"

class AsyncMarketMonitor:
    def __init__(self, tokens: List[str]):
        # 로컬 evaluator 초기화
        evaluator = ItemEvaluator()
        
        self.scanner = AsyncMarketScanner(evaluator, tokens)
        
        # IPC 서버 설정
        self.ipc_server = IPCServer(service_name="item_checker")
        self._setup_ipc_handlers()
        
    def _setup_ipc_handlers(self):
        """IPC 메시지 핸들러 등록"""
        # 패턴 업데이트 알림 핸들러
        self.ipc_server.register_handler(
            MessageTypes.PATTERN_UPDATED,
            self._handle_pattern_update
        )
        
        # 플레이어 데이터 업데이트 핸들러 (notification_hub에서)
        self.ipc_server.register_handler(
            MessageTypes.PLAYER_DATA_UPDATE,  # 새로운 메시지 타입 필요
            self._handle_player_data_update
        )
        
    def _handle_pattern_update(self, data: Dict):
        """패턴 업데이트 처리"""
        try:
            pattern_datetime = data.get('pattern_datetime')
            print(f"Pattern updated at {pattern_datetime} - refreshing evaluator cache")
            # ItemEvaluator의 패턴 캐시 갱신
            if hasattr(self.scanner.evaluator, 'refresh_patterns'):
                self.scanner.evaluator.refresh_patterns()
        except Exception as e:
            print(f"Error handling pattern update: {e}")
            
    def _handle_player_data_update(self, data: Dict):
        """플레이어 데이터 업데이트 처리"""
        try:
            # 향후 플레이어 선호도/행동 데이터 업데이트 로직
            print(f"Player data updated: {data}")
        except Exception as e:
            print(f"Error handling player data update: {e}")

    async def run(self):
        """비동기 모니터링 실행 (IPC 서버와 함께)"""
        print(f"Starting market monitoring at {datetime.now()}")
        print("IPC Server enabled - listening for pattern updates")
        
        # IPC 서버 시작 (동기 방식)
        self.ipc_server.start_server()
        
        try:
            # 스캔은 scan_market() 내부에서 지속적으로 실행됨
            await self.scanner.scan_market()
        except KeyboardInterrupt:
            print("\nStopping market monitoring...")
        except Exception as e:
            print(f"Fatal error in monitoring: {e}")
        finally:
            # IPC 서버 정리
            # IPC 서버는 동기 방식이므로 stop 메소드가 없음
            pass

async def main():
    try:
        monitor = AsyncMarketMonitor(tokens=config.monitor_tokens)
        
        print("Item Checker Starting...")
        print("IPC Server: Listening for pattern updates")
        print("Notifications: Sending to notification hub via IPC")
        print("Make sure notification hub is running: ./scripts/run_notification_hub.sh")

        await monitor.run()

    except KeyboardInterrupt:
        print("\nStopping monitoring...")
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())