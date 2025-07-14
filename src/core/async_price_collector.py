from typing import List
from datetime import datetime, timedelta
import asyncio
from src.api.async_api_client import TokenBatchRequester
from src.core.price_pattern_analyzer import PricePatternAnalyzer
from src.database.raw_database import *
from src.common.utils import *
from src.common.config import config
from src.common.utils import create_basic_search_request, add_search_option

def _create_acc_hash_key(item_data: dict) -> tuple:
    """악세서리 아이템의 해시 키 생성"""
    # 기본 속성으로 키 구성
    base_key = (
        item_data['grade'],
        item_data['name'],
        item_data['part'],
        item_data['level'],
        item_data['quality'],
        item_data['price'],
        item_data['trade_count']
    )
    
    # 옵션들을 정렬하여 튜플로 변환
    options_key = tuple(sorted(
        (opt[0], opt[1]) for opt in item_data['options']
    ))
    
    return base_key + (options_key,)

def _create_bracelet_hash_key(item_data: dict) -> tuple:
    """팔찌 아이템의 해시 키 생성"""
    # 기본 속성으로 키 구성
    base_key = (
        item_data['grade'],
        item_data['name'],
        item_data['price'],
        item_data['trade_count'],
        item_data['fixed_option_count'],
        item_data['extra_option_count']
    )
    
    # 각 옵션 타입별로 정렬된 튜플 생성
    combat_stats = tuple(sorted(
        (stat['stat_type'], stat['value'])
        for stat in item_data['combat_stats']
    ))
    
    base_stats = tuple(sorted(
        (stat['stat_type'], stat['value'])
        for stat in item_data['base_stats']
    ))
    
    special_effects = tuple(sorted(
        (effect['effect_type'], effect['value'])
        for effect in item_data['special_effects']
    ))
    
    return base_key + (combat_stats, base_stats, special_effects)

