import requests
from requests.exceptions import RequestException, JSONDecodeError, Timeout, ConnectionError
import json
import hashlib
import time
import random
import os
from datetime import datetime

# ================= 全局配置区 =================
GLOBAL_METHOD = "add.signon.item"
GLOBAL_STYPE = 1

# 环境变量读取（适配 GitHub Actions Secrets）
MILWAUKEETOOL_TOKEN_LIST = os.getenv('MILWAUKEETOOL_TOKEN_LIST', '')
MILWAUKEETOOL_CLIENT_ID = os.getenv('MILWAUKEETOOL_CLIENT_ID', '')
SEND_KEY_LIST = os.getenv('SEND_KEY_LIST', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
# 👇 移除钉钉环境变量读取，改为直接配置
SHOW_RAW_RESPONSE = True

# ========== 钉钉配置（直接写在代码中） ==========
# 请在这里替换为你的实际钉钉Webhook地址和加签密钥
# 格式说明：
# 1. 不加签：直接填Webhook地址，DINGTALK_SECRET留空
# 2. 加签：DINGTALK_WEBHOOK填基础地址，DINGTALK_SECRET填加签密钥
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=8feae4728efa754660cf55c4e9b115202a7a22918e11a8f8c8f1d37b7bd5d856"
DINGTALK_SECRET = "你的钉钉加签密钥（没有则留空）"

FAILED_LOG = []
RESULT_LOG = []

# 固定配置（建议也可移到 Secrets 中）
SECRET = "36affdc58f50e1035649abc808c22b48"
APPKEY = "76472358"
PLATFORM = "MP-WEIXIN"
FORMAT = "json"
URL = "https://service.milwaukeetool.cn/api/v1/signon"

HEADERS = {
    "Host": "service.milwaukeetool.cn",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541739) XWEB/19027",
    "xweb_xhr": "1",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wxc13e77b0a12aac68/59/page-frame.html",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9"
}


def generate_sign(params_dict):
    """生成API签名（核心函数）"""
    try:
        sorted_keys = sorted(params_dict.keys())
        s = SECRET
        for key in sorted_keys:
            val = params_dict[key]
            # 布尔值转换
            if isinstance(val, bool):
                val = 1 if val else 0
            # 空值处理
            elif val is None:
                val = ""
            s += str(key) + str(val)
        s += SECRET
        return hashlib.md5(s.encode('utf-8')).hexdigest()
    except Exception as e:
        print(f"⚠️  签名生成失败: {str(e)}")
        return ""


def format_sign_status(json_data, client_id=None):
    """格式化签到状态返回信息"""
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
        output.append("【基本信息】")
        if client_id is not None:
            output.append(f"  🆔 client_id：{client_id}")
        output.append(f"  🔐 签到状态：{status_text}")
        output.append(f"  📊 连续签到：{sign_count} 天")
        output.append(f"  📅 签到总数：{len(items)} 天")
        output.append("")

        if items:
            output.append("【签到记录】")
            sorted_items = sorted(items)
            # 只显示最近10条记录，避免过长
            for date in sorted_items[-10:]:
                output.append(f"  📆 {date} ✅")
            if len(sorted_items) > 10:
                output.append(f"  📜 更早 {len(sorted_items)-10} 条记录未显示")
        else:
            output.append("【签到记录】")
            output.append("  📭 暂无签到记录")

        output.append("")
        output.append("【使用统计】")
        output.append(f"  📤 今日发送：{send_num}")
        output.append(f"  📥 今日使用：{used_num}")
        output.append(f"  💾 可用额度：{available_num}")
        output.append("")
        output.append("=" * 50)
        output.append(f" 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("=" * 50)

        return "\n".join(output)

    except Exception as e:
        return f"❌ 格式化错误：{str(e)}"


def send_http_request(url, payload, headers=None, timeout=10):
    """封装HTTP请求，统一异常处理"""
    headers = headers or HEADERS
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()  # 抛出HTTP错误
        return True, response
    except Timeout:
        return False, "请求超时"
    except ConnectionError:
        return False, "网络连接失败"
    except RequestException as e:
        return False, f"HTTP请求错误: {str(e)}"
    except Exception as e:
        return False, f"未知请求错误: {str(e)}"


# ========== 企业微信通知 ==========
def send_wechat_notification(failed_accounts, total_count, success_count):
    if not WEBHOOK_URL or WEBHOOK_URL.strip() == "":
        print("\n⚠️  未配置企业微信Webhook")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason[:100]}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"

    # 内容长度限制
    content = (
        f"🤖 Milwaukee 签到任务执行报告\n"
        f"📅 时间: {now_str}\n"
        f"--------------------------\n"
        f"✅ 成功: {success_count} 个\n"
        f"❌ 失败: {len(failed_accounts)} 个\n"
        f"📦 总数: {total_count} 个\n"
        f"--------------------------\n"
        f"⚠️ 失败详情:\n{fail_details}"
    )[:2000]  # 企业微信内容长度限制

    payload = {
        "msgtype": "text",
        "text": {"content": content}
    }

    success, resp = send_http_request(WEBHOOK_URL, payload)
    if success and resp.status_code == 200 and resp.json().get("errcode") == 0:
        print("\n📢 企业微信通知发送成功")
    else:
        print(f"\n⚠️  企业微信通知失败: {resp}")


