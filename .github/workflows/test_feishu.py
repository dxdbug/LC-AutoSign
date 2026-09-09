import requests
import json

FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/f7f07bdf-4c5b-485b-bf43-d3b45c3ae36f"

payload = {
    "msg_type": "text",
    "content": {
        "text": "嘉立创签到测试消息"
    }
}
headers = {"Content-Type": "application/json;charset=utf-8"}
resp = requests.post(FEISHU_WEBHOOK_URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, timeout=15)
print("status_code:", resp.status_code)
print("response body:", resp.text)
