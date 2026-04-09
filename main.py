# -*- coding: UTF-8 -*-
import requests
import json
import time
import random
import os
import hmac
import hashlib
import base64
from urllib.parse import quote_plus
from requests.exceptions import RequestException
from collections import defaultdict

TOKEN_LIST = os.getenv('TOKEN_LIST', '')
DINGTALK_WEBHOOK_URL = os.getenv('DINGTALK_WEBHOOK_URL', '')
DINGTALK_SECRET = os.getenv('DINGTALK_SECRET', '')
# 新增：企业微信机器人webhook
WECHAT_WEBHOOK_URL = os.getenv('WECHAT_WEBHOOK_URL', '')

# 接口配置
url = 'https://m.jlc.com/api/activity/sign/signIn?source=3'
gold_bean_url = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
seventh_day_url = "https://m.jlc.com/api/activity/sign/receiveVoucher"

# ======== 防检测核心：随机生成真实浏览器UA ========
USER_AGENT_LIST = [
    # iPhone 主流 Safari 浏览器UA
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    # 安卓 Chrome 浏览器UA
    "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Mi 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.99 Mobile Safari/537.36",
    # 嘉立创APP混合UA（保留兼容）
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/20) JlcMobileApp",
]

def get_random_ua():
    """每次请求随机获取一个真实浏览器UA，防风控检测"""
    return random.choice(USER_AGENT_LIST)

# ======== 工具函数 ========
def mask_account(account):
    if len(account) >= 4:
        return account[:2] + '****' + account[-2:]
    return '****'

def mask_json_customer_code(data):
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "customerCode" and isinstance(v, str):
                new_data[k] = v[:1] + "xxxxx" + v[-2:]
            else:
                new_data[k] = mask_json_customer_code(v)
        return new_data
    elif isinstance(data, list):
        return [mask_json_customer_code(i) for i in data]
    else:
        return data

# ======== 推送通知：钉钉 ========
def send_msg_by_dingtalk(title, content):
    if not DINGTALK_WEBHOOK_URL:
        print("⚠️ 钉钉机器人Webhook未配置，跳过钉钉推送")
        return None
    
    msg = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"# {title}\n\n{content}"
        },
        "at": {
            "isAtAll": False
        }
    }
    
    try:
        timestamp = str(round(time.time() * 1000))
        if DINGTALK_SECRET:
            secret_enc = DINGTALK_SECRET.encode('utf-8')
            string_to_sign = f'{timestamp}\n{DINGTALK_SECRET}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            request_url = f'{DINGTALK_WEBHOOK_URL}&timestamp={timestamp}&sign={sign}'
        else:
            request_url = DINGTALK_WEBHOOK_URL
        
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        response = requests.post(
            request_url,
            headers=headers,
            data=json.dumps(msg, ensure_ascii=False).encode('utf-8')
        )
        result = response.json()
        
        if result.get('errcode') == 0:
            print("✅ 钉钉消息发送成功")
            return result
        else:
            print(f"❌ 钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
            return result
    except Exception as e:
        print(f"❌ 钉钉消息发送异常: {str(e)}")
        return None

# ======== 推送通知：企业微信（新增） ========
def send_msg_by_wechat(title, content):
    if not WECHAT_WEBHOOK_URL:
        print("⚠️ 企业微信机器人Webhook未配置，跳过企业微信推送")
        return None

    # 企业微信支持markdown格式
    msg = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"## {title}\n{content}"
        }
    }

    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(
            WECHAT_WEBHOOK_URL,
            headers=headers,
            data=json.dumps(msg, ensure_ascii=False)
        )
        result = response.json()

        if result.get('errcode') == 0:
            print("✅ 企业微信消息发送成功")
            return result
        else:
            print(f"❌ 企业微信消息发送失败: {result.get('errmsg', '未知错误')}")
            return result
    except Exception as e:
        print(f"❌ 企业微信消息发送异常: {str(e)}")
        return None