# ========== 钉钉机器人通知（修改版：直接读取代码内配置） ==========
import hmac
import base64
from urllib.parse import quote_plus

def send_dingtalk_notification(failed_accounts, total_count, success_count, all_result):
    # 👇 修改：从代码内配置读取，不再读环境变量
    if not DINGTALK_WEBHOOK or DINGTALK_WEBHOOK.strip() == "":
        print("\n⚠️  未配置钉钉Webhook（代码内）")
        return

    # 👇 修改：直接使用代码内的配置
    webhook_url = DINGTALK_WEBHOOK.strip()
    secret = DINGTALK_SECRET.strip()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fail_details = "\n".join([f"• {cid}: {reason[:100]}" for cid, reason in failed_accounts]) if failed_accounts else "无失败"
    all_result_content = all_result[:1000] if all_result else "无返回信息"

    # 钉钉markdown格式优化 + 长度限制
    text = (
        f"### Milwaukee 签到结果\n"
        f"**时间**：{now_str}\n\n"
        f"✅ 成功：{success_count}/{total_count}\n"
        f"❌ 失败：{len(failed_accounts)}/{total_count}\n\n"
        f"**失败详情**：\n{fail_details}\n\n"
        f"**完整结果**：\n{all_result_content}..."
    )[:2000]  # 钉钉内容长度限制

    msg = {
        "msgtype": "markdown",
        "markdown": {
            "title": "Milwaukee签到通知",
            "text": text
        }
    }

    # 处理加签逻辑
    headers = {"Content-Type": "application/json"}
    if secret:
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = f"{timestamp}\n{secret}"
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = quote_plus(base64.b64encode(hmac_code))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    try:
        print(f"\n📤 钉钉推送URL：{webhook_url[:50]}...")
        print(f"📤 钉钉推送内容：{text[:100]}...")
        
        success, resp = send_http_request(webhook_url, msg, headers, timeout=10)
        
        if success:
            resp_json = resp.json()
            if resp_json.get("errcode") == 0:
                print("✅ 钉钉通知发送成功")
            else:
                print(f"❌ 钉钉通知失败：{resp_json.get('errmsg', '未知错误')}")
        else:
            print(f"❌ 钉钉通知失败：{resp}")
    except Exception as e:
        print(f"❌ 钉钉发送异常：{str(e)}")


# ========== Server酱 ==========
def send_msg_by_server(send_key, title, content):
    push_url = f'https://sctapi.ftqq.com/{send_key}.send'
    data = {'text': title[:30], 'desp': content[:3000]}  # Server酱长度限制
    try:
        response = requests.post(push_url, data=data, timeout=10)
        return response.json()
    except RequestException:
        return None


def signAndList(token, client_id, account_index=1):
    """执行签到并查询签到记录"""
    now = datetime.now()
    # 修复：时间戳改为毫秒级数字（API通用规范）
    timestamp = str(int(time.time() * 1000))
    payload = {
        "token": token,
        "client_id": client_id,
        "appkey": APPKEY,
        "format": FORMAT,
        "timestamp": timestamp,  # 关键修复：使用数字时间戳
        "platform": PLATFORM,
        "method": GLOBAL_METHOD
    }

    if GLOBAL_METHOD == "add.signon.item":
        payload["year"] = str(now.year)
        payload["month"] = str(now.month)
        payload["day"] = str(now.day)
        payload["stype"] = GLOBAL_STYPE

    # 生成签名
    sign_val = generate_sign(payload)
    if not sign_val:
        err = "签名生成失败"
        RESULT_LOG.append(f"【账号 {account_index}】client_id: {client_id}\n❌ {err}")
        FAILED_LOG.append((client_id, err))
        return False
    
    payload["sign"] = sign_val

    try:
        # 随机延迟，避免风控
        delay = random.uniform(1.0, 2.5)
        print(f"      ⏳ 等待 {delay:.1f}s...")
        time.sleep(delay)

        # 发送签到请求
        success, resp = send_http_request(URL, payload)
        if not success:
            err = f"请求失败: {resp}"
            print(f"      ❌ {err}")
            RESULT_LOG.append(f"【账号 {account_index}】client_id: {client_id}\n❌ {err}")
            FAILED_LOG.append((client_id, err))
            return False

        # 解析响应
        try:
            resp_json = resp.json()
        except JSONDecodeError:
            resp_json = {"code": -1, "msg": f"非JSON响应: {resp.text[:200]}"}

        code = resp_json.get("code")
        msg = resp_json.get("msg", "") or resp_json.get("message", "") or str(resp_json)

        is_success = False
        if code == 200 or "成功" in msg or "已签到" in msg or "已簽到" in msg:
            is_success = True

        # 记录日志
        result_line = f"【账号 {account_index}】client_id: {client_id}\n结果：{'✅ 成功' if is_success else '❌ 失败'}\n信息：{msg[:200]}"
        RESULT_LOG.append(result_line)

        if is_success:
            print(f"      ✅ 结果: 成功 | {msg}")
            if SHOW_RAW_RESPONSE:
                print(f"      └─ 返回: {json.dumps(resp_json, ensure_ascii=False, indent=2)[:500]}")

            # 查询签到记录
            print("\n📢 开始检查签到天数")
            time.sleep(random.uniform(1.0, 2.5))
            
            # 构造查询请求
            payload2 = {
                "token": token,
                "client_id": client_id,
                "appkey": APPKEY,
                "format": FORMAT,
                "timestamp": str(int(time.time() * 1000)),
                "platform": PLATFORM,
                "method": "get.signon.list"
            }
            payload2["sign"] = generate_sign(payload2)
            
            # 发送查询请求
            success2, resp2 = send_http_request(URL, payload2, timeout=20)
            if success2:
                try:
                    signResult = format_sign_status(resp2.json(), client_id=client_id)
                except JSONDecodeError:
                    signResult = f"❌ 签到列表查询失败：非JSON响应 {resp2.text[:200]}"
            else:
                signResult = f"❌ 签到列表查询失败：{resp2}"
                
            print(signResult)
            return True
        else:
            print(f"      ❌ 结果: 失败 | {msg}")
            print(f"      └─ 完整返回: {json.dumps(resp_json, ensure_ascii=False, indent=2)[:500]}")
            FAILED_LOG.append((client_id, msg))
            return False

    except Exception as e:
        err = f"异常：{str(e)[:200]}"
        print(f"      ❌ {err}")
        RESULT_LOG.append(f"【账号 {account_index}】client_id: {client_id}\n❌ {err}")
        FAILED_LOG.append((client_id, err))
        return False


