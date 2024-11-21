import requests
from requests.structures import CaseInsensitiveDict
import utils

def fire_webhook(url, message):
    headers = CaseInsensitiveDict()
    headers["Content-Type"] = "application/json"

    result = requests.post(url, headers=headers, data=f"""{{"content":"{message}"}}""")
    
    return result.status_code

def send_discord_message(url, item, evaluation, url2=None):
    legacy_discord_message(url, item, evaluation)
    try:
        if url2:
            formatted_discord_message(url2, item, evaluation)
    except:
        pass

    
def legacy_discord_message(url, item, evaluation):
    options_str = ' '.join([f"{opt['OptionName']}{opt['Value']}" for opt in item["Options"] 
                        if opt["OptionName"] not in ["깨달음", "도약"]])
    
    end_date = item["AuctionInfo"]["EndDate"]  # 원본 문자열 그대로 사용
    return_str = ""

    if evaluation["type"] == "accessory": # 장신구
        return_str = (f"{evaluation['grade']} {item['Name']} | "
            f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
            f"({evaluation['price_ratio']*100:.1f}%) | "
            f"품질 {evaluation['quality']} | {evaluation['level']}연마 | "
            f"만료 {end_date} | "
            f"{options_str} | "
            f"거래 {item['AuctionInfo']['TradeAllowCount']}회")
    else:  # 팔찌
        return_str = (f"{evaluation['grade']} {item['Name']} | "
            f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 "
            f"({evaluation['price_ratio']*100:.1f}%) | "
            f"고정 {evaluation['fixed_option_count']} 부여 {int(evaluation['extra_option_count'])} | "
            f"만료 {end_date} | "
            f"{options_str}")

    print(return_str)
    fire_webhook(url, return_str)

def accessory_option(opt):
    colorList = ["\\u001b[2;30m", "\\u001b[2;34m", "\\u001b[2;35m", "\\u001b[2;33m"]
    scaleList = " 하중상"
    try:
        scale = utils.number_to_scale[opt["OptionName"]][opt["Value"]]
    except KeyError:
        scale = 0 
    return colorList[scale], scaleList[scale]

def bracelet_option_color(opt, grade):
    name = opt["OptionName"]
    value = int(opt['Value'])
    if name == "부여 효과 수량": # 2~3 / 1~2
        if grade == "고대":
            value -= 1
        if value == 2:
            return "\\u001b[2;33m"
        else:
            return "\\u001b[2;34m"

    elif name == "공격 및 이동 속도 증가": # 3~5 / 4~6
        if grade == "고대":
            value -= 1
        if value == 5:
            return "\\u001b[2;33m"
        elif value == 4:
            return "\\u001b[2;35m"
        else:
            return "\\u001b[2;34m"

    elif name in ["특화", "신속", "치명"]: # 61~100 / 81~120
        if grade == "고대":
            value -= 20
        if value == 100:
            return "\\u001b[2;33m"
        elif value > 80:
            return "\\u001b[2;35m"
        elif value > 62: # 62 was green
            return "\\u001b[2;34m"
        else: # 40 초과
            return "\\u001b[2;32m"

    elif name in ["힘", "민첩", "지능"]: # 6400~12800 / 9600~16000
        if grade == "고대":
            value -= 3200
        if value == 12800:
            return "\\u001b[2;33m"
        elif value > 10666:
            return "\\u001b[2;35m"
        elif value >= 8533:
            return "\\u001b[2;34m"
        else: # 6400 이상
            return "\\u001b[2;32m"
    
    else: # 제/인/숙/체력/기타 특옵
        return "\\u001b[2;30m"

def quality_color(quality):
    if quality == 100:
        return "\\u001b[2;33m"
    elif quality >= 90:
        return "\\u001b[2;35m"
    elif quality >= 70:
        return "\\u001b[2;34m"
    else: # 40 초과
        return "\\u001b[2;32m"

RESET = "\\u001b[0m"
def formatted_discord_message(url, item, evaluation, debug=False):
    toSend  = "```ansi\\n\\u001b[2;31m\\u001b[2;40m" if evaluation['grade'] == "유물" else "```ansi\\n\\u001b[2;37m\\u001b[2;40m"
    toSend += f"{evaluation['grade']} {item['Name']}{RESET}\\n"
    
    if evaluation["type"] == "accessory": # 장신구
        toSend += f"품질 {quality_color(evaluation['quality'])}{evaluation['quality']}{RESET} 거래 {item['AuctionInfo']['TradeAllowCount']}회\\n"
        toSend += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        for opt in item["Options"]:
            if opt["OptionName"] == "깨달음":
                continue
            color, scale = accessory_option(opt)
            toSend += f"{color}{opt['OptionName']} {scale}{RESET} "

    else:  # 팔찌
        toSend += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        for opt in item["Options"]:
            if opt["OptionName"] == "도약":
                continue
            color = bracelet_option_color(opt, evaluation['grade'])
            toSend += f"{color}{opt['OptionName']} {int(opt['Value'])}{RESET} "
    
    toSend += f"\\n만료 {item['AuctionInfo']['EndDate']}\\n```"
    if debug:
        print(toSend)
    fire_webhook(url, toSend)