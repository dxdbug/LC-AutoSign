# -*- coding: UTF-8 -*-
"""
立创商城「每月开盲盒」活动 —— 自动签到 + 自动抽盲盒脚本
新增：飞书群机器人推送 FEISHU_WEBHOOK 环境变量

思路参照 main-jindou.py（嘉立创签到）：
  1. 从环境变量 LCSC_TOKEN_LIST 读取账号凭证（多个用英文逗号分隔；名字特意与嘉立创的 TOKEN_LIST 区分，避免混淆）
  2. 调用盲盒首页接口获取 uuid、签到状态、抽奖次数
  3. 当日未签到则调用签到接口完成签到
  4. 有抽奖次数则自动开盲盒，直到次数用完
  5. 查询积分账户，统计今日签到所得积分与当前总积分
  6. 结果汇总后通过企业微信 / 飞书群机器人推送通知

接口来源：m.szlcsc.com/pages-activity/blind-box/index 页面打包 JS
  - 首页数据  GET  https://activity.szlcsc.com/phone/mcp/blind-box/home
  - 签到      POST https://activity.szlcsc.com/phone/cus/mcp/blind-box/sign/in  body: {"uuid":"..."}
  - 开盲盒    GET  https://activity.szlcsc.com/phone/lottery/activity/draw/v2?uuid=...
  - 刷新次数  POST https://activity.szlcsc.com/phone/cus/lottery/refresh        body: {"ruleCode":"..."}
  - 积分明细  GET  https://activity.szlcsc.com/phone/cus/point/detail/list?currentPage=1
     result.pointAccountModel.totalPoint=总积分；result.pointUpdateDetailVOList=积分明细
认证方式：请求头 X-LC-AccessToken（立创商城自己的登录凭证，与嘉立创的 X-JLC-AccessToken 不互通；
请勿直接使用嘉立创的 token，需登录 https://m.szlcsc.com 后抓取立创商城的 X-LC-AccessToken）

环境变量配置列表：
  WECHAT_WORK_WEBHOOK  企业微信群机器人 Webhook（可留空，留空则不推送企微）
  FEISHU_WEBHOOK       飞书群机器人 Webhook（可留空，留空则不推送飞书）
  LCSC_TOKEN_LIST      立创商城账号凭证（X-LC-AccessToken），多个用英文逗号分隔（必填）
  AUTO_DRAW_BLIND_BOX  是否自动抽盲盒，true/false，默认 true（可选）

如何获取 token（X-LC-AccessToken）：
  1) 手机/电脑浏览器登录 https://m.szlcsc.com
  2) F12 打开开发者工具 -> Network（网络）面板
  3) 刷新页面，任选一个接口请求，在「Request Headers」里复制 X-LC-AccessToken 的值
     （也可以在 Application -> Local Storage 里找到 X-LC-AccessToken 键复制）
飞书webhook获取：飞书群 -> 添加机器人 -> 自定义机器人，复制webhook地址
"""

import requests
import json
import time
import random
import os
from requests.exceptions import RequestException

# ===================== 配置区（仅做默认值，优先读取环境变量） =====================
# 替换为你的企业微信群机器人Webhook地址；留空则跳过推送
WECHAT_WORK_WEBHOOK = ""
# 飞书机器人webhook地址；优先读取环境变量 FEISHU_WEBHOOK
FEISHU_WEBHOOK = ""
# ==============================================================================

# 接口配置
HOME_URL = "https://activity.szlcsc.com/phone/mcp/blind-box/home"
SIGN_IN_URL = "https://activity.szlcsc.com/phone/cus/mcp/blind-box/sign/in"
DRAW_URL = "https://activity.szlcsc.com/phone/lottery/activity/draw/v2"
LOTTERY_REFRESH_URL = "https://activity.szlcsc.com/phone/cus/lottery/refresh"
POINT_DETAIL_URL = "https://activity.szlcsc.com/phone/cus/point/detail/list"

# 移动端 UA（与立创商城 H5 页面一致）
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
REFERER = "https://m.szlcsc.com/pages-activity/blind-box/index"
ORIGIN = "https://m.szlcsc.com"

# 是否自动抽盲盒（环境变量 AUTO_DRAW_BLIND_BOX 可覆盖，默认 true）
AUTO_DRAW_BLIND_BOX = os.getenv('AUTO_DRAW_BLIND_BOX', 'true').strip().lower() in ('true', '1', 'yes')


