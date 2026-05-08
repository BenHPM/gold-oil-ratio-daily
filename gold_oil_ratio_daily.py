#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金油比日报 - GitHub Actions 云端版 (v7)
- 数据源: TradingEconomics (伦敦金现 + 布伦特原油)
- 推送方式: 飞书官方API (Interactive卡片)
- 时段标签: 自动识别亚盘收盘/美盘收盘/欧盘时段
- 多维度对比: 昨日/近5日/近1月/近1季度涨跌
- 凭证: 从环境变量读取，不硬编码
"""

import requests
import json
import time
import sys
import os
import re
from datetime import datetime, timezone, timedelta

# 导入数据存储模块
from data_store import (
    add_record, 
    get_multi_period_changes, 
    get_data_summary,
    get_change_symbol,
    get_current_session
)

# ==================== 配置区 ====================

# 时区：中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))

# 数据源参考链接
GOLD_SOURCE_URL = "https://zh.tradingeconomics.com/commodity/gold"
OIL_SOURCE_URL = "https://zh.tradingeconomics.com/commodity/brent-crude-oil"

# 飞书应用凭证（从环境变量读取，安全不泄露）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# 历史常态区间（1970年至今）- 用于分析要点参考
HISTORICAL_RATIO_MIN = 10
HISTORICAL_RATIO_MAX = 25

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5


# ==================== 数据获取 ====================

def fetch_gold_price():
    """获取伦敦金现价格"""
    url = "https://zh.tradingeconomics.com/commodity/gold"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            text = resp.text

            # 多模式匹配价格
            meta_match = re.search(r'<meta[^>]*content="([\d,]+\.?\d*)"[^>]*property="[^"]*price"', text)
            if not meta_match:
                meta_match = re.search(r'"price"\s*:\s*"([\d,]+\.?\d*)"', text)
            if not meta_match:
                meta_match = re.search(r'"last"\s*:\s*([\d,]+\.?\d*)', text)
            if not meta_match:
                meta_match = re.search(r'(\d{1,2},?\d{3}\.?\d{0,2})\s*USD/t', text)

            if meta_match:
                price_str = meta_match.group(1).replace(',', '')
                price = float(price_str)
                # 尝试提取涨跌幅
                chg_match = re.search(r'"changePercent"\s*:\s*"([+-]?\d+\.?\d*)%"', text)
                chg = float(chg_match.group(1)) if chg_match else None
                print(f"  伦敦金现: {price} USD/盎司 ({chg:+.2f}%)" if chg else f"  伦敦金现: {price} USD/盎司")
                return price, chg
    except Exception as e:
        print(f"  TradingEconomics获取失败: {e}")

    return None, None


def fetch_brent_oil_price():
    """获取布伦特原油价格"""
    url = "https://zh.tradingeconomics.com/commodity/brent-crude-oil"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            text = resp.text

            meta_match = re.search(r'"price"\s*:\s*"([\d,]+\.?\d*)"', text)
            if not meta_match:
                meta_match = re.search(r'"last"\s*:\s*([\d,]+\.?\d*)', text)
            if not meta_match:
                meta_match = re.search(r'(\d{2,3}\.?\d{0,2})\s*USD/Bbl', text)

            if meta_match:
                price_str = meta_match.group(1).replace(',', '')
                price = float(price_str)
                chg_match = re.search(r'"changePercent"\s*:\s*"([+-]?\d+\.?\d*)%"', text)
                chg = float(chg_match.group(1)) if chg_match else None
                print(f"  布伦特原油: {price} USD/桶 ({chg:+.2f}%)" if chg else f"  布伦特原油: {price} USD/桶")
                return price, chg
    except Exception as e:
        print(f"  TradingEconomics获取失败: {e}")

    return None, None


def get_realtime_prices():
    """获取伦敦金现和布伦特原油的实时价格"""
    print("  正在获取实时行情数据...")

    gold_price, gold_chg = fetch_gold_price()
    oil_price, oil_chg = fetch_brent_oil_price()

    return gold_price, oil_price, gold_chg, oil_chg


def calculate_ratio(gold, oil):
    return round(gold / oil, 2)


def format_change_with_symbol(change_data):
    """格式化涨跌幅显示，带符号"""
    if change_data["change"] is None:
        return f"{change_data['symbol']} --"
    sign = "+" if change_data["change"] > 0 else ""
    return f"{change_data['symbol']} {sign}{change_data['change']:.2f}%"


def generate_report(gold_price, oil_price, gold_chg, oil_chg, multi_period_data):
    """生成金油比日报内容（v7 新版卡片）"""
    now = datetime.now(CST)
    ratio = calculate_ratio(gold_price, oil_price)
    session = get_current_session()

    # 涨跌幅字符串
    gold_chg_str = f"({gold_chg:+.2f}%)" if gold_chg is not None else ""
    oil_chg_str = f"({oil_chg:+.2f}%)" if oil_chg is not None else ""

    # 涨跌颜色标记
    gold_arrow = "🔴" if gold_chg is not None and gold_chg >= 0 else "🟢"
    oil_arrow = "🔴" if oil_chg is not None and oil_chg >= 0 else "🟢"

    # 判断金油比水平（5级判定体系，基于1970年至今历史数据）
    if ratio > 50:
        ratio_level = "极端"
        ratio_comment = "金油比极端异常，市场严重分化，历史罕见危机信号"
        header_color = "purple"
    elif ratio > 35:
        ratio_level = "极高"
        ratio_comment = "金油比极高，通常预示重大危机，经济衰退风险显著增加"
        header_color = "red"
    elif ratio > 25:
        ratio_level = "偏高"
        ratio_comment = "金油比偏高，市场避险情绪升温，需关注经济下行风险"
        header_color = "orange"
    elif ratio >= 10:
        ratio_level = "适中"
        ratio_comment = "金油比处于历史常态区间，经济运行相对稳定"
        header_color = "blue"
    else:
        ratio_level = "偏低"
        ratio_comment = "金油比偏低，经济过热或通胀预期强，原油需求旺盛"
        header_color = "green"

    # 构建多维度对比行（按天对比）
    period_1d = multi_period_data.get("1d", {})
    period_7d = multi_period_data.get("7d", {})
    period_1m = multi_period_data.get("1m", {})
    period_1q = multi_period_data.get("1q", {})

    # ========== 飞书 interactive 卡片消息 (v7 新版) ==========
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📊 金油比日报 | {session}"
            },
            "template": header_color
        },
        "elements": [
            # 日期时间
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{now.strftime('%Y年%m月%d日')}** ｜ 更新 {now.strftime('%H:%M')}"
                }
            },
            {"tag": "hr"},
            
            # 当前行情 - 黄金
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"🥇 **伦敦金现：**{gold_price:.2f} USD/盎司  {gold_arrow} {gold_chg_str}\n"
                        f"<font color='grey'>数据源: [Trading Economics]({GOLD_SOURCE_URL})</font>"
                    )
                }
            },
            # 当前行情 - 原油
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"🛢️ **布伦特原油：**{oil_price:.2f} USD/桶  {oil_arrow} {oil_chg_str}\n"
                        f"<font color='grey'>数据源: [Trading Economics]({OIL_SOURCE_URL})</font>"
                    )
                }
            },
            {"tag": "hr"},
            
            # 金油比主数值 + 水平判断
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**🎯 金油比：<font color='{header_color}'>{ratio:.2f}</font>**（{gold_price:.2f}/{oil_price:.2f}）"
                }
            },
            {"tag": "hr"},
            
            # 多维度对比（核心新功能）
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**📊 数据对比**"
                }
            },
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**昨日**\n{format_change_with_symbol(period_1d)}"
                        }
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**近7天**\n{format_change_with_symbol(period_7d)}"
                        }
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**近1月**\n{format_change_with_symbol(period_1m)}"
                        }
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**近1季**\n{format_change_with_symbol(period_1q)}"
                        }
                    }
                ]
            },
            {"tag": "hr"},
            
            # 分析要点（融合历史对照）
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**💡 分析要点**\n"
                        f"当前金油比 **<font color='{header_color}'>{ratio:.2f}</font>** {ratio_level}于历史常态区间（{HISTORICAL_RATIO_MIN}:1~{HISTORICAL_RATIO_MAX}:1）。"
                        f"{ratio_comment}。\n"
                        f"历史经验：金油比突破25通常预示危机，超过35则预示重大危机。"
                    )
                }
            },
            
            # 数据来源备注
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "⚠️ 数据来源：TradingEconomics (实时) ｜ 仅供研究参考，不构成投资建议"
                    }
                ]
            }
        ]
    }
    feishu_card = json.dumps(card, ensure_ascii=False)

    # 飞书降级纯文本（卡片发送失败时使用）
    feishu_fallback = (
        f"📊 金油比日报 | {session}\n"
        f"{now.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"🥇 伦敦金现: {gold_price:.2f} USD/盎司 {gold_chg_str}\n"
        f"🛢️ 布伦特原油: {oil_price:.2f} USD/桶 {oil_chg_str}\n\n"
        f"🎯 金油比: {ratio:.2f}（{ratio_level}）\n\n"
        f"📊 数据对比:\n"
        f"  昨日: {format_change_with_symbol(period_1d)}\n"
        f"  近7天: {format_change_with_symbol(period_7d)}\n"
        f"  近1月: {format_change_with_symbol(period_1m)}\n"
        f"  近1季: {format_change_with_symbol(period_1q)}\n\n"
        f"💡 {ratio_comment}\n\n"
        f"⚠️ 仅供研究参考"
    )

    return {
        'feishu_card': feishu_card,
        'fallback_text': feishu_fallback,
        'ratio': ratio,
        'date': now.strftime('%Y-%m-%d'),
        'time': now.strftime('%H:%M:%S'),
        'session': session,
        'multi_period': multi_period_data
    }


# =====================================================
# 飞书官方API推送
# =====================================================

class FeishuPusher:
    """飞书消息推送器（官方API + Interactive卡片）"""

    def __init__(self):
        self.app_id = FEISHU_APP_ID
        self.app_secret = FEISHU_APP_SECRET
        self.base_url = FEISHU_BASE_URL
        self.token = None

    def get_token(self):
        """获取 tenant_access_token"""
        if not self.app_id or not self.app_secret:
            print("  ❌ 飞书凭证未配置（请检查 FEISHU_APP_ID / FEISHU_APP_SECRET 环境变量）")
            return False

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }, timeout=15)

        data = resp.json()
        if data.get("code") == 0:
            self.token = data["tenant_access_token"]
            print("  ✅ 飞书Token获取成功")
            return True
        else:
            print(f"  ❌ 飞书Token获取失败: {data}")
            return False

    def find_user(self):
        """查找用户OpenID"""
        headers = {"Authorization": f"Bearer {self.token}"}

        url = f"{self.base_url}/contact/v3/users?user_id_type=open_id&page_size=10"
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()

        if data.get("code") == 0:
            items = data.get("data", {}).get("items", [])
            if items:
                open_id = items[0].get("open_id", "")
                name = items[0].get("name", "未知")
                print(f"  ✅ 找到用户: {name}")
                return open_id

        print("  ⚠️ 未找到用户")
        return None

    def send_interactive(self, open_id, card_json, fallback_text=None):
        """发送 interactive 卡片消息"""
        url = f"{self.base_url}/im/v1/messages?receive_id_type=open_id"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": card_json
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                data = resp.json()

                if data.get("code") == 0:
                    print(f"  ✅ 飞书卡片推送成功！(第{attempt}次)")
                    return True

                err_msg = data.get("msg", "")
                if attempt < MAX_RETRIES:
                    print(f"  ⚠️ 第{attempt}次失败: {err_msg[:80]}, 重试...")
                    time.sleep(RETRY_DELAY)

            except Exception as e:
                print(f"  ❌ 第{attempt}次异常: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        # 卡片失败，降级为纯文本
        print("  ⚠️ 卡片推送失败，降级为纯文本...")
        fallback = fallback_text or "金油比日报推送失败，请检查系统"
        return self.send_text(open_id, fallback)

    def send_text(self, open_id, message):
        """发送纯文本消息（降级方案）"""
        url = f"{self.base_url}/im/v1/messages?receive_id_type=open_id"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": message})
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if data.get("code") == 0:
                print("  ✅ 飞书纯文本推送成功！")
                return True
            else:
                print(f"  ❌ 飞书纯文本推送失败: {data.get('msg', '')[:80]}")
                return False

        except Exception as e:
            print(f"  ❌ 飞书纯文本推送异常: {e}")
            return False


# =====================================================
# 主程序
# =====================================================

def run_daily_report(manual_session=None):
    """执行每日报告主流程
    
    参数:
        manual_session: 手动指定时段（用于测试），None则自动判断
    """
    now = datetime.now(CST)

    print("=" * 65)
    print(f"  金油比日报系统 v7 (GitHub Actions + 飞书推送)")
    print(f"  {now.strftime('%Y-%m-%d %A')} | {now.strftime('%H:%M:%S')} CST")
    print("=" * 65)

    # 获取时段（优先使用手动指定，否则自动判断）
    if manual_session:
        session = manual_session
        print(f"  手动指定时段: {session}")
    else:
        session = get_current_session()
        print(f"  当前时段: {session}")

    # 获取实时数据
    print("\n[1/4] 获取实时行情...")
    gold_price, oil_price, gold_chg, oil_chg = get_realtime_prices()

    if gold_price is None or oil_price is None:
        print("\n  数据获取不完整，无法生成日报")
        return False

    ratio = calculate_ratio(gold_price, oil_price)

    print(f"\n  今日行情:")
    print(f"    伦敦金现: {gold_price} USD/盎司")
    print(f"    布伦特原油: {oil_price} USD/桶")
    print(f"    金油比: {ratio}")

    # 保存数据到本地（传入时段参数）
    print("\n[2/4] 保存历史数据...")
    add_record(gold_price, oil_price, ratio, session)
    print(f"  数据汇总: {get_data_summary()}")

    # 计算多维度对比数据
    print("\n[3/4] 计算数据对比...")
    multi_period_data = get_multi_period_changes(ratio)
    
    print("  数据对比涨跌幅:")
    for period, data in multi_period_data.items():
        symbol = data.get('symbol', '❓')
        change = data.get('change')
        label = data.get('label', period)
        if change is not None:
            sign = "+" if change > 0 else ""
            print(f"    {label}: {symbol} {sign}{change:.2f}%")
        else:
            print(f"    {label}: {symbol} --")

    # 生成日报
    print("\n[4/4] 生成日报并推送...")
    report = generate_report(gold_price, oil_price, gold_chg, oil_chg, multi_period_data)

    results = {}

    # 推送到飞书（官方API）
    print("\n" + "-" * 55)
    print("推送至飞书...")

    feishu = FeishuPusher()
    if feishu.get_token():
        open_id = feishu.find_user()
        if open_id:
            ok = feishu.send_interactive(open_id, report['feishu_card'], fallback_text=report['fallback_text'])
            results['飞书'] = '✅ 成功' if ok else '❌ 失败'
        else:
            results['飞书'] = '⚠️ 无用户'
    else:
        results['飞书'] = '❌ Token失败'

    # 汇总
    print("\n" + "=" * 65)
    print("  📊 推送结果汇总")
    print("=" * 65)

    for platform, status in results.items():
        icon = "✅" if "成功" in status else ("⚠️" if "无" in status else "❌")
        print(f"  [{icon}] {platform}: {status}")

    all_success = all("成功" in s for s in results.values())
    partial = any("成功" in s for s in results.values())

    print("\n" + "=" * 65)

    if all_success:
        print("\n  飞书推送成功!")
    elif partial:
        print("\n  部分推送成功，请检查")
    else:
        print("\n  推送失败（可能是凭证未配置）")

    print(f"\n  金油比: {ratio:.2f}")
    print("=" * 65)

    return all_success or partial


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='金油比日报系统')
    parser.add_argument('--session', '-s', 
                       choices=['亚盘收盘', '美盘收盘'],
                       help='手动指定时段（用于测试），不指定则根据当前时间自动判断')
    
    args = parser.parse_args()
    
    success = run_daily_report(manual_session=args.session)
    sys.exit(0 if success else 1)
