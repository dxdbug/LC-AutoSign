import requests
from requests.exceptions import RequestException
import hashlib
import json
import time
import random
import os
from datetime import datetime

# 设置时区为上海（北京时间）
os.environ['TZ'] = 'Asia/Shanghai'
if hasattr(time, 'tzset'):
    time.tzset()

# ================= 全局配置区 =================
GLOBAL_METHOD = "add.signon.item"
GLOBAL_STYPE = 1

MILWAUKEETOOL_TOKEN_LIST = os.getenv('MILWAUKEETOOL_TOKEN_LIST', '')
MILWAUKEETOOL_CLIENT_ID = os.getenv('MILWAUKEETOOL_CLIENT_ID', '')

# ========== 通知渠道：全部从环境变量读取 ==========
WECHAT_WEBHOOK_URL = os.getenv('WECHAT_WEBHOOK_URL', '')
DINGTALK_WEBHOOK_URL = os.getenv('DINGTALK_WEBHOOK_URL', '')
SERVERCHAN_SENDKEY = os.getenv('SERVERCHAN_SENDKEY', '')

FAILED_LOG = []
RESULT_LOG = []
FILTERED_LOG = []
POINT_LOG = []  # 积分日志

SHOW_RAW_RESPONSE = True

SECRET = "36affdc58f50e1035649abc808c22b48"
APPKEY = "76472358"
PLATFORM = "MP-WEIXIN"
FORMAT = "json"
URL = "https://service.milwaukeetool.cn/api/v1/signon"
POINT_URL = "https://service.milwaukeetool.cn/api/v1/user"