# ======== 工具函数 ========
def mask_token(token):
    """打印时隐藏 token 中间部分"""
    if not token:
        return '****'
    if len(token) >= 8:
        return token[:4] + '****' + token[-4:]
    return '****'

def build_headers(token):
    """构造请求头，认证凭证放入 X-LC-AccessToken 头"""
    return {
        'X-LC-AccessToken': token,
        'User-Agent': UA,
        'Referer': REFERER,
        'Origin': ORIGIN,
        'Content-Type': 'application/json',
    }

def get_point_info(headers):
    """
    查询积分账户与最近一页积分明细
    :return: (total_point 总积分, detail_list 明细列表)；接口失败返回 (None, [])
    明细字段：uuid、updateType(变动类型)、updatePoint(变动积分，正得负扣)、
             updateTime(时间)、totalPoint(变动后积分)、expireDate(过期时间)
    """
    try:
        resp = requests.get(POINT_DETAIL_URL, headers=headers,
                            params={'currentPage': 1}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 200:
            return None, []
        result = data.get('result') or {}
        total_point = (result.get('pointAccountModel') or {}).get('totalPoint')
        detail_list = result.get('pointUpdateDetailVOList') or []
        return total_point, detail_list
    except RequestException:
        return None, []

def calc_today_sign_point(before_list, after_list, today,
                          total_before, total_after):
    """
    计算今日签到获得的积分，按可靠程度依次尝试：
      1) 签到后明细中，今天、签到类型(red_packet)的正向积分
      2) 签到动作新增（uuid 不在签到前集合）、今天、非抽奖类的正向积分
      3) 总积分差值（兜底）
    :return: 今日签到积分（int），无法确定时返回 None
    """
    before_uuids = {d.get('uuid') for d in (before_list or [])}

    # 1) 今天、签到送积分(red_packet)
    val = sum(int(d.get('updatePoint') or 0)
              for d in (after_list or [])
              if (d.get('updateTime') or '').startswith(today)
              and d.get('updateType') == 'red_packet'
              and int(d.get('updatePoint') or 0) > 0)
    if val > 0:
        return val

    # 2) 签到后新增、今天、非抽奖(lottery_activity)的正向积分
    val = sum(int(d.get('updatePoint') or 0)
              for d in (after_list or [])
              if d.get('uuid') not in before_uuids
              and (d.get('updateTime') or '').startswith(today)
              and d.get('updateType') != 'lottery_activity'
              and int(d.get('updatePoint') or 0) > 0)
    if val > 0:
        return val

    # 3) 总积分差值兜底
    if total_before is not None and total_after is not None and total_after > total_before:
        return total_after - total_before

    return None

def send_msg_by_wechat_work(title, content):
    """
    企业微信群机器人推送消息（单个Webhook）
    :param title: 消息标题
    :param content: 消息内容（支持Markdown）
    :return: 推送结果
    """
    webhook_url = os.getenv("WECHAT_WORK_WEBHOOK", WECHAT_WORK_WEBHOOK)
    if not webhook_url or "你的key" in webhook_url:
        print("ℹ️ 未配置有效的企业微信Webhook，跳过企微推送")
        return False

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### {title}\n\n{content}"
        }
    }
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data), timeout=20)
        result = response.json()
        if result.get("errcode") == 0:
            return True
        else:
            print(f"❌ 企业微信推送失败：{result.get('errmsg')}")
            return False
    except RequestException as e:
        print(f"❌ 企业微信推送网络错误：{str(e)}")
        return False


def send_msg_by_feishu(title, content):
    """
    飞书自定义机器人推送，飞书markdown语法注意：不支持###大标题，使用**加粗标题**
    https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN
    """
    webhook_url = os.getenv("FEISHU_WEBHOOK", FEISHU_WEBHOOK)
    if not webhook_url:
        print("ℹ️ 未配置飞书Webhook，跳过飞书推送")
        return False
    #飞书markdown，标题用**加粗**
    md_text = f"**{title}**\n\n{content}"
    payload = {
        "msg_type": "markdown",
        "content": {
            "text": md_text
        }
    }
    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.post(webhook_url, data=json.dumps(payload), headers=headers, timeout=20)
        ret = resp.json()
        if ret.get("code") == 0:
            return True
        else:
            print(f"❌ 飞书推送失败：{ret.get('msg', '')}")
            return False
    except RequestException as e:
        print(f"❌ 飞书推送网络异常：{str(e)}")
        return False


