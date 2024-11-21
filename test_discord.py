import requests
from requests.structures import CaseInsensitiveDict

url = "https://discord.com/api/webhooks/1308811214674985011/DhmX8Stl3z8j22YBEwcErTY-w1r6l_zahCaBUMhIiXmpomfBFJhibEvh5sAJvZoS48rH?"

headers = CaseInsensitiveDict()
headers["Content-Type"] = "application/json"

data = """{"content":"```ansi\\n\\u001b[2;31m\\u001b[2;40m유물 엄숙한 결의의 반지\\u001b[0m\\n\\u001b[2;33m품질 100\\u001b[0m \\u001b[2;34m거래 1회\\u001b[0m\\n500골드 vs 15,000골드 (3.3%)\\n\\u001b[2;33m치피 상\\u001b[0m \\u001b[2;35m치적 중\\u001b[0m \\u001b[2;34m깡무공 하\\u001b[0m\\n2024-11-21T20:19:44.48 만료\\n```"}"""

resp = requests.post(url, headers=headers, data=data)

print(resp.status_code)
print(resp.text)
