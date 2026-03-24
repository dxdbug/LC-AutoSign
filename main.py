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
# 移除SEND_KEY_LIST定义
# 新增钉钉机器人配置（从环境变量读取）
DINGTALK_WEBHOOK_URL = os.getenv('DINGTALK_WEBHOOK_URL', '')
DINGTALK_SECRET = os.getenv('DINGTALK_SECRET', '')

# 接口配置
url = 'https://m.jlc.com/api/activity/sign/signIn?source=3'
gold_bean_url = "https://m.jlc.com/api/appPlatform/center/assets/selectPersonalAssetsInfo"
seventh_day_url = "https://m.jlc.com/api/activity/sign/receiveVoucher"


# ======== 工具函数 ========

def mask_account(account):
    """用于打印时隐藏部分账号信息"""
    if len(account) >= 4:
        return account[:2] + '****' + account[-2:]
    return '****'


def mask_json_customer_code(data):
    """递归地脱敏 JSON 中的 customerCode 字段"""
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "customerCode" and isinstance(v, str):
                new_data[k] = v[:1] + "xxxxx" + v[-2:]  # 例: 1xxxxx8A
            else:
                new_data[k] = mask_json_customer_code(v)
        return new_data
    elif isinstance(data, list):
        return [mask_json_customer_code(i) for i in data]
    else:
        return data


# ======== 推送通知 ========

# 移除Server酱推送函数 send_msg_by_server

def send_msg_by_dingtalk(title, content):
    """
    发送钉钉机器人消息
    :param title: 消息标题
    :param content: 消息内容
    :return: 响应结果
    """
    # 未配置webhook则直接返回
    if not DINGTALK_WEBHOOK_URL:
        print("⚠️ 钉钉机器人Webhook未配置，跳过钉钉推送")
        return None
    
    # 构建钉钉消息体（Markdown格式）
    msg = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"# {title}\n\n{content}"
        },
        "at": {
            "isAtAll": False  # 不@所有人
        }
    }
    
    try:
        # 如果配置了密钥，需要加签
        timestamp = str(round(time.time() * 1000))
        if DINGTALK_SECRET:
            # 加签计算
            secret_enc = DINGTALK_SECRET.encode('utf-8')
            string_to_sign = f'{timestamp}\n{DINGTALK_SECRET}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            request_url = f'{DINGTALK_WEBHOOK_URL}&timestamp={timestamp}&sign={sign}'
        else:
            request_url = DINGTALK_WEBHOOK_URL
        
        # 发送请求
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


# ======== 单个账号签到逻辑 ========

def sign_in(access_token):
    headers = {
        'X-JLC-AccessToken': access_token,
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/20) JlcMobileApp',
    }

    try:
        # 1. 获取金豆信息（先获取，用于获取 customer_code）
        bean_response = requests.get(gold_bean_url, headers=headers)
        bean_response.raise_for_status()
        bean_result = bean_response.json()

        # 获取 customerCode
        customer_code = bean_result['data']['customerCode']
        integral_voucher = bean_result['data']['integralVoucher']

        # 2. 执行签到请求
        sign_response = requests.get(url, headers=headers)
        sign_response.raise_for_status()
        sign_result = sign_response.json()

        # 检查签到是否成功
        if not sign_result.get('success'):
            message = sign_result.get('message', '未知错误')
            if '已经签到' in message:
                print(f"ℹ️ [账号{mask_account(customer_code)}] 今日已签到")
                return None  # 今日已签到，不返回消息
            else:
                print(f"❌ [账号{mask_account(customer_code)}] 签到失败 - {message}")
                return None  # 签到失败，不返回消息

        # 解析签到数据
        data = sign_result.get('data', {})
        
        # 安全地获取 gainNum 和 status
        gain_num = data.get('gainNum') if data else None
        status = data.get('status') if data else None

        # 处理签到结果
        if status and status > 0:
            if gain_num is not None and gain_num != 0:
                print(f"✅ [账号{mask_account(customer_code)}] 今日签到成功")
                return f"✅ 账号({mask_account(customer_code)})：获取{gain_num}个金豆，当前总数：{integral_voucher + gain_num}"
            else:
                # 第七天特殊处理
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
    # 从 GitHub Secrets 获取配置
    AccessTokenList = [token.strip() for token in TOKEN_LIST.split(',') if token.strip()]

    # 仅检查TOKEN是否为空
    if not AccessTokenList:
        print("❌ 请设置 TOKENS")
        return

    print(f"🔧 共发现 {len(AccessTokenList)} 个账号需要签到")

    # 移除按SendKey分组逻辑，直接遍历所有账号
    all_dingtalk_results = []

    print(f"\n🚀 开始处理所有账号签到")
    for i, token in enumerate(AccessTokenList):
        print(f"📝 处理第 {i+1}/{len(AccessTokenList)} 个账号...")
        
        # 执行签到
        result = sign_in(token)
        if result is not None:
            all_dingtalk_results.append(result)
        
        # 如果不是最后一个账号，则等待随机时间
        if i < len(AccessTokenList) - 1:
            wait_time = random.randint(5, 15)
            print(f"⏳ 等待 {wait_time} 秒后处理下一个账号...")
            time.sleep(wait_time)

    # 仅保留钉钉推送逻辑
    print("\n📬 开始检查是否需要发送钉钉通知...")
    if all_dingtalk_results:
        dingtalk_content = "\n\n".join(all_dingtalk_results)
        print(f"📤 检测到有金豆获取，准备发送钉钉通知...")
        send_msg_by_dingtalk("嘉立创签到汇总", dingtalk_content)
    else:
        print("⏭️ 无金豆获取，跳过钉钉通知")


# ======== 程序入口 ========

if __name__ == '__main__':
    print("🏁 嘉立创自动签到任务开始")
    main()
    print("🏁 任务执行完毕")
