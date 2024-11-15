import time
import os
from datetime import datetime, timedelta
from database import DatabaseManager, PriceRecord, ItemOption, RawItemOption
from utils import *

class ItemChecker:
    def __init__(self, db_manager):
        self.db = db_manager
        self.url = "https://developer-lostark.game.onstove.com/auctions/items"
        
        # 3일짜리 토큰
        self.headers_3day = {
            'accept': 'application/json',
            'authorization': f"bearer {os.getenv('API_TOKEN_HONEYITEM_3DAY')}",
            'content-Type': 'application/json'
        }
        
        # 1일짜리 토큰
        self.headers_1day = {
            'accept': 'application/json',
            'authorization': f"bearer {os.getenv('API_TOKEN_HONEYITEM_1DAY')}",
            'content-Type': 'application/json'
        }
        
        # 마지막 체크 시간 초기화
        self.last_expireDate_3day = None
        self.last_expireDate_1day = None
        self.last_page_index_1day = None

    def gen_search_data(self, grade, pageNo=1):
        """검색 데이터 생성"""
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
            "Sort": "EXPIREDATE",
            "CategoryCode": 200000,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": grade,
            "ItemName": "",
            "PageNo": pageNo,
            "SortCondition": "DESC",
            "EtcOptions": [
                {
                    "FirstOption": 8,
                    "SecondOption": 1,
                    "MinValue": 1,
                    "MaxValue": '',
                },
            ],
        }
        return data

    def evaluate_item(self, item):
        """아이템 가치 평가"""
        # 기본 정보 추출
        grade = item["Grade"]
        level = len(item["Options"]) - 1
        if level == 0 or item['GradeQuality'] < 67:
            return None

        part = None
        if "목걸이" in item["Name"]:
            part = "목걸이"
        elif "귀걸이" in item["Name"]:
            part = "귀걸이"
        elif "반지" in item["Name"]:
            part = "반지"
        else:
            return None

        # DB에서 유사 아이템 검색
        with self.db.get_read_session() as session:
            # 최근 24시간 데이터 중에서 검색
            recent_time = datetime.now() - timedelta(hours=24)
            query = session.query(PriceRecord).filter(
                PriceRecord.timestamp >= recent_time,
                PriceRecord.grade == grade,
                PriceRecord.part == part,
                PriceRecord.level == level,
                PriceRecord.quality >= item["GradeQuality"] - 5,
                PriceRecord.quality <= item["GradeQuality"] + 5
            )

            similar_items = query.all()
            if not similar_items:
                return None

            # 옵션 조합이 동일한 아이템들 필터링
            fix_dup_options(item)
            target_options = set(
                (opt["OptionName"], number_to_scale.get(opt["OptionName"], {}).get(opt["Value"], 1))
                for opt in item["Options"]
                if opt["OptionName"] not in ["아크", "도약"]
            )

            matched_items = []
            for record in similar_items:
                record_options = set(
                    (opt.option_name, opt.option_grade)
                    for opt in record.options
                )
                if record_options == target_options:
                    matched_items.append(record)

            if not matched_items:
                return None

            # 평균 가격 계산
            avg_price = sum(r.price for r in matched_items) / len(matched_items)
            current_price = item["AuctionInfo"]["BuyPrice"]
            
            # 가치 평가 결과 생성
            evaluation = {
                "expected_price": int(avg_price),
                "price_ratio": current_price / avg_price,
                "damage_increment": calc_dmg_increment_percent(item),
                "quality": item["GradeQuality"],
                "trade_count": item["AuctionInfo"]["TradeAllowCount"]
            }

            return evaluation

    def process_new_items(self, items):
        """새로운 매물들 처리"""
        if not items:
            return None

        results = []
        for item in items:
            if not item["AuctionInfo"]["BuyPrice"]:  # 즉구가 없으면 스킵
                continue

            evaluation = self.evaluate_item(item)
            if not evaluation:
                continue

            # 매물이 주목할 만한지 확인
            is_notable = False
            price_ratio = evaluation["price_ratio"]
            expected_price = evaluation["expected_price"]

            if price_ratio < 0.6 and expected_price > 60000:
                is_notable = True
            elif price_ratio < 0.45 and expected_price > 40000:
                is_notable = True

            if is_notable:
                result = {
                    "item": item,
                    "evaluation": evaluation,
                    "alert": True
                }
                results.append(result)

        return results

    def find_new_items_3day(self):
        """3일 만료 매물 검색"""
        current_time = datetime.now()
        if not self.last_expireDate_3day:
            self.last_expireDate_3day = current_time + timedelta(days=3) - timedelta(minutes=3)

        new_items = []
        repeat = True
        pageNo = 1
        next_expireDate = None

        while repeat:
            post_body = self.gen_search_data(grade="", pageNo=pageNo)
            response = do_search(self.url, self.headers_3day, post_body, error_log=False)
            data = response.json()

            for item in data["Items"]:
                end_time = datetime.strptime(item["AuctionInfo"]["EndDate"].split('.')[0], 
                                           "%Y-%m-%dT%H:%M:%S")
                if end_time <= self.last_expireDate_3day:
                    repeat = False
                    break
                else:
                    new_items.append(item)
                    if not next_expireDate:
                        next_expireDate = end_time

            pageNo += 1

        if not next_expireDate:
            next_expireDate = self.last_expireDate_3day

        self.last_expireDate_3day = next_expireDate
        return new_items

    def find_new_items_1day(self):
        """1일 만료 매물 검색"""
        # 1일짜리 매물 검색 로직 구현
        # (원래 코드의 find_new_items_1day 로직과 동일)
        pass

    def check_new_items(self):
        """새로운 매물 체크 및 평가"""
        # 3일 만료 매물 체크
        new_items_3day = self.find_new_items_3day()
        results_3day = self.process_new_items(new_items_3day)
        if results_3day:
            for result in results_3day:
                if result["alert"]:
                    print(f"[3일 매물] 주목할 매물 발견!")
                    self.print_item_details(result)

        # 1일 만료 매물 체크
        new_items_1day = self.find_new_items_1day()
        results_1day = self.process_new_items(new_items_1day)
        if results_1day:
            for result in results_1day:
                if result["alert"]:
                    print(f"[1일 매물] 주목할 매물 발견!")
                    self.print_item_details(result)

        return bool(results_3day or results_1day)

    def print_item_details(self, result):
        """아이템 상세 정보 출력"""
        item = result["item"]
        eval = result["evaluation"]
        
        print(f"이름: {item['Name']}")
        print(f"품질: {item['GradeQuality']}")
        print(f"현재 가격: {item['AuctionInfo']['BuyPrice']:,}")
        print(f"예상 가격: {eval['expected_price']:,}")
        print(f"가격 비율: {eval['price_ratio']*100:.1f}%")
        print(f"거래 횟수: {item['AuctionInfo']['TradeAllowCount']}")
        print(f"데미지 증가: {eval['damage_increment']:.2f}%")
        print("옵션:")
        for opt in item["Options"]:
            if opt["OptionName"] not in ["아크", "도약"]:
                print(f"  - {opt['OptionName']}: {opt['Value']}")
        print("-" * 50)