# ======== 单个账号签到逻辑 ========
def sign_in(access_token):
    # 核心修改：每次签到随机使用不同UA，防检测
    headers = {
        'X-JLC-AccessToken': access_token,
        'User-Agent': get_random_ua(),  # 随机UA
    }

    try:
        # 1. 获取金豆信息
        bean_response = requests.get(gold_bean_url, headers=headers)
        bean_response.raise_for_status()
        bean_result = bean_response.json()

        customer_code = bean_result['data']['customerCode']
        integral_voucher = bean_result['data']['integralVoucher']

        # 2. 执行签到
        sign_response = requests.get(url, headers=headers)
        sign_response.raise_for_status()
        sign_result = sign_response.json()

        if not sign_result.get('success'):
            message = sign_result.get('message', '未知错误')
            if '已经签到' in message:
                print(f"ℹ️ [账号{mask_account(customer_code)}] 今日已签到")
                return None
            else:
                print(f"❌ [账号{mask_account(customer_code)}] 签到失败 - {message}")
                return None

        data = sign_result.get('data', {})
        gain_num = data.get('gainNum') if data else None
        status = data.get('status') if data else None

        if status and status > 0:
            if gain_num is not None and gain_num != 0:
                print(f"✅ [账号{mask_account(customer_code)}] 今日签到成功")
                return f"✅ 账号({mask_account(customer_code)})：获取{gain_num}个金豆，当前总数：{integral_voucher + gain_num}"
            else:
                seventh_response = requests.get(seventh_day_url, headers=headers)
                seventh_response.raise_for_status()
                seventh_result = seventh_response.json()

                if seventh_result.get("success"):
                    print(f"🎉 [账号{mask_account(customer_code)}] 第七天签到成功")
                    return f"🎉 账号({mask_account(customer_code)})：第七天签到成功，当前金豆总数：{integral_voucher + 8}"
                else:
                    print(f"ℹ️ [账号{mask_account(customer_code)}] 第七天签到失败，无金豆获取")
                    return None
        else:
            print(f"ℹ️ [账号{mask_account(customer_code)}] 今日已签到或签到失败")
            return None

    except RequestException as e:
        print(f"❌ [账号{mask_account(access_token)}] 网络请求失败: {str(e)}")
        return None
    except KeyError as e:
        print(f"❌ [账号{mask_account(access_token)}] 数据解析失败: 缺少键 {str(e)}")
        return None
    except Exception as e:
        print(f"❌ [账号{mask_account(access_token)}] 未知错误: {str(e)}")
        return None

# ======== 主函数 ========
def main():
    AccessTokenList = [token.strip() for token in TOKEN_LIST.split(',') if token.strip()]

    if not AccessTokenList:
        print("❌ 请设置 TOKENS")
        return

    print(f"🔧 共发现 {len(AccessTokenList)} 个账号需要签到")
    all_dingtalk_results = []

    print(f"\n🚀 开始处理所有账号签到")
    for i, token in enumerate(AccessTokenList):
        print(f"📝 处理第 {i+1}/{len(AccessTokenList)} 个账号...")
        
        result = sign_in(token)
        if result is not None:
            all_dingtalk_results.append(result)
        
        if i < len(AccessTokenList) - 1:
            wait_time = random.randint(5, 15)
            print(f"⏳ 等待 {wait_time} 秒后处理下一个账号...")
            time.sleep(wait_time)

    print("\n📬 开始发送通知...")
    if all_dingtalk_results:
        dingtalk_content = "\n\n".join(all_dingtalk_results)
        # 同时推送钉钉 + 企业微信
        send_msg_by_dingtalk("嘉立创签到汇总", dingtalk_content)
        send_msg_by_wechat("嘉立创签到汇总", dingtalk_content)
    else:
        print("⏭️ 无金豆获取，跳过通知")

# ======== 程序入口 ========
if __name__ == '__main__':
    print("🏁 嘉立创自动签到任务开始")
    main()
    print("🏁 任务执行完毕")
