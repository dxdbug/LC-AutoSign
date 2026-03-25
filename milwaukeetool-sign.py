import requests
from requests.exceptions import RequestException
import hashlib
import json
import time
import random
import os
from datetime import datetime, timedelta

# ===================== 时区：固定北京时间 =====================
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
SEND_ALL_NOTICE = True
SHOW_RAW_RESPONSE = True

SECRET = "36affdc58f50e1035649abc808c22b48"
APPKEY = "76472358"
PLATFORM = "MP-WEIXIN"
FORMAT = "json"
URL = "https://service.milwaukeetool.cn/api/v1/signon"
POINT_URL = "https://service.milwaukeetool.cn/api/v1/user"

# ================= 时间配置文件（自动记录） =====================
TIME_FILE = "last_run_hour.txt"

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

# ================= 积分查询 =================
def get_points(token, client_id):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "token": token,
            "client_id": client_id,
            "appkey": APPKEY,
            "format": FORMAT,
            "timestamp": ts,
            "platform": PLATFORM,
            "method": "get.user.info"
        }
        payload["sign"] = generate_sign(payload)
        res = requests.post(POINT_URL, headers=HEADERS, json=payload, timeout=10)
        data = res.json()
        return int(data.get("data", {}).get("points", 0))
    except Exception as e:
        print(f"[积分查询异常] {e}")
        return -1

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
        print("\n⚠️  未配置环境变量 WECHAT_WEBHOOK_URL，跳过企业微信推送")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"
    account_details = ""
    if FILTERED_LOG:
        account_details = "\n\n📋 账号签到详情：\n" + "\n".join(FILTERED_LOG)

    content = (
        f"🤖 Milwaukee 签到任务执行报告\n"
        f"📅 时间: {now_str}\n"
        f"--------------------------\n"
        f"✅ 成功: {success_count} 个\n"
        f"❌ 失败: {len(failed_accounts)} 个\n"
        f"📦 总数: {total_count} 个\n"
        f"--------------------------\n"
        f"⚠️ 失败详情:\n{fail_details}"
        f"{account_details}"
    )

    payload = {"msgtype": "text", "text": {"content": content}}
    try:
        resp = requests.post(WECHAT_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("\n✅ 企业微信通知发送成功")
        else:
            print(f"\n❌ 企业微信通知失败: {resp.text}")
    except Exception as e:
        print(f"\n❌ 企业微信发送异常: {str(e)}")

# ================= 钉钉通知 =================
def send_dingtalk_notification(failed_accounts, total_count, success_count, all_result):
    if not DINGTALK_WEBHOOK_URL or DINGTALK_WEBHOOK_URL.strip() == "":
        print("\n⚠️  未配置环境变量 DINGTALK_WEBHOOK_URL，跳过钉钉推送")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"
    filtered_result = "\n\n".join(FILTERED_LOG) if FILTERED_LOG else "无需要推送的账号"

    text = (
        f"### Milwaukee 签到结果\n"
        f"**时间**：{now_str}\n\n"
        f"✅ 成功：{success_count}/{total_count}\n"
        f"❌ 失败：{len(failed_accounts)}/{total_count}\n\n"
        f"**失败详情**：\n{fail_details}\n\n"
        f"**完整结果**：\n{filtered_result[:1500]}..."
    )

    msg = {"msgtype": "markdown", "markdown": {"title": "Milwaukee签到通知", "text": text}}
    try:
        resp = requests.post(DINGTALK_WEBHOOK_URL, json=msg, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("✅ 钉钉通知发送成功")
        else:
            print(f"❌ 钉钉通知失败: {resp.text}")
    except Exception as e:
        print(f"❌ 钉钉发送异常: {str(e)}")

# ================= Server酱通知 =================
def send_msg_by_server(send_key, title, content):
    push_url = f'https://sctapi.ftqq.com/{send_key}.send'
    data = {'text': title, 'desp': content}
    try:
        response = requests.post(push_url, data=data, timeout=10)
        return response.json()
    except RequestException:
        return None

# ================= 签到主逻辑 =================
def signAndList(token, client_id, account_index=1):
    before = get_points(token, client_id)
    time.sleep(random.uniform(0.5, 1))

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
        delay = random.uniform(1.0, 2.5)
        print(f"      ⏳ 等待 {delay:.1f}s...")
        time.sleep(delay)

        response = requests.post(URL, headers=HEADERS, json=payload, timeout=10)
        resp_json = response.json()
        code = resp_json.get("code")
        msg = resp_json.get("msg", "") or resp_json.get("message", "") or str(resp_json)
        is_success = code == 200 or "成功" in msg or "已签到" in msg

        after = get_points(token, client_id)
        msg += f" | 签到前积分：{before} | 签到后积分：{after}"

        if is_success and before == after and before != -1:
            print(f"✅ 账号{account_index}：已签到，积分无变化，不推送")
            RESULT_LOG.append(f"【账号 {account_index}】client_id: {client_id}\n结果：✅ 成功\n信息：{msg} | 备注：积分无变化")
        else:
            print(f"✅ 账号{account_index}：正常推送")
            line = f"【账号 {account_index}】client_id: {client_id}\n结果：{'✅ 成功' if is_success else '❌ 失败'}\n信息：{msg}"
            RESULT_LOG.append(line)
            FILTERED_LOG.append(line)

        if is_success:
            print(f"      ✅ 结果: 成功 | {msg}")
            if SHOW_RAW_RESPONSE:
                print(f"      └─ 返回: {json.dumps(resp_json, ensure_ascii=False)}")

            print("\n📢 检查签到记录")
            time.sleep(random.uniform(1.0, 2.5))
            p2 = {
                "token": token, "client_id": client_id, "appkey": APPKEY,
                "format": FORMAT, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": PLATFORM, "method": "get.signon.list"
            }
            p2["sign"] = generate_sign(p2)
            r2 = requests.post(URL, headers=HEADERS, json=p2, timeout=20)
            print(format_sign_status(r2.json(), client_id))
            return True
        else:
            print(f"      ❌ 失败 | {msg}")
            FAILED_LOG.append((client_id, msg))
            return False

    except Exception as e:
        err = f"异常：{str(e)}"
        print(f"      ❌ {err}")
        line = f"【账号 {account_index}】client_id: {client_id}\n{err}"
        RESULT_LOG.append(line)
        FILTERED_LOG.append(line)
        FAILED_LOG.append((client_id, err))
        return False

# ================= 处理账号 =================
def processAccount():
    tokenList = [t.strip() for t in MILWAUKEETOOL_TOKEN_LIST.split(',') if t.strip()]
    clientIdList = [cid.strip() for cid in MILWAUKEETOOL_CLIENT_ID.split(',') if cid.strip()]
    if not tokenList or not clientIdList:
        print("❌ 缺少 token 或 client_id")
        FAILED_LOG.append(("config", "缺少账号信息"))
        return 0, 0
    n = min(len(tokenList), len(clientIdList))
    success = 0
    for i, (t, cid) in enumerate(zip(tokenList[:n], clientIdList[:n]), 1):
        print(f"\n{'─'*50}\n📌 账号 {i}/{n} | {cid}\n{'─'*50}")
        if signAndList(t, cid, i):
            success += 1
    return success, n

# ================= 通知 =================
def sendNotification():
    if not FILTERED_LOG:
        print("\n🔇 无变化，跳过推送")
        return
    if not SERVERCHAN_SENDKEY:
        print("📤 未配置 SERVERCHAN_SENDKEY")
        return
    content = "\n\n".join(FILTERED_LOG)
    for k in [SERVERCHAN_SENDKEY.strip()]:
        ret = send_msg_by_server(k, "Milwaukee 签到结果（仅推送变化）", content)
        if ret and ret.get("code") == 0:
            print("✅ Server酱推送成功")
        else:
            print("❌ Server酱推送失败")

# ===================== 核心：时间控制逻辑（你要的功能） =====================
def check_and_wait_run_time():
    now = datetime.now()
    current_hour = now.hour

    # 读取上次运行的小时
    last_hour = 9
    if os.path.exists(TIME_FILE):
        try:
            with open(TIME_FILE, "r", encoding="utf-8") as f:
                last_hour = int(f.read().strip())
        except:
            last_hour = 9

    # 今天应该运行的小时：上次 +1，最大 17，最小 9
    run_hour = last_hour + 1
    if run_hour > 17:
        run_hour = 9

    # 保存下次使用
    with open(TIME_FILE, "w", encoding="utf-8") as f:
        f.write(str(run_hour))

    print(f"⏰ 计划运行时间：北京时间 {run_hour}:00 左右")
    print(f"⏳ 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 只在 9-17 点运行
    while True:
        now = datetime.now()
        h = now.hour
        if 9 <= h <= 17:
            print("✅ 在 9-17 点范围内，开始执行签到")
            break
        print(f"⏳ 不在 9-17 点，等待中... 当前：{h}点")
        time.sleep(60)

# ================= 主函数 =================
def main():
    global FILTERED_LOG, SEND_ALL_NOTICE
    FILTERED_LOG = []
    SEND_ALL_NOTICE = True

    # ========== 启用时间控制 ==========
    check_and_wait_run_time()

    print("=" * 60)
    print("🚀 Milwaukee 自动签到（每日延迟1小时版）")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    success_cnt, total_cnt = processAccount()
    all_result_str = "\n\n".join(RESULT_LOG)

    if not FILTERED_LOG:
        SEND_ALL_NOTICE = False
        print("\n🔇 所有账号无变化，不推送")

    if SEND_ALL_NOTICE:
        sendNotification()
        send_wechat_notification(FAILED_LOG, total_cnt, success_cnt)
        send_dingtalk_notification(FAILED_LOG, total_cnt, success_cnt, all_result_str)

    print("\n" + "=" * 60)
    print(f"🏁 完成 | 成功 {success_cnt}/{total_cnt} | 失败 {len(FAILED_LOG)} | 需推送 {len(FILTERED_LOG)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
