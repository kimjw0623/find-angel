import threading
import time
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from database import *
from utils import *
from itertools import combinations, product
from typing import List, Dict, Tuple, Any
from market_price_cache import MarketPriceCache

class PriceCollector(threading.Thread):
    def __init__(self, db_manager):  # 기본 2시간 간격
        super().__init__()
        self.daemon = True
        self.db = db_manager
        self.current_cycle_id = None  # 추가
        self.url = "https://developer-lostark.game.onstove.com/auctions/items"
        self.headers = {
            'accept': 'application/json',
            'authorization': f"bearer {os.getenv('API_TOKEN_LOWESTPRICE')}",
            'content-Type': 'application/json'
        }

        # 프리셋 생성기 초기화
        self.preset_generator = SearchPresetGenerator()

    def process_acc_response(self, response, grade, part):
        """API 응답 처리 및 DB 저장"""
        data = response.json()
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
        data = response.json()
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

    def save_acc_items(self, items, search_cycle_id):
        """처리된 아이템 데이터를 DB에 저장"""
        with self.db.get_write_session() as session:
            dup_item_num = 0
            for item_data in items:
                # 1차 필터링: 기본 정보로 후보 아이템 조회
                candidate_items = session.query(PriceRecord).filter(
                    PriceRecord.grade == item_data['grade'],
                    PriceRecord.name == item_data['name'],
                    PriceRecord.part == item_data['part'],
                    PriceRecord.level == item_data['level'],
                    PriceRecord.quality == item_data['quality'],
                    PriceRecord.price == item_data['price'],
                    PriceRecord.search_cycle_id == search_cycle_id
                ).all()

                # 2차 필터링: 옵션 세부 비교
                is_duplicate = False
                for existing_item in candidate_items:
                    session.refresh(existing_item)  # 관계 데이터 리프레시

                    # 1. 명시적으로 같은 형식으로 만든 후 비교
                    existing_options = {(opt.option_name, opt.option_grade) for opt in existing_item.options}
                    new_options = {(opt[0], opt[1]) for opt in item_data['options']}  # 형식 명확히 지정

                    # 모든 옵션이 일치하는지 확인
                    if existing_options == new_options:
                        is_duplicate = True
                        dup_item_num += 1
                        break

                if is_duplicate:
                    continue

                record = PriceRecord(
                    timestamp=item_data['timestamp'],
                    search_cycle_id=search_cycle_id,  # 추가
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

                # 옵션 저장
                for opt_name, opt_grade in item_data['options']:
                    option = ItemOption(
                        option_name=opt_name,
                        option_grade=opt_grade
                    )
                    record.options.append(option)

                # 원본 옵션 저장
                for raw_opt in item_data['raw_options']:
                    raw_option = RawItemOption(
                        option_name=raw_opt['option_name'],
                        option_value=raw_opt['option_value'],
                        is_percentage=raw_opt['is_percentage']
                    )
                    record.raw_options.append(raw_option)

                session.add(record)
            return dup_item_num

    def save_bracelet_items(self, items, search_cycle_id):
        """처리된 팔찌 데이터를 DB에 저장"""
        with self.db.get_write_session() as session:
            dup_item_num = 0
            for item_data in items:
                # 1차 필터링: 기본 정보로 후보 아이템 조회
                candidate_items = session.query(BraceletPriceRecord).filter(
                    BraceletPriceRecord.grade == item_data['grade'],
                    BraceletPriceRecord.name == item_data['name'],
                    BraceletPriceRecord.price == item_data['price'],
                    BraceletPriceRecord.fixed_option_count == item_data['fixed_option_count'],
                    BraceletPriceRecord.extra_option_count == item_data['extra_option_count'],
                    BraceletPriceRecord.search_cycle_id == search_cycle_id,
                ).all()

                # 2차 필터링: 옵션 세부 비교
                is_duplicate = False
                for existing_item in candidate_items:
                    session.refresh(existing_item)  # 관계 데이터 리프레시

                    # 전투특성 비교
                    existing_combat_stats = {(stat.stat_type, stat.value) 
                                        for stat in existing_item.combat_stats}
                    new_combat_stats = {(stat['stat_type'], stat['value']) 
                                    for stat in item_data['combat_stats']}
                    
                    # 기본스탯 비교
                    existing_base_stats = {(stat.stat_type, stat.value) 
                                        for stat in existing_item.base_stats}
                    new_base_stats = {(stat['stat_type'], stat['value']) 
                                    for stat in item_data['base_stats']}
                    
                    # 특수효과 비교
                    existing_special_effects = {(effect.effect_type, effect.value) 
                                            for effect in existing_item.special_effects}
                    new_special_effects = {(effect['effect_type'], effect['value']) 
                                        for effect in item_data['special_effects']}

                    # 모든 옵션이 일치하는지 확인
                    if (existing_combat_stats == new_combat_stats and
                        existing_base_stats == new_base_stats and
                        existing_special_effects == new_special_effects):
                        dup_item_num += 1
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue

                record = BraceletPriceRecord(
                    timestamp=item_data['timestamp'],
                    search_cycle_id=search_cycle_id,  # 추가
                    grade=item_data['grade'],
                    name=item_data['name'],
                    trade_count=item_data['trade_count'],
                    price=item_data['price'],
                    end_time=item_data['end_time'],
                    fixed_option_count=item_data['fixed_option_count'],
                    extra_option_count=item_data['extra_option_count']
                )

                # 전투특성 저장
                for stat in item_data['combat_stats']:
                    combat_stat = BraceletCombatStat(
                        stat_type=stat['stat_type'],
                        value=stat['value']
                    )
                    record.combat_stats.append(combat_stat)

                # 기본스탯 저장
                for stat in item_data['base_stats']:
                    base_stat = BraceletBaseStat(
                        stat_type=stat['stat_type'],
                        value=stat['value']
                    )
                    record.base_stats.append(base_stat)

                # 특수효과 저장 
                for effect in item_data['special_effects']:
                    special_effect = BraceletSpecialEffect(
                        effect_type=effect['effect_type'],  # 딕셔너리의 effect_type 키
                        value=effect['value']               # 딕셔너리의 value 키
                    )
                    record.special_effects.append(special_effect)

                session.add(record)
            return dup_item_num

    def collect_prices(self):
        """각 부위별, 등급별 가격 수집"""
        try:
            # 사이클 시작할 때 ID 생성
            self.current_cycle_id = datetime.now().strftime("%Y%m%d_%H%M")
            
            # 악세서리
            parts = ["목걸이", "귀걸이", "반지"]
            grades = ["고대", "유물"]
            ACC_MAX_PAGES = 1000  # API에서 10000개 이후로 안 나옴
            BRACELET_MAX_PAGES = 1000 # API에서 10000개 이후로 안 나옴

            total_collected = 0
            for grade in grades:
                for part in parts:
                    # 해당 부위의 모든 프리셋 생성
                    presets = self.preset_generator.generate_presets_acc(part)
                    print(presets)
                    for preset in presets:
                        try:
                            # 첫 페이지 요청
                            search_data = self.preset_generator.create_search_data_acc(
                                preset, grade, part, page_no=1)
                            response = do_search(
                                self.url, self.headers, search_data, error_log=False)
                            
                            # 첫 페이지 처리
                            processed_items = self.process_acc_response(response, grade, part)
                            if not processed_items:
                                continue

                            # 첫 페이지 저장
                            dup_item_num = self.save_acc_items(processed_items, self.current_cycle_id)
                            total_collected += len(processed_items)
                            
                            # 총 매물 수 확인
                            total_count = response.json()["TotalCount"]
                            pages_to_fetch = min(ACC_MAX_PAGES, (total_count + 9) // 10)  # 올림 나눗셈

                            print(f"Found {total_count} items for {grade} {part} "
                                f"(Level: {preset['enhancement_level']}, "
                                f"Quality: {preset['quality']}, "
                                f"Options: {preset['options']}), {len(processed_items) - dup_item_num}/{len(processed_items)} are collected")

                            # 추가 페이지 처리
                            for page in range(2, pages_to_fetch + 1):
                                time.sleep(SEARCH_INTERVAL)  # API 요청 간격
                                
                                search_data = self.preset_generator.create_search_data_acc(
                                    preset, grade, part, page_no=page)
                                response = do_search(
                                    self.url, self.headers, search_data, error_log=False)
                                processed_items = self.process_acc_response(
                                    response, grade, part)
                                
                                if processed_items:
                                    dup_item_num = self.save_acc_items(processed_items, self.current_cycle_id)
                                    total_collected += len(processed_items)
                                    print(f"Collected additional {len(processed_items) - dup_item_num}/{len(processed_items)} are collected items from page {page}")

                        except Exception as e:
                            print(f"Error collecting {grade} {part}: {e}")
                            continue

                        time.sleep(SEARCH_INTERVAL)  # 다음 프리셋 검색 전 대기

                # 팔찌 (동일한 페이지네이션 로직 적용)
                presets = self.preset_generator.generate_presets_bracelet(grade)
                print(presets)

                for preset in presets:
                    try:
                        # 첫 페이지 요청
                        search_data = self.preset_generator.create_search_data_bracelet(
                            preset, grade, page_no=1)
                        response = do_search(
                            self.url, self.headers, search_data, error_log=False)
                        
                        # 첫 페이지 처리
                        processed_items = self.process_bracelet_response(response, grade)
                        if not processed_items:
                            continue

                        # 첫 페이지 저장
                        dup_item_num = self.save_bracelet_items(processed_items, self.current_cycle_id)
                        total_collected += len(processed_items)
                        
                        # 총 매물 수 확인
                        total_count = response.json()["TotalCount"]
                        pages_to_fetch = min(BRACELET_MAX_PAGES, (total_count + 9) // 10)

                        print(f"Found {total_count} bracelet items for {grade}, {preset}, {len(processed_items) - dup_item_num}/{len(processed_items)} are collected")

                        # 추가 페이지 처리
                        for page in range(2, pages_to_fetch + 1):
                            time.sleep(SEARCH_INTERVAL)
                            
                            search_data = self.preset_generator.create_search_data_bracelet(
                                preset, grade, page_no=page)
                            response = do_search(
                                self.url, self.headers, search_data, error_log=False)
                            processed_items = self.process_bracelet_response(
                                response, grade)
                            
                            if processed_items:
                                dup_item_num = self.save_bracelet_items(processed_items, self.current_cycle_id)
                                total_collected += len(processed_items)
                                print(f"Collected additional {len(processed_items) - dup_item_num}/{len(processed_items)} bracelet items from page {page}")

                    except Exception as e:
                        print(f"Error collecting {grade} bracelet: {e}")
                        continue

                    time.sleep(SEARCH_INTERVAL)

            print(f"Total collected items: {total_collected}")
            
            if total_collected > 0:  # 새로운 데이터가 수집된 경우에만
                # 캐시 업데이트 실행
                cache = MarketPriceCache(self.db)
                cache.update_cache()
                print(f"Cache updated at {datetime.now()}")
        
        except Exception as e:
            print(f"Error in price collection: {e}")

    def run(self):
        """메인 스레드 실행"""
        def get_next_run_time():
            """다음 실행 시간 계산 (다음 짝수 시간)"""
            now = datetime.now()
            current_hour = now.hour
            next_hour = current_hour + (2 - current_hour % 2)  # 다음 짝수 시간
            
            next_run = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            if next_run <= now:  # 이미 지난 시간이면 다음 주기로
                next_run += timedelta(hours=2)
            return next_run

        while True:
            try:
                # 다음 실행 시간까지 대기
                next_run = get_next_run_time()
                wait_seconds = (next_run - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    print(f"다음 실행 시간: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"대기 중... ({int(wait_seconds)}초)")
                    time.sleep(wait_seconds)

                # 가격 수집 실행
                start_time = datetime.now()
                print(f"Starting price collection at {start_time}")
                
                self.collect_prices()
                
                end_time = datetime.now()
                duration = end_time - start_time
                
                # 소요 시간 계산
                hours, remainder = divmod(duration.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                # 소요 시간 표시
                duration_str = []
                if hours > 0:
                    duration_str.append(f"{int(hours)}시간")
                if minutes > 0:
                    duration_str.append(f"{int(minutes)}분")
                duration_str.append(f"{int(seconds)}초")
                
                print(f"Completed price collection at {end_time}")
                print(f"총 소요 시간: {' '.join(duration_str)}")
                
            except Exception as e:
                print(f"Error in price collection: {e}")
                # 에러 발생 시 1분 대기 후 재시도
                time.sleep(60)


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

if __name__ == "__main__":
    # 환경 변수 로드
    load_dotenv()
    
    print("Starting price collector...")
    db_manager = init_database()  # DatabaseManager() 대신 init_database() 사용
    collector = PriceCollector(db_manager)
    collector.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping price collector...")