def processAccount():
    """处理所有账号的签到"""
    # 解析配置
    tokenList = [t.strip() for t in MILWAUKEETOOL_TOKEN_LIST.split(',') if t.strip()]
    clientIdList = [cid.strip() for cid in MILWAUKEETOOL_CLIENT_ID.split(',') if cid.strip()]

    # 配置校验
    if not tokenList or not clientIdList:
        print("❌ 错误：缺少 token 或 client_id 配置")
        FAILED_LOG.append(("config", "缺少账号信息"))
        return 0, 0

    # 长度校验
    if len(tokenList) != len(clientIdList):
        print(f"⚠️  警告：token数量({len(tokenList)})与client_id数量({len(clientIdList)})不一致，将按较少数量处理")
    
    min_len = min(len(tokenList), len(clientIdList))
    tokenList = tokenList[:min_len]
    clientIdList = clientIdList[:min_len]

    print(f"🔧 共加载 {min_len} 个账号")

    success = 0
    for i, (token, cid) in enumerate(zip(tokenList, clientIdList), 1):
        print(f"\n{'─' * 50}")
        print(f"📌 账号 {i}/{min_len} | client_id: {cid}")
        print('─' * 50)
        if signAndList(token, cid, i):
            success += 1
            
    return success, min_len


def sendNotification():
    """发送Server酱通知"""
    if not RESULT_LOG:
        RESULT_LOG.append("本次执行无任何账号返回信息")

    keys = [k.strip() for k in SEND_KEY_LIST.split(",") if k.strip()]
    if not keys:
        print("📤 未配置 SEND_KEY_LIST，跳过Server酱推送")
        return

    content = "\n\n".join(RESULT_LOG)
    print(f"📤 准备推送 {len(keys)} 个Server酱通知...")

    for idx, key in enumerate(keys):
        if not key:
            continue
        ret = send_msg_by_server(key, "Milwaukee 签到结果", content)
        if ret and ret.get("code") == 0:
            print(f"✅ Server酱推送成功 ({idx+1}/{len(keys)}) | key尾号:{key[-4:]}")
        else:
            print(f"❌ Server酱推送失败 ({idx+1}/{len(keys)}) | key尾号:{key[-4:]}")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Milwaukee 自动签到脚本（优化版）")
    print(f"📅 执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 执行签到
    success_cnt, total_cnt = processAccount()
    
    # 发送通知
    all_result_str = "\n\n".join(RESULT_LOG) if RESULT_LOG else "无执行结果"
    sendNotification()
    send_wechat_notification(FAILED_LOG, total_cnt, success_cnt)
    send_dingtalk_notification(FAILED_LOG, total_cnt, success_cnt, all_result_str)

    # 输出最终统计
    print("\n" + "=" * 60)
    print(f"🏁 执行完成 | 成功 {success_cnt}/{total_cnt} | 失败 {len(FAILED_LOG)}")
    print("=" * 60)


if __name__ == "__main__":
    # 设置请求重试（可选）
    requests.adapters.DEFAULT_RETRIES = 3
    main()
