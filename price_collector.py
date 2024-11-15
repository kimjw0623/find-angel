import threading
import time
from datetime import datetime
from utils import option_dict, level_enpoint, do_search, fix_dup_options, number_to_scale

class PriceCollector(threading.Thread):
    def __init__(self, db_manager, interval=7200):  # 기본 2시간 간격
        super().__init__()
        self.daemon = True
        self.db = db_manager
        self.interval = interval
        self.url = "https://developer-lostark.game.onstove.com/auctions/items"
        self.headers = {
            'accept': 'application/json',
            'authorization': f"bearer {os.getenv('API_TOKEN_LOWESTPRICE')}",
            'content-Type': 'application/json'
        }

    def gen_search_data(self, grade, preset, pageNo=1):
        """검색 데이터 생성"""
        level = preset[0]
        options = preset[1:]
        
        # 목걸이 여부 확인
        is_necklace = any(opt[0] in ["추피", "적주피", "아덴게이지", "낙인력"] for opt in options)
        
        # enpoints 계산
        if is_necklace:
            enpoints = 4 + level_enpoint[grade][level]
        else:
            enpoints = 3 + level_enpoint[grade][level]

        data = {
            "ItemLevelMin": 0,
            "ItemLevelMax": 1800,
            "ItemGradeQuality": 60,
            "SkillOptions": [
                {
                    "FirstOption": None,
                    "SecondOption": None,
                    "MinValue": None,
                    "MaxValue": None
                }
            ],
            "EtcOptions": [
                {
                    "FirstOption": 8,
                    "SecondOption": 1,
                    "MinValue": enpoints,
                    "MaxValue": enpoints
                },
            ],
            "Sort": "BUY_PRICE",
            "CategoryCode": 200000,
            "CharacterClass": "",
            "ItemTier": 4,
            "ItemGrade": grade,
            "PageNo": pageNo,
            "SortCondition": "ASC"
        }

        for option in options:
            option_name = option[0]
            option_level = option[1]
            option_to_dict = {
                "FirstOption": 7,
                "SecondOption": option_dict[option_name],
                "MinValue": option_level,
                "MaxValue": option_level,
            }
            data["EtcOptions"].append(option_to_dict)

        return data

    def process_response(self, response, grade, part):
        """API 응답 처리 및 DB 저장"""
        data = response.json()
        if not data["Items"]:
            return None

        processed_items = []
        current_time = datetime.now()

        for item in data["Items"]:
            if not item["AuctionInfo"]["BuyPrice"] or item["GradeQuality"] < 67:
                continue

            # 기본 정보 구조화
            processed_item = {
                'timestamp': current_time,
                'grade': grade,
                'name': item["Name"],
                'part': part,
                'level': len(item["Options"]) - 1,
                'quality': item["GradeQuality"],
                'trade_count': item["AuctionInfo"]["TradeAllowCount"],
                'price': item["AuctionInfo"]["BuyPrice"],
                'end_time': datetime.strptime(item["AuctionInfo"]["EndDate"].split('.')[0], 
                                            "%Y-%m-%dT%H:%M:%S"),
                'options': [],
                'raw_options': []
            }

            # 옵션 처리
            fix_dup_options(item)
            for option in item["Options"]:
                if option["OptionName"] not in ["아크", "도약"]:
                    opt_value = option["Value"]
                    # raw option 저장
                    processed_item['raw_options'].append({
                        'option_name': option["OptionName"],
                        'option_value': opt_value,
                        'is_percentage': option.get("IsValuePercentage", False)
                    })
                    # 가공된 option 저장
                    opt_grade = number_to_scale.get(option["OptionName"], {}).get(opt_value, 1)
                    processed_item['options'].append((option["OptionName"], opt_grade))

            processed_items.append(processed_item)

        return processed_items

    def save_items(self, items):
        """처리된 아이템 데이터를 DB에 저장"""
        with self.db.get_write_session() as session:
            for item_data in items:
                record = PriceRecord(
                    timestamp=item_data['timestamp'],
                    grade=item_data['grade'],
                    name=item_data['name'],
                    part=item_data['part'],
                    level=item_data['level'],
                    quality=item_data['quality'],
                    trade_count=item_data['trade_count'],
                    price=item_data['price'],
                    end_time=item_data['end_time']
                )

                # 가공된 옵션 저장
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

    def collect_prices(self):
        """각 부위별, 등급별 가격 수집"""
        parts = {
            "목걸이": self.necklace_presets,
            "귀걸이": self.earring_presets,
            "반지": self.ring_presets
        }
        grades = ["고대", "유물"]

        for grade in grades:
            for part, presets in parts.items():
                for preset in presets:
                    try:
                        post_body = self.gen_search_data(grade, preset)
                        response = do_search(self.url, self.headers, post_body)
                        
                        if response.status_code == 200:
                            items = self.process_response(response, grade, part)
                            if items:
                                self.save_items(items)
                                print(f"Collected {len(items)} items for {grade} {part} with preset {preset}")
                    except Exception as e:
                        print(f"Error collecting {grade} {part} with preset {preset}: {e}")

    def run(self):
        """스레드 실행 메서드"""
        while True:
            try:
                print(f"Starting price collection at {datetime.now()}")
                self.collect_prices()
                print(f"Completed price collection at {datetime.now()}")
            except Exception as e:
                print(f"Error in price collection: {e}")
            
            time.sleep(self.interval)

    # 프리셋 정의들은 원래 코드에서 가져옴
    necklace_presets = [
        [3, ("추피", 3), ("적주피", 3)],
        [3, ("추피", 2), ("적주피", 3)],
        # ... 나머지 프리셋
    ]

    earring_presets = [
        [3, ("공퍼", 3), ("무공퍼", 3)],
        [3, ("공퍼", 2), ("무공퍼", 3)],
        # ... 나머지 프리셋
    ]

    ring_presets = [
        [3, ("치적", 3), ("치피", 3)],
        [3, ("치적", 2), ("치피", 3)],
        # ... 나머지 프리셋
    ]