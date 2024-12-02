import multiprocessing as mp
import requests
import json
import time
from queue import Empty
import os
import utils, async_price_collector


RESET = "\\u001b[0m"

def init_discord_manager(accept_queue):
    url = os.getenv("WEBHOOK2")
    readback_queue = mp.Queue()

    post_message(url, "경매장 모니터 시작", flags=1 << 12)
    p_reflex = mp.Process(target=message_reflex, args=(accept_queue, readback_queue, url))
    p_reflex.start()
    p_manager = mp.Process(target=discord_manager, args=(readback_queue, url))
    p_manager.start()

    def terminate():
        p_reflex.terminate()
        p_manager.terminate()
        post_message(url, "경매장 모니터 종료", flags=1 << 12)

    return terminate
    
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
        elif value >= 8533: # 8512 was green
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
    else:
        return "\\u001b[2;32m"

def send_discord_message(url, item, evaluation):
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
    post_message(url, return_str, wait=False)

def format_multiline_message(item, evaluation):

    toSend  = "```ansi\\n\\u001b[2;31m\\u001b[2;40m" if evaluation['grade'] == "유물" else "```ansi\\n\\u001b[2;37m\\u001b[2;40m"
    
    if evaluation["type"] == "accessory": # 장신구
        usage_type = evaluation["usage_type"]
        price_detail = evaluation["price_details"][usage_type]
        toSend += f"{evaluation['grade']} {item['Name']}{RESET} ({usage_type}: 특옵 가격 {price_detail["base_price"]:,}골드)\\n"
        toSend += f"품질 {quality_color(evaluation['quality'])}{evaluation['quality']}({price_detail["quality_adjustment"]:+,}골드){RESET} 거래 {item['AuctionInfo']['TradeAllowCount']}회({price_detail["trade_adjustment"]:+,}골드)\\n"
        toSend += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        options = []
        for opt in item["Options"]:
            if opt["OptionName"] == "깨달음":
                continue
            color, scale = accessory_option(opt)
            # 공통 옵션에 대한 가치 정보 추가
            if opt["OptionName"] in price_detail["options"]:
                opt_value = price_detail["options"][opt["OptionName"]]["price"]
                options.append(f"{color}{opt['OptionName']} {scale}({opt_value:+,}골드){RESET}")
            else:
                options.append(f"{color}{opt['OptionName']} {scale}{RESET}")
        toSend += " | ".join(options)

    else:  # 팔찌
        toSend += f"{evaluation['grade']} {item['Name']}{RESET}\\n"
        toSend += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        options = []
        for opt in item["Options"]:
            if opt["OptionName"] == "도약":
                continue
            color = bracelet_option_color(opt, evaluation['grade'])
            options.append(f"{color}{opt['OptionName']} {int(opt['Value'])}{RESET}")
        toSend += " | ".join(options)
    
    toSend += f"\\n만료 {item['AuctionInfo']['EndDate']}\\n```"
    return toSend

def post_message(url, content, flags=0, wait=True):
    headers = {"Content-Type": "application/json"}
    data = f"""{{"content": "{content}", "flags": {flags}}}"""
    host = url + "?wait=true" if wait else url
    
    response = requests.post(host, headers=headers, data=data)
    if wait: return json.loads(response.text)["id"]

def patch_message(url, message_id, content):
    headers = {"Content-Type": "application/json"}
    data = f"""{{"content": "{content}"}}"""
    
    requests.patch(url + f"/messages/{message_id}", headers=headers, data=data)

def create_search_query(item, evaluation):
    spg = async_price_collector.SearchPresetGenerator()
    
    preset = {}
    if "팔찌" in item["Name"]:
        preset['options'] = []
        for op in item["Options"]:
            if op["OptionName"] not in ["깨달음", "도약"]:
                if op["OptionName"] in ["특화", "신속", "치명", "제압", "인내", "숙련"]:
                    preset['options'].append(("전투 특성", op["OptionName"], int(op["Value"])))
                elif op["OptionName"] in ["힘", "민첩", "지능", "체력"]:
                    preset['options'].append(("팔찌 기본 효과", op["OptionName"], int(op["Value"])))
                elif op["OptionName"] == "부여 효과 수량":
                    preset['options'].append(("팔찌 옵션 수량", op["OptionName"], int(op["Value"])))
                else:
                    preset['options'].append(("팔찌 특수 효과", op["OptionName"], ""))
        data = spg.create_search_data_bracelet(preset, evaluation['grade'])
    else:
        preset['enhancement_level'] = evaluation['level']
        preset['quality'] = evaluation['quality']
        preset['options'] = [(op["OptionName"], utils.number_to_scale[op["OptionName"]][op["Value"]]) for op in item['Options'] if op["OptionName"] not in ["깨달음", "도약"]]
        data = spg.create_search_data_acc(preset, evaluation['grade'], item["Name"])
    
    return data

def check_existance(item, evaluation):
    headers = {"Content-Type": "application/json",
                "Authorization": "bearer " + os.getenv('API_TOKEN_CHECKER')}
    url = f"https://developer-lostark.game.onstove.com/auctions/items"
    data = create_search_query(item, evaluation)
    
    response = requests.post(url, headers=headers, json=data)

    if json.loads(response.text)["TotalCount"] > 0:
        current_price = json.loads(response.text)["Items"][0]["AuctionInfo"]["BuyPrice"]
        if current_price is not None and current_price <= evaluation['current_price']:
            return True
    return False

def message_reflex(accept_queue, readback_queue, url):
    while True:
        arg = accept_queue.get()
        toSend = format_multiline_message(*arg)
        message_id = post_message(url, toSend)
        readback_queue.put((*arg, message_id, toSend))

def discord_manager(queue, url):
    interesting_items = []
    while True:
        try:
            item, evaluation, message_id, message = queue.get(timeout=1)
            registered_time = time.time()
        except Empty:
            if len(interesting_items) > 0:
                item, evaluation, message_id, message, registered_time = interesting_items.pop()
            else:
                continue

        isExist = check_existance(item, evaluation)
        if isExist:
            if time.time() - registered_time > 600: # 10분동안 tracking
                patch_message(url, message_id, message.replace("만료", "[추적 종료됨] 만료"))
            else:
                interesting_items.insert(0, (item, evaluation, message_id, message, registered_time))
        else:
            patch_message(url, message_id, f"~~{message}~~")
