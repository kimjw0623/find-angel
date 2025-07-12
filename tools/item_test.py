import re
from database import *
from market_price_cache import MarketPriceCache
from item_evaluator import ItemEvaluator

def parse_market_item(line: str) -> dict:
    """매물 정보 문자열을 아이템 딕셔너리로 변환"""
    import re

    # 기본 정보 파싱
    parts = line.split(" | ")

    # 이름과 등급 파싱
    name_parts = parts[0].split()
    grade = name_parts[0]  # 첫 번째 단어는 등급
    name = " ".join(name_parts[1:])  # 나머지는 이름

    # 가격 파싱
    price_str = parts[1].split()[0]
    price = int(price_str.replace(",", "").replace("골드", ""))

    if "팔찌" in name:
        # 팔찌 옵션 파싱
        options = []
        # 고정/부여 정보 파싱
        fixed_parts = parts[2].split()
        fixed_count = int(fixed_parts[1])
        extra_count = int(fixed_parts[3])

        # 스탯 파싱
        stat_str = parts[4]

        # 정규식으로 스탯과 값을 추출
        stat_pattern = re.compile(
            r"(특화|치명|신속|힘|민첩|지능|체력|제압|인내|신속|공격 및 이동 속도 증가|물리 방어력|마법 방어력|전투 자원 회복량|피격 이상 면역 효과|시드 이하 받는 피해 감소|시드 이하 주는 피해 증가|이동기 및 기상기 재사용 대기시간 감소|전투 중 생명력 회복량|최대 생명력)(\d+\.?\d*)"
        )
        extra_pattern = re.compile(r"부여 효과 수량(\d+\.?\d*)")

        # 스탯 매칭
        for match in stat_pattern.finditer(stat_str):
            stat_name, value = match.groups()
            options.append({
                "Type": "STAT",
                "OptionName": stat_name,
                "Value": float(value)
            })

        # 부여 효과 수량 매칭
        extra_match = extra_pattern.search(stat_str)
        if extra_match:
            value = extra_match.group(1)
            options.append({
                "Type": "BRACELET_RANDOM_SLOT",
                "OptionName": "부여 효과 수량",
                "Value": float(value)
            })

    else:
        # 악세서리 옵션 파싱
        quality = int(parts[2].split()[1])
        level = int(parts[3].split()[0].replace("연마", ""))
        trade_count = int(parts[6].split()[1].replace("회", ""))

        options = []
        # 옵션 파싱
        option_str = parts[5]

        # 정규식으로 옵션과 값을 추출
        option_pattern = re.compile(r'(추피|적주피|아덴게이지|낙인력|공퍼|무공퍼|아군회복|아군보호막|치적|치피|아공강|아피강|깡공|깡무공|최생|최마|전투중생회|상태이상공격지속시간)(\d+\.?\d*)')

        for match in option_pattern.finditer(option_str):
            opt_name, value = match.groups()
            options.append({
                "OptionName": opt_name,
                "Value": float(value)
            })

        # 깨달음 옵션 추가
        options.append({
            "OptionName": "깨달음",
            "Value": level + 8
        })

        return {
            "Name": name,
            "Grade": grade,
            "GradeQuality": quality,
            "AuctionInfo": {
                "BuyPrice": price,
                "TradeAllowCount": trade_count,
                "EndDate": parts[4].split()[-1]  # 만료 시간 추가
            },
            "Options": options
        }

    return {
        "Name": name,
        "Grade": grade,
        "AuctionInfo": {
            "BuyPrice": price,
            "EndDate": parts[3].split()[-1]  # 만료 시간 추가
        },
        "Options": options
    }

def main():
    # 데이터베이스 매니저와 평가기 초기화
    db_manager = init_database()  # DatabaseManager() 대신 init_database() 사용
    price_cache = MarketPriceCache(db_manager, debug=True)
    evaluator = ItemEvaluator(price_cache, debug=True)
    
    print("매물 정보를 입력하세요. 종료하려면 'q' 또는 'exit'를 입력하세요.")
    print("입력 형식 예시:")
    print("팔찌: 고대 찬란한 구원자의 팔찌 | 27,777골드 vs 42,555골드 (65.3%) | 고정 2 부여 3 | 만료 2024-11-18T17:49:20.913 | 신속78.0 특화78.0 부여 효과 수량3.0")
    print("악세서리: 유물 엄숙한 결의의 반지 | 500골드 vs 194골드 (257.7%) | 품질 91 | 3연마 | 만료 2024-11-18T17:49:19.667 | 아피강4.5 깡무공480.0 최마15.0 | 거래 2회")
    
    while True:
        line = input("\n매물 정보 입력: ")
        if line.lower() in ['q', 'exit']:
            break
            
        try:
            test_item = parse_market_item(line)
            print("\n=== 파싱된 아이템 정보 ===")
            print(f"이름: {test_item['Name']}")
            print(f"등급: {test_item['Grade']}")
            if 'GradeQuality' in test_item:
                print(f"품질: {test_item['GradeQuality']}")
            print(f"가격: {test_item['AuctionInfo']['BuyPrice']:,}")
            print("옵션:")
            for opt in test_item['Options']:
                print(f"  {opt['OptionName']}: {opt['Value']}")
                
            print("\n=== 가격 평가 결과 ===")
            evaluation = evaluator.evaluate_item(test_item)
            
            if evaluation:
                print(f"아이템 종류: {evaluation['type']}")
                print(f"예상 가격: {evaluation['expected_price']:,}")
                print(f"가격 비율: {evaluation['price_ratio']:.1%}")
                print(f"주목할만함: {evaluation['is_notable']}")
            else:
                print("가격 평가 실패")
                
        except Exception as e:
            print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()
