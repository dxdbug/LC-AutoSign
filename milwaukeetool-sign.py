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
    time.tzset()  # 生效时区设置（兼容Linux系统，GitHub Actions用的是Linux）

# ================= 全局配置区 =================
GLOBAL_METHOD = "add.signon.item"
GLOBAL_STYPE = 1

MILWAUKEETOOL_TOKEN_LIST = os.getenv('MILWAUKEETOOL_TOKEN_LIST', '')
MILWAUKEETOOL_CLIENT_ID = os.getenv('MILWAUKEETOOL_CLIENT_ID', '')

# ========== 通知渠道：全部从环境变量读取 ==========
WECHAT_WEBHOOK_URL = os.getenv('WECHAT_WEBHOOK_URL', '')
DINGTALK_WEBHOOK_URL = os.getenv('DINGTALK_WEBHOOK_URL', '')

FAILED_LOG = []
RESULT_LOG = []
FILTERED_LOG = []  # 存储需要推送的日志
SEND_ALL_NOTICE = True  # 核心开关：是否发起通知请求

SHOW_RAW_RESPONSE = True

SECRET = "36affdc58f50e1035649abc808c22b48"
APPKEY = "76472358"
PLATFORM = "MP-WEIXIN"
FORMAT = "json"
URL = "https://service.milwaukeetool.cn/api/v1/signon"
POINT_URL = "https://service.milwaukeetool.cn/api/v1/user"  # 积分接口


# ================= 防检测UA（你原版基础微改） =================
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


# ================= 签名（你原版，完全不动） =================
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


# ================= 积分查询（只加这个，极简） =================
def get_points(token, client_id):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "token": token, "client_id": client_id, "appkey": APPKEY,
            "format": FORMAT, "timestamp": ts, "platform": PLATFORM,
            "method": "get.user.item"
        }
        payload["sign"] = generate_sign(payload)
        res = requests.post(POINT_URL, headers=HEADERS, json=payload, timeout=10)
        data = res.json()
        return int(data.get("data", {}).get("get_user_money", {}).get("points", 0))
    except:
        return -1


