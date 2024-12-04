import datetime

type_to_code = {
    "목걸이": 200010,
    "귀걸이": 200020,
    "반지": 200030,
    "팔찌": 200040,
}

code_to_type = {
    200010: "목걸이",
    200020: "귀걸이",
    200030: "반지",
    200040: "팔찌",
}

stat_to_code = {
    "힘": 3,
    "민첩": 4,
    "지능": 5,
    "체력": 6,
    "치명": 15,
    "특화": 16,
    "제압": 17,
    "신속": 18,
    "인내": 19,
    "숙련": 20,
}

code_to_stat = {
    3: "힘",
    4: "민첩",
    5: "지능",
    6: "체력",
    15: "치명",
    16: "특화",
    17: "제압",
    18: "신속",
    19: "인내",
    20: "숙련",
}

effect_to_code = {
    "추가 피해": 41,
    "적에게 주는 피해": 42,
    "세레나데, 신성, 조화 게이지 획득량 증가": 43,
    "낙인력": 44,
    "공격력 ": 45, # 공퍼, 띄어쓰기에 주의
    "무기 공격력 ": 46, # 무공퍼, 띄어쓰기에 주의
    "파티원 회복 효과": 47,
    "파티원 보호막 효과": 48,
    "치명타 적중률": 49,
    "치명타 피해": 50,
    "아군 공격력 강화 효과": 51,
    "아군 피해량 강화 효과": 52,
    #"무기 공격력 ": 53, # 깡무공, 띄어쓰기에 주의
    #"공격력 ": 54, # 깡공, 띄어쓰기에 주의
    "최대 생명력": 55,
    "최대 마나": 56,
    "상태이상 공격 지속시간": 57,
    "전투 중 생명력 회복량": 58,
}

code_to_effect = {
    41: "추피",
    42: "적주피",
    43: "아덴게이지",
    44: "낙인력",
    45: "공퍼",
    46: "무공퍼 ",
    47: "아군회복",
    48: "아군쉴드",
    49: "치적",
    50: "치피",
    51: "아공강",
    52: "아피강",
    53: "깡무공",
    54: "깡공",
    55: "최생",
    56: "최마",
    57: "상태이상공격지속시간",
    58: "전투중생회",
}

effect_value_to_code = {
    41: {   0.7 : 1,    1.6 : 2,    2.6 : 3},
    42: {   0.55: 1,    1.2 : 2,    2.0 : 3},
    43: {   1.6 : 1,    3.6 : 2,    6.0 : 3},
    44: {   2.15: 1,    4.8 : 2,    8.0 : 3},
    45: {   0.4 : 1,    0.95: 2,    1.55: 3},
    46: {   0.8 : 1,    1.8 : 2,    3.0 : 3},
    47: {   0.95: 1,    2.1 : 2,    3.5 : 3},
    48: {   0.95: 1,    2.1 : 2,    3.5 : 3},
    49: {   0.4 : 1,    0.95: 2,    1.55: 3},
    50: {   1.1 : 1,    2.4 : 2,    4.0 : 3},
    51: {   1.35: 1,    3.0 : 2,    5.0 : 3},
    52: {   2.0 : 1,    4.5 : 2,    7.5 : 3},
    53: { 195.0 : 1,  480.0 : 2,  960.0 : 3},
    54: {  80.0 : 1,  195.0 : 2,  390.0 : 3},
    55: {1300.0: 1,  3250.0 : 2, 6500.0 : 3},
    56: {   6.0: 1,    15.0 : 2,   30.0 : 3},
    57: {   0.2: 1,     0.5 : 2,    1.0 : 3},
    58: {  10.0: 1,    25.0 : 2,   50.0 : 3},
}


class Item:
    def __init__(self, name, grade, price, endDate, type, options, gradeQuality=None, tradeAllowCount=None, upgradeLevel=None):
        self.name = name
        self.grade = grade
        self.price = price
        self.endDate = endDate
        self.type = type
        self.options = options
        self.gradeQuality = gradeQuality
        self.tradeAllowCount = tradeAllowCount
        self.upgradeLevel = upgradeLevel

    @staticmethod
    def parse_type(name):
        if "목걸이" in name:
            return 200010
        elif "귀걸이" in name:
            return 200020
        elif "반지" in name:
            return 200030
        elif "팔찌" in name:
            return 200040
        else:
            raise ValueError("Unknown item type, Item name: " + name)

    @staticmethod
    def parse_accessory_options(options):
        toReturn = []
        for op in options:
            if op["Type"] == "ACCESSORY_UPGRADE":
                if op["OptionName"] == "공격력 " and op["IsValuePercentage"]:
                    toReturn.append((3, 54, effect_value_to_code[54][op["Value"]]))
                elif op["OptionName"] == "무기 공격력 " and op["IsValuePercentage"]:
                    toReturn.append((3, 53, effect_value_to_code[53][op["Value"]]))
                else:
                    toReturn.append((3, effect_to_code[op["OptionName"]], effect_value_to_code[effect_to_code[op["OptionName"]]][op["Value"]]))

        return toReturn
    
    @staticmethod
    def parse_bracelet_options(options):
        toReturn = []
        for op in options:
            if op["Type"] == "STAT":
                toReturn.append((2, stat_to_code[op["OptionName"]], int(op["Value"])))
            elif op["Type"] == "BRACELET_RANDOM_SLOT":
                toReturn.append((4, 2, int(op["Value"])))
            elif op["Type"] == "????????????": #TODO: check if this is correct
                toReturn.append((1, stat_to_code[op["OptionName"]], int(op["Value"])))
            elif op["Type"] == "????????????": # TODO: check if this is correct
                toReturn.append((5, 60, int(op["Value"])))
        return toReturn

    @staticmethod
    def from_response_json(json):
        
        name = json["Name"]
        grade = json["Grade"]
        price = json["AuctionInfo"]["BuyPrice"]
        endDate = datetime.fromisoformat(json["AuctionInfo"]["EndDate"])

        type = Item.parse_type(name)

        if type == 200040:
            options = Item.parse_bracelet_options(json["Options"])
            return Item(name, grade, price, endDate, type, options)
        else:
            options = Item.parse_accessory_options(json["Options"])
            gradeQuality = json["GradeQuality"]
            tradeAllowCount = json["AuctionInfo"]["TradeAllowCount"]
            upgradeLevel = json["AuctionInfo"]["UpgradeLevel"]
            return Item(name, grade, price, endDate, type, options, gradeQuality, tradeAllowCount, upgradeLevel)

        # tier = json["Tier"] # must be 4
        # level = json["Level"] # must be one of 1640 or 1680
        # icon = json["Icon"] # image url
        # startPrice = json["AuctionInfo"]["StartPrice"]
        # bidPrice = json["AuctionInfo"]["BidPrice"]
        # bidCount = json["AuctionInfo"]["BidCount"]
        # bidStartPrice = json["AuctionInfo"]["BidStartPrice"]
        # isCompetitive = json["AuctionInfo"]["IsCompetitive"]
        
    def evaluate(self, evaluator):
        pass