# ======== 单个账号签到 + 抽盲盒逻辑 ========
def sign_and_draw(token):
    """
    对一个账号完成签到与抽盲盒
    :param token: X-LC-AccessToken
    :return: 需要推送的消息（str），或 None（无推送）
    """
    headers = build_headers(token)
    mask = mask_token(token)

    try:
        # 1. 获取盲盒首页数据：uuid、登录状态、今日是否已签到、抽奖次数
        home_response = requests.get(HOME_URL, headers=headers, timeout=30)
        home_response.raise_for_status()
        home = home_response.json()

        if home.get('code') == 401:
            print(f"❌ [账号{mask}] 未登录（token 无效或过期），请重新获取 X-LC-AccessToken")
            return None

        if home.get('code') != 200:
            print(f"❌ [账号{mask}] 获取活动信息失败 - {home.get('msg') or '未知错误'}")
            return None

        result = home.get('result') or {}
        uuid = result.get('uuid')
        is_login = result.get('isLogin')
        sign_in_vo = result.get('blindBoxSignInVO') or {}
        lottery_vo = result.get('blindBoxLotteryVO') or {}

        if not uuid:
            print(f"❌ [账号{mask}] 未获取到活动 uuid，活动可能未开始或已结束")
            return None

        if is_login is False:
            print(f"❌ [账号{mask}] token 无效或未登录（isLogin=False），请重新获取 X-LC-AccessToken")
            return None

        messages = []

        # 2. 判断今日是否已签到
        signed_dates = set(sign_in_vo.get('signInDateList') or [])
        today = (result.get('currentTime') or time.strftime('%Y-%m-%d %H:%M:%S'))[:10]

        # 签到前先读取一次积分（用于统计今日签到所得与总积分）
        total_point_before, point_before_list = get_point_info(headers)

        if today in signed_dates:
            consecutive = sign_in_vo.get('consecutiveSignInCount') or 0
            print(f"ℹ️ [账号{mask}] 今日已签到（连续 {consecutive} 天）")
        else:
            # 3. 执行签到
            sign_response = requests.post(
                SIGN_IN_URL,
                headers=headers,
                data=json.dumps({"uuid": uuid}),
                timeout=30,
            )
            sign_response.raise_for_status()
            sign_result = sign_response.json()

            if sign_result.get('code') == 200:
                print(f"✅ [账号{mask}] 今日签到成功")
                messages.append("✅ 今日签到成功")
            else:
                message = sign_result.get('msg') or '未知错误'
                if '已签到' in message or '重复' in message:
                    print(f"ℹ️ [账号{mask}] 今日已签到：{message}")
                elif sign_result.get('code') in (401, 402):
                    print(f"❌ [账号{mask}] 签到失败 - 登录失效（token 无效或过期）")
                    messages.append("❌ 签到失败：登录失效")
                else:
                    print(f"❌ [账号{mask}] 签到失败 - {message}")
                    messages.append(f"❌ 签到失败：{message}")

        # 4. 自动抽盲盒（可选）
        draw_num = lottery_vo.get('quantitySurplus') or 0
        rule_code = lottery_vo.get('ruleCode')

        if AUTO_DRAW_BLIND_BOX and draw_num > 0:
            # 签到后抽奖次数可能增加，先刷新一次再重新读取
            if rule_code:
                try:
                    requests.post(
                        LOTTERY_REFRESH_URL,
                        headers=headers,
                        data=json.dumps({"ruleCode": rule_code}),
                        timeout=30,
                    )
                    time.sleep(1)
                    home2 = requests.get(HOME_URL, headers=headers, timeout=30).json()
                    draw_num = (home2.get('result') or {}).get('blindBoxLotteryVO', {}).get('quantitySurplus') or 0
                except Exception:
                    pass  # 刷新失败也不影响按原次数抽

            print(f"🎁 [账号{mask}] 开始抽盲盒，剩余次数：{draw_num}")
            draw_results = []
            while draw_num > 0:
                try:
                    draw_response = requests.get(
                        DRAW_URL,
                        headers=headers,
                        params={'uuid': uuid},
                        timeout=30,
                    )
                    draw_response.raise_for_status()
                    draw_result = draw_response.json()

                    if draw_result.get('code') == 200:
                        prize = draw_result.get('result') or {}
                        prize_name = prize.get('prizeName') or '未知奖品'
                        prize_type = prize.get('prizeType') or ''
                        quantity = prize.get('rewardQuantity')
                        if quantity:
                            prize_text = f"{prize_name} x{quantity}"
                        else:
                            prize_text = prize_name
                        if prize_type == 'thanks':
                            prize_text = '谢谢参与'
                        print(f"🎉 [账号{mask}] 第 {len(draw_results) + 1} 抽：{prize_text}")
                        draw_results.append(prize_text)
                        draw_num -= 1
                    elif draw_result.get('code') in (401, 402):
                        print(f"❌ [账号{mask}] 抽盲盒时登录失效，停止本账号")
                        messages.append("❌ 抽盲盒时登录失效")
                        break
                    else:
                        message = draw_result.get('msg') or '未知错误'
                        print(f"ℹ️ [账号{mask}] 抽盲盒未成功：{message}")
                        # 部分错误（如无次数、频率限制）视为本账号结束
                        break
                except RequestException as e:
                    print(f"❌ [账号{mask}] 抽盲盒网络错误: {str(e)}")
                    break

                # 每次抽奖之间随机等待，降低风控概率
                if draw_num > 0:
                    wait_time = random.randint(3, 8)
                    time.sleep(wait_time)

            if draw_results:
                messages.append("🎁 抽盲盒结果：" + "、".join(draw_results))

        # 5. 签到/抽奖后重新读取积分，统计今日签到积分与当前总积分
        total_point_after, point_after_list = get_point_info(headers)
        total_point = total_point_after if total_point_after is not None else total_point_before
        today_sign_point = calc_today_sign_point(
            point_before_list, point_after_list, today,
            total_point_before, total_point_after)

        if today_sign_point:
            print(f"📊 [账号{mask}] 今日签到 +{today_sign_point} 积分，当前总积分：{total_point}")
            messages.append(f"📊 今日签到 +{today_sign_point} 积分，当前总积分：{total_point}")
        elif total_point is not None:
            print(f"📊 [账号{mask}] 当前总积分：{total_point}")
            messages.append(f"📊 当前总积分：{total_point}")

        # 6. 汇总
        if messages:
            return f"账号({mask})：\n" + "\n".join(messages)
        return None

    except RequestException as e:
        print(f"❌ [账号{mask}] 网络请求失败: {str(e)}")
        return None
    except Exception as e:
        print(f"❌ [账号{mask}] 未知错误: {str(e)}")
        return None