# ================= 你原版格式函数，完全不动 =================
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
        send_num = sign_data.get('reward_points', 0)
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
        output.append(f"  📤 今日获得：{send_num}")
        output.append(f"  📥 今日使用：{used_num}")
        output.append(f"  💾 可用积分：{available_num}")
        output.append("")
        output.append("=" * 50)
        output.append(f" 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("=" * 50)

        return "\n".join(output)

    except Exception as e:
        return f"❌ 格式化错误：{str(e)}"


# ================= 你原版企业微信，保留完整逻辑 =================
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

    payload = {
        "msgtype": "text",
        "text": {"content": content}
    }

    try:
        resp = requests.post(WECHAT_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("\n✅ 企业微信通知发送成功")
        else:
            print(f"\n❌ 企业微信通知失败: {resp.text}")
    except Exception as e:
        print(f"\n❌ 企业微信发送异常: {str(e)}")


# ================= 你原版钉钉，保留完整逻辑 =================
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

    msg = {
        "msgtype": "markdown",
        "markdown": {
            "title": "Milwaukee签到通知",
            "text": text
        }
    }

    try:
        resp = requests.post(DINGTALK_WEBHOOK_URL, json=msg, timeout=5)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print("✅ 钉钉通知发送成功")
        else:
            print(f"❌ 钉钉通知失败: {resp.text}")
    except Exception as e:
        print(f"❌ 钉钉发送异常: {str(e)}")


# ================= 签到主逻辑（单个账号积分判断） =================
def signAndList(token, client_id, account_index=1):
    # 签到前查积分
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

    sign_val = generate_sign(payload)
    payload["sign"] = sign_val

    try:
        delay = random.uniform(1.0, 2.5)
        print(f"      ⏳ 等待 {delay:.1f}s...")
        time.sleep(delay)

        response = requests.post(URL, headers=HEADERS, json=payload, timeout=10)
        resp_json = response.json()

        # ========== ✅ 终极修复：已签到 = 成功，不算失败 ==========
        status = resp_json.get("status")
        msg = resp_json.get("message", "")
        
        # 核心规则：只要 message 包含“已签到”，一律视为成功
        is_success = (status == 200) or ("已签到" in msg)
        # ======================================================

        # 签到后查积分
        after = get_points(token, client_id)
        # ============== 新增：计算本次签到获得积分 ==============
        reward_points = after - before  # 本次获得积分
        # ======================================================
        # 优化日志展示，增加本次获得积分项
        msg += f" | 获得：{reward_points} | 总分：{after}"

        # 积分判断
        point_increased = (after > before) and (before != -1)
        already_signed = "已签到" in msg  # 直接判断文案
        real_failed = not is_success

        # 推送规则（你要的最终版）
        need_push = False
        if already_signed:
            print(f"✅ 账号{account_index}：今日已签到 → 不推送")
        elif is_success and point_increased:
            print(f"✅ 账号{account_index}：签到成功，积分增加 → 推送")
            need_push = True
        else:
            print(f"❌ 账号{account_index}：签到失败 → 推送")
            need_push = True

        # 日志展示（已签到 = ✅ 绝不是 ❌）
        if already_signed:
            result_line = f"【账号 {account_index}】 {client_id}\n✅ 已签到\n{msg}"
        else:
            result_line = f"【账号 {account_index}】 {client_id}\n{'✅ 成功' if is_success else '❌ 失败'}\n{msg}"

        RESULT_LOG.append(result_line)
        if need_push:
            FILTERED_LOG.append(result_line)

        # 只有真正失败才加入失败列表
        if real_failed and not already_signed:
            FAILED_LOG.append((client_id, msg))

        # 控制台输出
        if already_signed:
            print(f"      ✅ 结果: 成功 | {msg}")
        elif is_success:
            print(f"      ✅ 结果: 成功 | {msg}")
        else:
            print(f"      ❌ 结果: 失败 | {msg}")

        if SHOW_RAW_RESPONSE:
            print(f"      └─ 返回: {json.dumps(resp_json, ensure_ascii=False)}")

        # 成功/已签到 都执行查询
        if is_success:
            print("\n📢 开始检查签到天数")
            time.sleep(random.uniform(1.0, 2.5))
            payload2 = {
                "token": token,
                "client_id": client_id,
                "appkey": APPKEY,
                "format": FORMAT,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": PLATFORM,
                "method": "get.signon.list"
            }
            payload2["sign"] = generate_sign(payload2)
            resp2 = requests.post(URL, headers=HEADERS, json=payload2, timeout=20)
            signResult = format_sign_status(resp2.json(), client_id=client_id)
            print(signResult)

        return is_success

    except Exception as e:
        err = f"异常：{str(e)}"
        print(f"      ❌ 账号{account_index}：{err}")
        result_line = f"【账号 {account_index}】client_id: {client_id}\n结果：❌ 异常\n信息：{err}"
        RESULT_LOG.append(result_line)
        FILTERED_LOG.append(result_line)
        FAILED_LOG.append((client_id, err))
        return False
        
# ================= 你原版账号处理，不动 =================
def processAccount():
    tokenList = [t.strip() for t in MILWAUKEETOOL_TOKEN_LIST.split(',') if t.strip()]
    clientIdList = [cid.strip() for cid in MILWAUKEETOOL_CLIENT_ID.split(',') if cid.strip()]

    if not tokenList or not clientIdList:
        print("❌ 缺少 token 或 client_id")
        FAILED_LOG.append(("config", "缺少账号信息"))
        return 0, 0

    min_len = min(len(tokenList), len(clientIdList))
    tokenList = tokenList[:min_len]
    clientIdList = clientIdList[:min_len]

    print(f"🔧 共 {min_len} 个账号")

    success = 0
    for i, (token, cid) in enumerate(zip(tokenList, clientIdList), 1):
        print(f"\n{'─' * 50}")
        print(f"📌 账号 {i}/{min_len} | {cid}")
        print('─' * 50)
        if signAndList(token, cid, i):
            success += 1
    return success, min_len


# ================= 通知逻辑：使用过滤后的日志 =================
def sendNotification():
    if not FILTERED_LOG:
        print("\n🔇 所有账号积分均无变化，跳过Server酱推送")
        return

    if not RESULT_LOG:
        RESULT_LOG.append("本次执行无任何账号返回信息")

    keys = [SERVERCHAN_SENDKEY.strip()]
    if not keys or not keys[0]:
        print("📤 未配置 SERVERCHAN_SENDKEY")
        return

    content = "\n\n".join(FILTERED_LOG)
    print(f"📤 准备推送需要通知的账号...")

    for key in keys:
        ret = send_msg_by_server(key, "Milwaukee 签到结果（仅推送积分变化账号）", content)
        if ret and ret.get("code") == 0:
            print(f"✅ Server酱推送成功")
        else:
            print(f"❌ Server酱推送失败")


# ================= 主函数（核心：控制是否发送所有通知） =================
def main():
    global FILTERED_LOG, SEND_ALL_NOTICE
    FILTERED_LOG = []
    SEND_ALL_NOTICE = True  # 初始化通知开关

    print("=" * 60)
    print("🚀 Milwaukee 签到（最终版：积分不变不发通知）")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    success_cnt, total_cnt = processAccount()
    all_result_str = "\n\n".join(RESULT_LOG)
    
    # 核心判断：无需要推送的账号则关闭所有通知
    if not FILTERED_LOG:
        SEND_ALL_NOTICE = False
        print("\n🔇 所有账号积分均无变化，关闭所有通知渠道")
    else:
        SEND_ALL_NOTICE = True

    # 仅当需要推送时才调用通知函数
    if SEND_ALL_NOTICE:
        sendNotification()
        send_wechat_notification(FAILED_LOG, total_cnt, success_cnt, all_result_str)
        send_dingtalk_notification(FAILED_LOG, total_cnt, success_cnt, all_result_str)
    else:
        print("\n🔇 跳过所有通知推送（企业微信/钉钉）")

    print("\n" + "=" * 60)
    print(f"🏁 完成 | 成功 {success_cnt}/{total_cnt} | 失败 {len(FAILED_LOG)} | 需推送账号 {len(FILTERED_LOG)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