# ================= 防检测UA =================
def get_headers():
    chrome = random.randint(132, 136)
    xweb = random.randint(18960,19027)
    ua = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
        f"MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254173b) XWEB/{xweb}"
    )
    return {
        "Host": "service.milwaukeetool.cn",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": ua,
        "xweb_xhr": "1",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://servicewechat.com/wxc13e77b0a12aac68/5/page.html",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }

HEADERS = get_headers()

# ================= 签名 =================
def generate_sign(params_dict):
    sorted_keys = sorted(params_dict.keys())
    s = SECRET
    for key in sorted_keys:
        val = params_dict[key]
        if isinstance(val, bool):
            val = 1 if val else 0
        s += str(key) + str(val)
    s += SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest()

# ================= 查询总积分（最终正确版） =================
def get_user_point(token, client_id):
    try:
        payload = {
            "token": token,
            "client_id": client_id,
            "appkey": APPKEY,
            "format": FORMAT,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "platform": PLATFORM,
            "method": "get.user.point"  # <--- 关键！换成这个
        }
        payload["sign"] = generate_sign(payload)
        
        time.sleep(0.8)
        resp = requests.post(POINT_URL, headers=HEADERS, json=payload, timeout=10)
        data = resp.json()
        
        print(f"【积分接口返回】: {json.dumps(data, ensure_ascii=False)}")
        
        if data.get("status") == 200:
            point_data = data.get("data", {})
            # 真实字段：
            total_point = point_data.get("total_point", 0)
            available_point = point_data.get("available_point", 0)
            return total_point, available_point
        return 0, 0
    except Exception as e:
        print(f"积分查询异常：{e}")
        return 0, 0
# ================= 签到状态格式化 =================
def format_sign_status(json_data, client_id=None):
    try:
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        if data.get('status') != 200:
            cid = f" | client_id: {client_id}" if client_id is not None else ""
            return f"❌ 错误：API 回应异常 (状态码: {data.get('status')}){cid}"

        sign_data = data.get('data', {})
        sign_status = sign_data.get('SigninStatus', 0)
        sign_count = sign_data.get('signcount', 0)
        items = sign_data.get('items', [])
        send_num = sign_data.get('send_num', 0)
        used_num = sign_data.get('used_num', 0)
        available_num = sign_data.get('available_send_num', 0)

        output = []
        output.append("=" * 50)
        output.append(" 📋 签到系统状态报告 ".center(48, "="))
        output.append("=" * 50)
        output.append("")

        status_text = "✅ 已签到" if sign_status == 1 else "❌ 未签到"
        output.append("【基本资讯】")
        if client_id is not None:
            output.append(f"  🆔 client_id：{client_id}")
        output.append(f"  🔐 签到状态：{status_text}")
        output.append(f"  📊 连续签到：{sign_count} 天")
        output.append(f"  📅 签到总数：{len(items)} 天")
        output.append("")

        if items:
            output.append("【签到记录】")
            sorted_items = sorted(items)
            for date in sorted_items:
                output.append(f"  📆 {date} ✅")
        else:
            output.append("【签到记录】")
            output.append("  📭 暂无签到记录")

        output.append("")
        output.append("【使用统计】")
        output.append(f"  📤 今日发送：{send_num}")
        output.append(f"  📥 今日使用：{used_num}")
        output.append(f"  💾 可用积分：{available_num}")
        output.append("")
        output.append("=" * 50)
        output.append(f" 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("=" * 50)

        return "\n".join(output)

    except Exception as e:
        return f"❌ 格式化错误：{str(e)}"

# ================= 企业微信通知 =================
def send_wechat_notification(failed_accounts, total_count, success_count):
    if not WECHAT_WEBHOOK_URL or WECHAT_WEBHOOK_URL.strip() == "":
        print("\n⚠️  未配置企业微信机器人，跳过")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"
    account_details = "\n\n📋 账号详情：\n" + "\n".join(FILTERED_LOG) if FILTERED_LOG else ""
    point_details = "\n\n💰 积分汇总：\n" + "\n".join(POINT_LOG) if POINT_LOG else ""

    content = (
        f"🤖 Milwaukee 签到报告\n"
        f"📅 时间: {now_str}\n"
        f"--------------------------\n"
        f"✅ 成功: {success_count} 个\n"
        f"❌ 失败: {len(failed_accounts)} 个\n"
        f"📦 总数: {total_count} 个\n"
        f"--------------------------\n"
        f"⚠️ 失败详情:\n{fail_details}"
        f"{account_details}"
        f"{point_details}"
    )

    payload = {"msgtype": "text", "text": {"content": content}}
    try:
        resp = requests.post(WECHAT_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("✅ 企业微信通知成功")
    except:
        print("❌ 企业微信通知失败")

# ================= 钉钉通知 =================
def send_dingtalk_notification(failed_accounts, total_count, success_count):
    if not DINGTALK_WEBHOOK_URL or DINGTALK_WEBHOOK_URL.strip() == "":
        print("\n⚠️  未配置钉钉机器人，跳过")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"
    all_detail = "\n\n".join(FILTERED_LOG + POINT_LOG) if (FILTERED_LOG + POINT_LOG) else "无详情"

    text = (
        f"### Milwaukee 签到结果\n"
        f"**时间**：{now_str}\n\n"
        f"✅ 成功：{success_count}/{total_count}\n"
        f"❌ 失败：{len(failed_accounts)}/{total_count}\n\n"
        f"**失败详情**：\n{fail_details}\n\n"
        f"**详情**：\n{all_detail[:1800]}"
    )

    msg = {
        "msgtype": "markdown",
        "markdown": {"title": "Milwaukee签到", "text": text}
    }

    try:
        resp = requests.post(DINGTALK_WEBHOOK_URL, json=msg, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("✅ 钉钉通知成功")
    except:
        print("❌ 钉钉通知失败")

# ================= Server酱通知 =================
def send_msg_by_server(send_key, title, content):
    if not send_key:
        print("📤 未配置Server酱")
        return
    push_url = f'https://sctapi.ftqq.com/{send_key}.send'
    data = {'text': title, 'desp': content}
    try:
        requests.post(push_url, data=data, timeout=10)
        print("✅ Server酱推送成功")
    except:
        print("❌ Server酱推送失败")

# ================= 签到主逻辑 =================
def signAndList(token, client_id, account_index=1):
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "token": token,
        "client_id": client_id,
        "appkey": APPKEY,
        "format": FORMAT,
        "timestamp": timestamp_str,
        "platform": PLATFORM,
        "method": GLOBAL_METHOD
    }

    if GLOBAL_METHOD == "add.signon.item":
        payload["year"] = str(now.year)
        payload["month"] = str(now.month)
        payload["day"] = str(now.day)
        payload["stype"] = GLOBAL_STYPE

    payload["sign"] = generate_sign(payload)

    try:
        time.sleep(random.uniform(1.0, 2.5))
        response = requests.post(URL, headers=HEADERS, json=payload, timeout=10)
        resp_json = response.json()
        code = resp_json.get("code")
        msg = resp_json.get("msg", "") or resp_json.get("message", "")
        is_success = code == 200 or "成功" in msg or "已签到" in msg

        # 查询积分（已修复）
        total_point, available_point = get_user_point(token, client_id)
        point_line = f"【账号 {account_index}】{client_id}\n💰 总积分：{total_point} | 可用积分：{available_point}"
        POINT_LOG.append(point_line)

        # 记录日志
        result_line = f"【账号 {account_index}】{client_id}\n{'✅ 成功' if is_success else '❌ 失败'} | {msg}"
        RESULT_LOG.append(result_line)
        FILTERED_LOG.append(result_line)

        if is_success:
            print(f"✅ 成功 | {msg}")
            print(f"💰 总积分：{total_point} | 可用积分：{available_point}")
            time.sleep(1)
            payload2 = {
                "token": token, "client_id": client_id, "appkey": APPKEY,
                "format": FORMAT, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": PLATFORM, "method": "get.signon.list"
            }
            payload2["sign"] = generate_sign(payload2)
            resp2 = requests.post(URL, headers=HEADERS, json=payload2, timeout=10)
            print(format_sign_status(resp2.json(), client_id))
            return True
        else:
            print(f"❌ 失败 | {msg}")
            FAILED_LOG.append((client_id, msg))
            return False

    except Exception as e:
        err = f"异常：{str(e)}"
        print(f"❌ {err}")
        RESULT_LOG.append(f"【账号 {account_index}】{client_id} | {err}")
        FAILED_LOG.append((client_id, err))
        return False

# ================= 账号处理 =================
def processAccount():
    tokenList = [t.strip() for t in MILWAUKEETOOL_TOKEN_LIST.split(',') if t.strip()]
    clientIdList = [cid.strip() for cid in MILWAUKEETOOL_CLIENT_ID.split(',') if cid.strip()]
    if not tokenList or not clientIdList:
        print("❌ 缺少账号信息")
        return 0, 0
    min_len = min(len(tokenList), len(clientIdList))
    success = 0
    for i, (token, cid) in enumerate(zip(tokenList, clientIdList), 1):
        print(f"\n📌 账号 {i}/{min_len} | {cid}")
        if signAndList(token, cid, i):
            success += 1
    return success, min_len

# ================= 主函数 =================
def main():
    global FAILED_LOG, RESULT_LOG, FILTERED_LOG, POINT_LOG
    FAILED_LOG = []
    RESULT_LOG = []
    FILTERED_LOG = []
    POINT_LOG = []

    print("=" * 60)
    print("🚀 Milwaukee 签到脚本（积分修复版）")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    success_cnt, total_cnt = processAccount()

    # 发送通知
    content = "\n\n".join(FILTERED_LOG + POINT_LOG) if (FILTERED_LOG + POINT_LOG) else "无结果"
    send_msg_by_server(SERVERCHAN_SENDKEY, "Milwaukee 签到完成", content)
    send_wechat_notification(FAILED_LOG, total_cnt, success_cnt)
    send_dingtalk_notification(FAILED_LOG, total_cnt, success_cnt)

    print("\n" + "=" * 60)
    print(f"🏁 任务完成 | 成功 {success_cnt}/{total_cnt} | 失败 {len(FAILED_LOG)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