# ======== 主函数 ========
def main():
    # 从环境变量读取配置
    LCSC_TOKEN_LIST = os.getenv('LCSC_TOKEN_LIST', '')
    AccessTokenList = [token.strip() for token in LCSC_TOKEN_LIST.split(',') if token.strip()]

    if not AccessTokenList:
        print("❌ 请设置 LCSC_TOKEN_LIST 环境变量（多个 token 用英文逗号分隔）")
        return

    print(f"🔧 共发现 {len(AccessTokenList)} 个账号需要处理")
    print(f"🎁 自动抽盲盒：{'开启' if AUTO_DRAW_BLIND_BOX else '关闭'}")

    # 顺序执行任务
    results = []
    for i, token in enumerate(AccessTokenList):
        print(f"\n📝 处理第 {i + 1}/{len(AccessTokenList)} 个账号...")

        result = sign_and_draw(token)
        if result is not None:
            results.append(result)

        # 如果不是最后一个账号，则等待随机时间
        if i < len(AccessTokenList) - 1:
            wait_time = random.randint(20, 45)
            print(f"⏳ 等待 {wait_time} 秒后处理下一个账号...")
            time.sleep(wait_time)

    # 推送通知 -企微、飞书独立推送
    print("\n📬 开始执行消息推送...")
    if results:
        content = "\n\n".join(results)
        #企业微信推送
        wechat_ok = send_msg_by_wechat_work("立创盲盒签到抽奖汇总", content)
        if wechat_ok:
            print(f"✅ 企业微信通知发送成功！")
        #飞书推送
        feishu_ok = send_msg_by_feishu("立创盲盒签到抽奖汇总", content)
        if feishu_ok:
            print(f"✅ 飞书通知发送成功！")
    else:
        print(f"ℹ️ 所有账号均无结果，跳过推送")

# ======== 程序入口 ========
if __name__ == '__main__':
    print("🏁 立创商城盲盒自动签到抽奖任务开始")
    main()
    print("🏁 任务执行完毕")