class AsyncPriceCollector:
    def __init__(self, db_manager: RawDatabaseManager, tokens: List[str]):
        self.db = db_manager
        self.analyzer = PricePatternAnalyzer(self.db)
        self.requester = TokenBatchRequester(tokens)
        self.current_cycle_id = None
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
        """비동기 가격 수집"""
        try:
            self.current_cycle_id = datetime.now().strftime("%Y%m%d_%H%M")
            total_collected = 0

            # 장신구 수집 준비
            grades = ["고대", "유물"]
            accessory_parts = ["목걸이", "귀걸이", "반지"]
            enhancement_levels = [0, 1, 2, 3]
            fixed_slots_list = [1, 2]
            extra_slots_list = [1, 2]
            
            for grade in grades:
                # 1. 목걸이/귀걸이/반지 수집 (연마 단계별)
                for part in accessory_parts:
                    for enhancement_level in enhancement_levels:
                        collected = await self._collect_accessory_data(grade, part, enhancement_level)
                        total_collected += collected
                
                # 2. 팔찌 수집 (고정/부여 효과 수량별)
                bonus_slots = 1 if grade == "고대" else 0
                for fixed_slots in fixed_slots_list:
                    for extra_slots in extra_slots_list:
                        collected = await self._collect_bracelet_data(grade, fixed_slots, extra_slots + bonus_slots)
                        total_collected += collected

            print(f"Total collected items: {total_collected}")
            
            if total_collected > 0:
                # 캐시 업데이트
                self.analyzer.update_pattern(self.current_cycle_id)
                print(f"Pattern updated at {datetime.now()}")
                
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

        # 4. 결과 일괄 처리
        all_processed_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                processed_items = self.process_acc_response(result, grade, part, enhancement_level)
                if processed_items:
                    all_processed_items.extend(processed_items)

        # 5. 일괄 저장
        if all_processed_items:
            print(f"Saving {grade} {part} {enhancement_level}연마 {len(all_processed_items)} items...")
            duplicate_count = await self.save_acc_items(all_processed_items, self.current_cycle_id)
            total_collected = len(all_processed_items) - duplicate_count
            print(f"Saved {total_collected} unique items after removing {duplicate_count} duplicates")

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

        # 4. 결과 일괄 처리
        all_processed_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                processed_items = self.process_bracelet_response(result, grade, fixed_slots, extra_slots)
                if processed_items:
                    all_processed_items.extend(processed_items)

        # 5. 일괄 저장
        if all_processed_items:
            print(f"Saving {grade} 팔찌 {fixed_slots}고정 {extra_slots}부여 {len(all_processed_items)} items...")
            duplicate_count = await self.save_bracelet_items(all_processed_items, self.current_cycle_id)
            total_collected = len(all_processed_items) - duplicate_count
            print(f"Saved {total_collected} unique items after removing {duplicate_count} duplicates")

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

    def process_acc_response(self, response, grade, part, enhancement_level):
        """API 응답 처리 및 DB 저장"""
        data = response
        if not data["Items"]:
            return None

        # 유효한 아이템 필터링: 즉구가 있고 품질 67 이상인 것만
        valid_items = [
            item for item in data["Items"]
            if item["AuctionInfo"]["BuyPrice"] and item["GradeQuality"] >= 67
        ]
        if not valid_items:
            return None

        processed_items = []
        search_timestamp = response.get('search_timestamp', datetime.now())  # API 응답에서 timestamp 추출

        for item in valid_items:
            processed_item = {
                'search_timestamp': search_timestamp,
                'name': item["Name"],
                'grade': grade,
                'part': part,
                'level': len(item["Options"]) - 1,
                'quality': item["GradeQuality"],
                'trade_count': item["AuctionInfo"]["TradeAllowCount"],
                'price': item["AuctionInfo"]["BuyPrice"],
                'end_time': datetime.strptime(
                    item["AuctionInfo"]["EndDate"].split('.')[0],
                    "%Y-%m-%dT%H:%M:%S"
                ),
                'options': [],
                'raw_options': []
            }

            # 옵션 처리
            fix_dup_options(item)
            for option in item["Options"]:
                if option["OptionName"] not in ["깨달음", "도약"]:
                    opt_value = option["Value"]
                    # raw option 저장
                    processed_item['raw_options'].append({
                        'option_name': option["OptionName"],
                        'option_value': opt_value,
                        'is_percentage': option.get("IsValuePercentage", False)
                    })
                    # 가공된 option 저장
                    opt_grade = number_to_scale.get(
                        option["OptionName"], {}).get(opt_value, 1)
                    processed_item['options'].append(
                        (option["OptionName"], opt_grade))

            processed_items.append(processed_item)

        return processed_items

    def process_bracelet_response(self, response, grade, fixed_slots, extra_slots):
        """팔찌 API 응답 처리"""
        data = response
        if not data["Items"]:
            return None

        # 유효한 아이템 필터링 (팔찌는 품질 체크 필요 없음)
        valid_items = [
            item for item in data["Items"]
            if item["AuctionInfo"]["BuyPrice"]
        ]
        if not valid_items:
            return None

        processed_items = []
        search_timestamp = response.get('search_timestamp', datetime.now())  # API 응답에서 timestamp 추출

        for item in valid_items:
            # 기본 정보 처리
            processed_item = {
                'search_timestamp': search_timestamp,
                'grade': grade,
                'name': item["Name"],
                'trade_count': item["AuctionInfo"]["TradeAllowCount"],
                'price': item["AuctionInfo"]["BuyPrice"],
                'end_time': datetime.strptime(
                    item["AuctionInfo"]["EndDate"].split('.')[0],
                    "%Y-%m-%dT%H:%M:%S"
                ),
                'combat_stats': [],
                'base_stats': [],
                'special_effects': [],
                'fixed_option_count': 0,  # 기본값 설정
                'extra_option_count': 0   # 기본값 설정
            }

            # 옵션 처리
            for option in item["Options"]:
                option_type = option["Type"]
                option_name = option["OptionName"]
                value = option["Value"]

                # 고정 효과 수량은 전체 옵션 개수에서 도약 값과 부여 효과 수량, 즉 2를 뺀 값
                processed_item['fixed_option_count'] = len(item["Options"]) - 2
                if option_type == "ARK_PASSIVE":    # 도약 포인트는 필요 없음
                    continue
                # 부여 효과 수량 체크
                if option_type == "BRACELET_RANDOM_SLOT":
                    processed_item['extra_option_count'] = value
                # 전투특성 처리
                elif option_type == "STAT" and option_name in ["특화", "치명", "신속"]:
                    processed_item['combat_stats'].append({
                        'stat_type': option_name,
                        'value': value
                    })
                # 기본스탯 처리
                elif option_type == "STAT" and option_name in ["힘", "민첩", "지능"]:
                    processed_item['base_stats'].append({
                        'stat_type': option_name,
                        'value': value
                    })
                # 특수효과 처리(제인숙, 체력 등등 그 외 모든 건 다 여기에 들어감)
                else:
                    processed_item['special_effects'].append({
                        'effect_type': option_name,
                        'value': value
                    })

            processed_items.append(processed_item)

        return processed_items

    async def save_acc_items(self, items, search_cycle_id):
        """기존 save_acc_items 메서드를 비동기 컨텍스트에서 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_save_acc_items, items, search_cycle_id)

    async def save_bracelet_items(self, items, search_cycle_id):
        """기존 save_bracelet_items 메서드를 비동기 컨텍스트에서 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_save_bracelet_items, items, search_cycle_id)

    def _sync_save_acc_items(self, items: List[dict], search_cycle_id: str) -> int:
        """개선된 악세서리 아이템 저장"""
        # 1. 메모리 내 중복 제거
        unique_items = {}
        for item in items:
            item_key = _create_acc_hash_key(item)
            # 같은 키의 아이템 중 가장 최근 것만 유지
            if item_key not in unique_items or item['search_timestamp'] > unique_items[item_key]['search_timestamp']:
                unique_items[item_key] = item
        
        # 2. DB에 일괄 저장
        with self.db.get_write_session() as session:
            saved_count = 0
            for item_data in unique_items.values():
                record = PriceRecord(
                    timestamp=item_data['search_timestamp'],
                    search_cycle_id=search_cycle_id,
                    grade=item_data['grade'],
                    name=item_data['name'],
                    part=item_data['part'],
                    level=item_data['level'],
                    quality=item_data['quality'],
                    trade_count=item_data['trade_count'],
                    price=item_data['price'],
                    end_time=item_data['end_time'],
                    damage_increment=item_data.get('damage_increment')
                )
                
                # 옵션 추가
                for opt_name, opt_grade in item_data['options']:
                    option = ItemOption(
                        option_name=opt_name,
                        option_grade=opt_grade
                    )
                    record.options.append(option)
                
                # 원본 옵션 추가
                for raw_opt in item_data['raw_options']:
                    raw_option = RawItemOption(
                        option_name=raw_opt['option_name'],
                        option_value=raw_opt['option_value'],
                        is_percentage=raw_opt['is_percentage']
                    )
                    record.raw_options.append(raw_option)
                
                session.add(record)
                saved_count += 1
            
            session.flush()
            
            # 중복 제거된 수 반환
            return len(items) - saved_count

    def _sync_save_bracelet_items(self, items: List[dict], search_cycle_id: str) -> int:
        """개선된 팔찌 아이템 저장"""
        # 1. 메모리 내 중복 제거
        unique_items = {}
        for item in items:
            item_key = _create_bracelet_hash_key(item)
            # 같은 키의 아이템 중 가장 최근 것만 유지
            if item_key not in unique_items or item['search_timestamp'] > unique_items[item_key]['search_timestamp']:
                unique_items[item_key] = item
        
        # 2. DB에 일괄 저장
        with self.db.get_write_session() as session:
            saved_count = 0
            for item_data in unique_items.values():
                record = BraceletPriceRecord(
                    timestamp=item_data['search_timestamp'],
                    search_cycle_id=search_cycle_id,
                    grade=item_data['grade'],
                    name=item_data['name'],
                    trade_count=item_data['trade_count'],
                    price=item_data['price'],
                    end_time=item_data['end_time'],
                    fixed_option_count=item_data['fixed_option_count'],
                    extra_option_count=item_data['extra_option_count']
                )
                
                # 전투특성 추가
                for stat in item_data['combat_stats']:
                    combat_stat = BraceletCombatStat(
                        stat_type=stat['stat_type'],
                        value=stat['value']
                    )
                    record.combat_stats.append(combat_stat)
                
                # 기본스탯 추가
                for stat in item_data['base_stats']:
                    base_stat = BraceletBaseStat(
                        stat_type=stat['stat_type'],
                        value=stat['value']
                    )
                    record.base_stats.append(base_stat)
                
                # 특수효과 추가
                for effect in item_data['special_effects']:
                    special_effect = BraceletSpecialEffect(
                        effect_type=effect['effect_type'],
                        value=effect['value']
                    )
                    record.special_effects.append(special_effect)
                
                session.add(record)
                saved_count += 1
            
            session.flush()
            
            # 중복 제거된 수 반환
            return len(items) - saved_count

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