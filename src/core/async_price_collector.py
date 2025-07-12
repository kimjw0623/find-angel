from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncio
from src.api.async_api_client import TokenBatchRequester
from src.core.market_price_cache import DBMarketPriceCache
from itertools import combinations, product
from src.database.database import *
from src.common.utils import *
from src.common.config import config

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
    def __init__(self, db_manager: DatabaseManager, tokens: List[str]):
        self.db = db_manager
        self.cache = DBMarketPriceCache(self.db)
        self.requester = TokenBatchRequester(tokens)
        self.current_cycle_id = None
        self.ITEMS_PER_PAGE = config.items_per_page
        
        # 프리셋 생성기 초기화
        self.preset_generator = SearchPresetGenerator()

    async def run(self):
        """메인 실행 함수"""
        while True:
            try:
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
                
            except Exception as e:
                print(f"Error in collection cycle: {e}")
                await asyncio.sleep(config.time_settings["error_retry_delay"])

    async def collect_prices(self):
        """비동기 가격 수집"""
        try:
            self.current_cycle_id = datetime.now().strftime("%Y%m%d_%H%M")
            total_collected = 0

            # 악세서리 프리셋 준비
            parts = ["목걸이", "귀걸이", "반지"]
            grades = ["고대", "유물"]
            
            for grade in grades:
                # 1. 악세서리 수집
                for part in parts:
                    presets = self.preset_generator.generate_presets_acc(part)
                    collected = await self._collect_accessory_data(grade, part, presets)
                    total_collected += collected

                # 2. 팔찌 수집
                presets = self.preset_generator.generate_presets_bracelet(grade)
                collected = await self._collect_bracelet_data(grade, presets)
                total_collected += collected

            print(f"Total collected items: {total_collected}")
            
            if total_collected > 0:
                # 캐시 업데이트
                self.cache.update_cache(self.current_cycle_id)
                print(f"Cache updated at {datetime.now()}")
                
        except Exception as e:
            print(f"Error in price collection: {e}")

    async def collect_total_counts(self, search_presets: List[Dict]) -> Dict[str, int]:
        """각 프리셋의 첫 페이지를 검색하여 전체 페이지 수 확인"""
        preset_counts = {}
        
        # 첫 페이지 요청 준비
        initial_requests = []
        for preset in search_presets:
            search_data = preset.copy()
            search_data['PageNo'] = 1
            initial_requests.append({
                'preset_key': self._get_preset_key(preset),
                'search_data': search_data
            })

        # 배치 처리로 첫 페이지 검색
        results = await self.requester.process_requests([req['search_data'] for req in initial_requests])

        # 결과에서 전체 페이지 수 계산
        for i, result in enumerate(results):
            if result and not isinstance(result, Exception):
                preset_key = initial_requests[i]['preset_key']
                total_count = result.get('TotalCount', 0)
                total_pages = min(1000, (total_count + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
                preset_counts[preset_key] = total_pages
                print(f"Preset {preset_key}: {total_count} items ({total_pages} pages)")

        return preset_counts

    async def _collect_accessory_data(self, grade: str, part: str, presets: List[Dict]) -> int:
        """특정 등급/부위의 악세서리 데이터 수집"""
        total_collected = 0

        # 1. 각 프리셋의 전체 페이지 수 확인
        search_requests = []
        for preset in presets:
            search_data = self.preset_generator.create_search_data_acc(preset, grade, part)
            search_requests.append(search_data)

        total_pages = await self.collect_total_counts(search_requests)

        # 2. 모든 페이지 요청 생성
        all_requests = []
        for preset_idx, preset in enumerate(presets):
            preset_key = self._get_preset_key(search_requests[preset_idx])
            if preset_key in total_pages:
                for page in range(1, total_pages[preset_key] + 1):
                    search_data = self.preset_generator.create_search_data_acc(preset, grade, part, page)
                    all_requests.append(search_data)

        # 3. 모든 요청 처리
        results = await self.requester.process_requests(all_requests)

        # 4. 결과 일괄 처리
        all_processed_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                processed_items = self.process_acc_response(result, grade, part)
                if processed_items:
                    all_processed_items.extend(processed_items)

        # 5. 일괄 저장
        if all_processed_items:
            print(f"Saving {len(all_processed_items)} {grade} {part} items...")
            unique_count = await self.save_acc_items(all_processed_items, self.current_cycle_id)
            total_collected = len(all_processed_items) - unique_count
            print(f"Saved {total_collected} unique items after removing {unique_count} duplicates")

        return total_collected

    async def _collect_bracelet_data(self, grade: str, presets: List[Dict]) -> int:
        """특정 등급의 팔찌 데이터 수집"""
        total_collected = 0

        # 1. 각 프리셋의 전체 페이지 수 확인
        search_requests = []
        for preset in presets:
            search_data = self.preset_generator.create_search_data_bracelet(preset, grade)
            search_requests.append(search_data)

        total_pages = await self.collect_total_counts(search_requests)

        # 2. 모든 페이지 요청 생성
        all_requests = []
        for preset_idx, preset in enumerate(presets):
            preset_key = self._get_preset_key(search_requests[preset_idx])
            if preset_key in total_pages:
                for page in range(1, total_pages[preset_key] + 1):
                    search_data = self.preset_generator.create_search_data_bracelet(preset, grade, page)
                    all_requests.append(search_data)

        # 3. 모든 요청 처리
        results = await self.requester.process_requests(all_requests)

        # 4. 결과 일괄 처리
        all_processed_items = []
        for result in results:
            if result and not isinstance(result, Exception):
                processed_items = self.process_bracelet_response(result, grade)
                if processed_items:
                    all_processed_items.extend(processed_items)

        # 5. 일괄 저장
        if all_processed_items:
            print(f"Saving {len(all_processed_items)} {grade} bracelets...")
            unique_count = await self.save_bracelet_items(all_processed_items, self.current_cycle_id)
            total_collected = len(all_processed_items) - unique_count
            print(f"Saved {total_collected} unique items after removing {unique_count} duplicates")

        return total_collected

    def _get_preset_key(self, preset: Dict) -> str:
        """프리셋의 고유 키 생성"""
        if 'CategoryCode' in preset:
            if preset['CategoryCode'] == 200040:  # 팔찌
                # 팔찌는 ItemGrade와 EtcOptions에서 고정/부여 슬롯 정보 추출
                fixed_slots = None
                extra_slots = None
                for opt in preset['EtcOptions']:
                    if opt['FirstOption'] == 4:  # 팔찌 옵션 수량
                        if opt['SecondOption'] == 1:  # 고정 효과 수량
                            fixed_slots = opt['MinValue']
                        elif opt['SecondOption'] == 2:  # 부여 효과 수량
                            extra_slots = opt['MinValue']
                
                return f"bracelet_{preset['ItemGrade']}_fixed{fixed_slots}_extra{extra_slots}"
            
            else:  # 악세서리
                # 악세서리는 등급, 이름, 연마 레벨, 품질 포함
                level = preset.get('ItemUpgradeLevel', 0)
                quality = preset.get('ItemGradeQuality', 0)
                # 옵션 정보도 포함 (있는 경우)
                options = []
                for opt in preset.get('EtcOptions', []):
                    if opt.get('FirstOption') == 7:  # 연마 효과
                        options.append(f"{opt['SecondOption']}_{opt['MinValue']}")
                
                options_str = '_'.join(sorted(options)) if options else 'no_options'
                return f"{preset['ItemGrade']}_{preset['ItemName']}_lv{level}_q{quality}_{options_str}"
        
        return str(hash(str(preset)))

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

    def process_acc_response(self, response, grade, part):
        """API 응답 처리 및 DB 저장"""
        data = response
        if not data["Items"]:
            return None

        # 유효한 아이템 필터링
        valid_items = [
            item for item in data["Items"]
            if item["AuctionInfo"]["BuyPrice"] and item["GradeQuality"] >= 67
        ]
        if not valid_items:
            return None

        processed_items = []
        current_time = datetime.now()

        for item in valid_items:
            processed_item = {
                'timestamp': current_time,
                'grade': grade,
                'name': item["Name"],
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

    def process_bracelet_response(self, response, grade):
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
        current_time = datetime.now()

        for item in valid_items:
            # 기본 정보 처리
            processed_item = {
                'timestamp': current_time,
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
            if item_key not in unique_items or item['timestamp'] > unique_items[item_key]['timestamp']:
                unique_items[item_key] = item
        
        # 2. DB에 일괄 저장
        with self.db.get_write_session() as session:
            # 현재 사이클의 기존 아이템 확인
            existing_count = session.query(PriceRecord).filter(
                PriceRecord.search_cycle_id == search_cycle_id
            ).count()
            
            # 새 아이템들만 저장
            for item_data in unique_items.values():
                record = PriceRecord(
                    timestamp=item_data['timestamp'],
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
            
            session.flush()
            
            # 중복 제거된 수 반환
            return len(items) - len(unique_items)

    def _sync_save_bracelet_items(self, items: List[dict], search_cycle_id: str) -> int:
        """개선된 팔찌 아이템 저장"""
        # 1. 메모리 내 중복 제거
        unique_items = {}
        for item in items:
            item_key = _create_bracelet_hash_key(item)
            # 같은 키의 아이템 중 가장 최근 것만 유지
            if item_key not in unique_items or item['timestamp'] > unique_items[item_key]['timestamp']:
                unique_items[item_key] = item
        
        # 2. DB에 일괄 저장
        with self.db.get_write_session() as session:
            # 현재 사이클의 기존 아이템 확인
            existing_count = session.query(BraceletPriceRecord).filter(
                BraceletPriceRecord.search_cycle_id == search_cycle_id
            ).count()
            
            # 새 아이템들만 저장
            for item_data in unique_items.values():
                record = BraceletPriceRecord(
                    timestamp=item_data['timestamp'],
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
            
            session.flush()
            
            # 중복 제거된 수 반환
            return len(items) - len(unique_items)

class SearchPresetGenerator:
    def __init__(self):
        # self.qualities = [60, 70, 80, 90]
        self.qualities = [60]
        self.enhancement_levels = [0, 1, 2, 3]

        # 특수 옵션만 정의 (부가 옵션 제거)
        self.special_options = {
            "목걸이": [
                [],  # 특수 옵션 없는 경우
                # # 딜러용
                # # 특수 옵션 1개
                # [("추피", 1)], [("적주피", 1)],
                # [("추피", 2)], [("적주피", 2)],
                # [("추피", 3)], [("적주피", 3)],
                # # 특수 옵션 2개 - 모든 가능한 조합
                # [("추피", 1), ("적주피", 1)],
                # [("추피", 1), ("적주피", 2)],
                # [("추피", 1), ("적주피", 3)],
                # [("추피", 2), ("적주피", 1)],
                # [("추피", 2), ("적주피", 2)],
                # [("추피", 2), ("적주피", 3)],
                # [("추피", 3), ("적주피", 1)],
                # [("추피", 3), ("적주피", 2)],
                # [("추피", 3), ("적주피", 3)],
                # # 서폿용
                # [("아덴게이지", 1)], [("낙인력", 1)],
                # [("아덴게이지", 2)], [("낙인력", 2)],
                # [("아덴게이지", 3)], [("낙인력", 3)],
                # [("아덴게이지", 1), ("낙인력", 1)],
                # [("아덴게이지", 1), ("낙인력", 2)],
                # [("아덴게이지", 1), ("낙인력", 3)],
                # [("아덴게이지", 2), ("낙인력", 1)],
                # [("아덴게이지", 2), ("낙인력", 2)],
                # [("아덴게이지", 2), ("낙인력", 3)],
                # [("아덴게이지", 3), ("낙인력", 1)],
                # [("아덴게이지", 3), ("낙인력", 2)],
                # [("아덴게이지", 3), ("낙인력", 3)],
            ],
            "귀걸이": [
                [],
                # [("공퍼", 1)], [("무공퍼", 1)],
                # [("공퍼", 2)], [("무공퍼", 2)],
                # [("공퍼", 3)], [("무공퍼", 3)],
                # [("공퍼", 1), ("무공퍼", 1)],
                # [("공퍼", 1), ("무공퍼", 2)],
                # [("공퍼", 1), ("무공퍼", 3)],
                # [("공퍼", 2), ("무공퍼", 1)],
                # [("공퍼", 2), ("무공퍼", 2)],
                # [("공퍼", 2), ("무공퍼", 3)],
                # [("공퍼", 3), ("무공퍼", 1)],
                # [("공퍼", 3), ("무공퍼", 2)],
                # [("공퍼", 3), ("무공퍼", 3)],
            ],
            "반지": [
                [],
                # 딜러용
                # [("치적", 1)], [("치피", 1)],
                # [("치적", 2)], [("치피", 2)],
                # [("치적", 3)], [("치피", 3)],
                # [("치적", 1), ("치피", 1)],
                # [("치적", 1), ("치피", 2)],
                # [("치적", 1), ("치피", 3)],
                # [("치적", 2), ("치피", 1)],
                # [("치적", 2), ("치피", 2)],
                # [("치적", 2), ("치피", 3)],
                # [("치적", 3), ("치피", 1)],
                # [("치적", 3), ("치피", 2)],
                # [("치적", 3), ("치피", 3)],

                # 서폿용
                # [("아공강", 1)], [("아피강", 1)],
                # [("아공강", 2)], [("아피강", 2)],
                # [("아공강", 3)], [("아피강", 3)],
                # [("아공강", 1), ("아피강", 1)],
                # [("아공강", 1), ("아피강", 2)],
                # [("아공강", 1), ("아피강", 3)],
                # [("아공강", 2), ("아피강", 1)],
                # [("아공강", 2), ("아피강", 2)],
                # [("아공강", 2), ("아피강", 3)],
                # [("아공강", 3), ("아피강", 1)],
                # [("아공강", 3), ("아피강", 2)],
                # [("아공강", 3), ("아피강", 3)],
            ]
        }

        # # 부가 옵션도 수정
        # self.sub_options = {
        #     "목걸이": {
        #         "깡공": [1, 2, 3],
        #         "깡무공": [1, 2, 3],
        #         "최생": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #         "최마": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #     },
        #     "귀걸이": {
        #         "깡공": [1, 2, 3],
        #         "깡무공": [1, 2, 3],
        #         "아군회복": [1, 2, 3],      # 서폿용 부가 옵션 추가
        #         "아군보호막": [1, 2, 3],    # 서폿용 부가 옵션 추가
        #         "최생": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #         "최마": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #     },
        #     "반지": {
        #         "깡공": [1, 2, 3],
        #         "깡무공": [1, 2, 3],
        #         "최생": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #         "최마": [1, 2, 3],          # 서폿용 부가 옵션 추가
        #     }
        # }

    def generate_valid_option_combinations(self, part: str, enhancement_level: int) -> List[List[tuple]]:
        """연마 단계에 맞는 유효한 옵션 조합 생성"""
        if enhancement_level == 0:
            return [[]]  # 연마 0단계면 옵션 없음

        result = []

        # 특수 옵션 세트에서 연마 단계에 맞는 것만 선택
        for special_set in self.special_options[part]:
            if len(special_set) <= enhancement_level:
                result.append(special_set)

        return result

    def generate_presets_acc(self, part: str) -> List[Dict]:
        """전체 프리셋 생성"""
        presets = []

        # 각 연마 단계, 품질에 대해
        for level, quality in product(
            self.enhancement_levels,
            self.qualities
        ):
            # 해당 연마 단계에 맞는 옵션 조합 생성
            valid_options = self.generate_valid_option_combinations(
                part, level)

            # 각 옵션 조합에 대한 프리셋 생성
            for options in valid_options:
                preset = {
                    'enhancement_level': level,
                    'quality': quality,
                    'options': options
                }
                presets.append(preset)

        return presets

    def generate_presets_bracelet(self, grade: str) -> List[Dict]:
        """전체 프리셋 생성"""
        presets = []

        # 등급별 보너스 설정
        slot_bonus = 1 if grade == "고대" else 0        # 부여 하나 추가
        combat_stat_bonus = 20 if grade == "고대" else 0    # 특성 20 증가
        base_stat_bonus = 3200 if grade == "고대" else 0     # 주스탯 증가

        # 기본 수치 설정
        # combat_stat_values = [40, 50, 60, 70, 80, 90]
        combat_stat_values = [40]
        # base_stat_values = [6400, 8000, 9600, 11200]
        base_stat_values = [6400]
        combat_stats = ["특화", "치명", "신속"]
        base_stats = ["힘", "민첩", "지능"]

        # # 고정 효과 2개인 경우
        # for fixed_slots in [2]: 
        #     base_options = [
        #         ("팔찌 옵션 수량", "고정 효과 수량", fixed_slots),
        #     ]

        #     # 전투특성 2개 조합 생성
        #     for stat_combo in combinations(combat_stats, 2):
        #         for combat_stat_combo in product(combat_stat_values, repeat=2):
        #             # for extra_slots in [1, 2]:  # 부여 효과 수량 1개 또는 2개
        #             for extra_slots in [1]:  # 부여 효과 수량 1개
        #                 options = base_options + [
        #                     ("팔찌 옵션 수량", "부여 효과 수량", extra_slots + slot_bonus),
        #                     ("전투 특성", stat_combo[0],
        #                      combat_stat_combo[0] + combat_stat_bonus),
        #                     ("전투 특성", stat_combo[1],
        #                      combat_stat_combo[1] + combat_stat_bonus)
        #                 ]
        #                 presets.append({'options': options})

        #     # 전투특성 1개 + 기본스탯 조합 생성
        #     for combat_stat in combat_stats:
        #         for combat_stat_value in combat_stat_values:
        #             for base_stat in base_stats:
        #                 for base_stat_value in base_stat_values:
        #                     # for extra_slots in [1, 2]:  # 부여 효과 수량 1개 또는 2개
        #                     for extra_slots in [1]:  # 부여 효과 수량 1개
        #                         options = base_options + [
        #                             ("팔찌 옵션 수량", "부여 효과 수량",
        #                              extra_slots + slot_bonus),
        #                             ("전투 특성", combat_stat,
        #                              combat_stat_value + combat_stat_bonus),
        #                             ("팔찌 기본 효과", base_stat,
        #                              base_stat_value + base_stat_bonus)
        #                         ]
        #                         presets.append({'options': options})

        #     # 전투특성 1개 + 공이속 조합 생성
        #     for combat_stat in combat_stats:
        #         for combat_stat_value in combat_stat_values:
        #             # for extra_slots in [1, 2]:  # 부여 효과 수량 1개 또는 2개
        #             for extra_slots in [1]:  # 부여 효과 수량 1개
        #                 options = base_options + [
        #                     ("팔찌 옵션 수량", "부여 효과 수량", extra_slots + slot_bonus),
        #                     ("전투 특성", combat_stat,
        #                      combat_stat_value + combat_stat_bonus),
        #                     ("팔찌 특수 효과", "공격 및 이동 속도 증가", 0)
        #                 ]
        #                 presets.append({'options': options})

        #     # 전투특성 1개 + 잡 조합 생성
        #     for combat_stat in combat_stats:
        #         for combat_stat_value in combat_stat_values:
        #             options = base_options + [
        #                 ("팔찌 옵션 수량", "부여 효과 수량", 2 + slot_bonus),
        #                 ("전투 특성", combat_stat, combat_stat_value + combat_stat_bonus),
        #             ]
        #             presets.append({'options': options})

        # 고정 효과 1개인 경우 (전투특성 1개만)
        # base_options = [
        #     ("팔찌 옵션 수량", "고정 효과 수량", 1),
        # ]

        # for combat_stat in combat_stats:
        #     for combat_stat_value in combat_stat_values:
        #         options = base_options + [
        #             ("팔찌 옵션 수량", "부여 효과 수량", 2 + slot_bonus),
        #             ("전투 특성", combat_stat, combat_stat_value + combat_stat_bonus),
        #         ]
        #         presets.append({'options': options})

        # 고정 효과 1개인 경우 (전투특성 1개만)
        for fixed_slots in [1, 2]:
            for extra_slots in [1, 2]:
                options = [("팔찌 옵션 수량", "고정 효과 수량", fixed_slots), ("팔찌 옵션 수량", "부여 효과 수량", extra_slots + slot_bonus)]
                presets.append({'options': options})

        return presets

    def create_search_data_acc(self, preset: Dict, grade: str, part: str, page_no: int = 1) -> Dict:
        """생성된 프리셋으로 검색 데이터 생성"""
        level = preset['enhancement_level']
        quality = preset['quality']
        options = preset['options']

        data = {
            "ItemLevelMin": 0,
            "ItemLevelMax": 1800,
            "ItemGradeQuality": quality,
            "ItemUpgradeLevel": level,
            "ItemTradeAllowCount": None,
            "SkillOptions": [
                {
                    "FirstOption": None,
                    "SecondOption": None,
                    "MinValue": None,
                    "MaxValue": None
                }
            ],
            "EtcOptions": [
                # {
                #     "FirstOption": 8,
                #     "SecondOption": 1,
                #     "MinValue": enpoints,
                #     "MaxValue": enpoints
                # },
            ],
            "Sort": "BUY_PRICE",
            # 200010 목걸이, 20 귀걸이, 30 반지, 40 팔찌, 200000 장신구
            "CategoryCode": 200000,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": grade,
            "ItemName": part,
            "PageNo": page_no,
            "SortCondition": "ASC"
        }

        # 옵션 추가
        for opt_name, opt_level in options:
            data["EtcOptions"].append({
                "FirstOption": 7,
                "SecondOption": option_dict[opt_name],
                "MinValue": opt_level,
                "MaxValue": opt_level,
            })

        return data

    def create_search_data_bracelet(self, preset: Dict, grade: str, page_no: int = 1) -> Dict:
        """생성된 프리셋으로 검색 데이터 생성"""
        options = preset['options']

        data = {
            "ItemLevelMin": 0,
            "ItemLevelMax": 1800,
            "ItemGradeQuality": None,
            "SkillOptions": [
                {
                    "FirstOption": None,
                    "SecondOption": None,
                    "MinValue": None,
                    "MaxValue": None
                }
            ],
            "EtcOptions": [
                # { 왜인지 모르겠는데 이거 들어가면 검색이 안됨
                #     "FirstOption": 8,
                #     "SecondOption": 2,
                #     "MinValue": 18 if grade == "고대" else 9,
                #     "MaxValue": 18 if grade == "고대" else 9
                # },
            ],
            "Sort": "BUY_PRICE",
            # 200010 목걸이, 20 귀걸이, 30 반지, 40 팔찌, 200000 장신구
            "CategoryCode": 200040,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": grade,
            "PageNo": page_no,
            "SortCondition": "ASC"
        }

        # 옵션 추가
        for opt_first_name, opt_second_name, opt_value in options:
            data["EtcOptions"].append({
                "FirstOption": option_dict_bracelet_first[opt_first_name],
                "SecondOption": option_dict_bracelet_second[opt_second_name],
                "MinValue": opt_value,
                "MaxValue": opt_value,
            })

        return data

async def main():
    db_manager = DatabaseManager()   
    collector = AsyncPriceCollector(db_manager, tokens=config.price_tokens)
    await collector.run()

if __name__ == "__main__":
    asyncio.run(main())