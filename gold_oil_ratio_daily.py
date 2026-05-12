#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金油银哨兵 - GitHub Actions 云端版 (v8)
- 数据源: TradingEconomics (伦敦金现 + 布伦特原油 + 伦敦银现)
- 推送方式: 飞书官方API (Interactive卡片)
- 时段标签: 自动识别亚盘收盘/美盘收盘/欧盘时段
- 多维度对比: 昨日/近5日/近1月/近1季度涨跌（金油比 + 金银比）
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
SILVER_SOURCE_URL = "https://zh.tradingeconomics.com/commodity/silver"

# 飞书应用凭证（从环境变量读取，安全不泄露）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# 金油比历史常态区间（1970年至今）- 用于分析要点参考
HISTORICAL_RATIO_MIN = 10
HISTORICAL_RATIO_MAX = 25

# 金银比历史常态区间（1970年至今）- 用于分析要点参考
GS_RATIO_MIN = 60
GS_RATIO_MAX = 80

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


def fetch_silver_price():
    """获取伦敦银现价格（复用 fetch_gold_price 的正则匹配模式）"""
    url = "https://zh.tradingeconomics.com/commodity/silver"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            text = resp.text

            # 多模式匹配价格（与 fetch_gold_price 一致）
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
                print(f"  伦敦银现: {price} USD/盎司 ({chg:+.2f}%)" if chg else f"  伦敦银现: {price} USD/盎司")
                return price, chg
    except Exception as e:
        print(f"  TradingEconomics获取银价失败: {e}")

    return None, None


def get_realtime_prices():
    """获取伦敦金现、布伦特原油和伦敦银现的实时价格"""
    print("  正在获取实时行情数据...")

    gold_price, gold_chg = fetch_gold_price()
    oil_price, oil_chg = fetch_brent_oil_price()
    silver_price, silver_chg = fetch_silver_price()

    return gold_price, oil_price, gold_chg, oil_chg, silver_price, silver_chg


def calculate_ratio(gold, oil):
    """计算金油比"""
    return round(gold / oil, 2)


def calculate_gs_ratio(gold, silver):
    """计算金银比（黄金价格 / 白银价格）"""
    return round(gold / silver, 2)


def format_change_with_symbol(change_data):
    """格式化涨跌幅显示，带符号"""
    if change_data["change"] is None:
        return f"{change_data['symbol']} --"
    sign = "+" if change_data["change"] > 0 else ""
    return f"{change_data['symbol']} {sign}{change_data['change']:.2f}%"


def generate_report(gold_price, oil_price, gold_chg, oil_chg, silver_price, silver_chg,
                    multi_period_data, gs_multi_period_data):
    """生成金油银哨兵内容（v8 合并卡片，含金油比+金银比）"""
    now = datetime.now(CST)
    ratio = calculate_ratio(gold_price, oil_price)
    gs_ratio = calculate_gs_ratio(gold_price, silver_price)
    session = get_current_session()

    # 涨跌幅字符串
    gold_chg_str = f"({gold_chg:+.2f}%)" if gold_chg is not None else ""
    oil_chg_str = f"({oil_chg:+.2f}%)" if oil_chg is not None else ""
    silver_chg_str = f"({silver_chg:+.2f}%)" if silver_chg is not None else ""

    # 涨跌颜色标记
    gold_arrow = "🔴" if gold_chg is not None and gold_chg >= 0 else "🟢"
    oil_arrow = "🔴" if oil_chg is not None and oil_chg >= 0 else "🟢"
    silver_arrow = "🔴" if silver_chg is not None and silver_chg >= 0 else "🟢"

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

    # 判断金银比水平（5级判定体系）
    if gs_ratio > 100:
        gs_level = "极端"
        gs_color = "purple"
        gs_comment = "金银比极端异常，白银被严重低估，历史罕见"
    elif gs_ratio > 85:
        gs_level = "极高"
        gs_color = "red"
        gs_comment = "金银比极高，白银相对黄金严重低估，避险情绪极端"
    elif gs_ratio > 70:
        gs_level = "偏高"
        gs_color = "orange"
        gs_comment = "金银比偏高，白银相对黄金偏弱，市场避险需求较强"
    elif gs_ratio >= 50:
        gs_level = "适中"
        gs_color = "blue"
        gs_comment = "金银比处于历史常态区间，贵金属市场相对均衡"
    else:
        gs_level = "偏低"
        gs_color = "green"
        gs_comment = "金银比偏低，白银相对强势，经济扩张期或通胀预期强"

    # 构建金油比多维度对比行
    go_period_1d = multi_period_data.get("1d", {})
    go_period_7d = multi_period_data.get("7d", {})
    go_period_1m = multi_period_data.get("1m", {})
    go_period_1q = multi_period_data.get("1q", {})

    # 构建金银比多维度对比行
    gs_period_1d = gs_multi_period_data.get("1d", {})
    gs_period_7d = gs_multi_period_data.get("7d", {})
    gs_period_1m = gs_multi_period_data.get("1m", {})
    gs_period_1q = gs_multi_period_data.get("1q", {})

    # ========== 飞书 interactive 卡片消息 (v8 合并版 + 表格) ==========
    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📊 金油银哨兵 | {session}"
            },
            "template": header_color
        },
        "body": {
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
                # 当前行情 - 白银
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"🥈 **伦敦银现：**{silver_price:.2f} USD/盎司  {silver_arrow} {silver_chg_str}\n"
                            f"<font color='grey'>数据源: [Trading Economics]({SILVER_SOURCE_URL})</font>"
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
                # 金银比主数值 + 水平判断
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🥈 金银比：<font color='{gs_color}'>{gs_ratio:.2f}</font>**（{gold_price:.2f}/{silver_price:.2f}）"
                    }
                },
                {"tag": "hr"},

                # 数据对比 - 使用表格组件
                {
                    "tag": "table",
                    "row_height": "low",
                    "header_style": {
                        "text_align": "center",
                        "bold": True,
                        "background_style": "grey",
                        "text_color": "default"
                    },
                    "columns": [
                        {
                            "name": "period",
                            "display_name": "周期",
                            "data_type": "text",
                            "width": "25%",
                            "horizontal_align": "center"
                        },
                        {
                            "name": "go_ratio",
                            "display_name": "金油比",
                            "data_type": "text",
                            "width": "37.5%",
                            "horizontal_align": "center"
                        },
                        {
                            "name": "gs_ratio",
                            "display_name": "金银比",
                            "data_type": "text",
                            "width": "37.5%",
                            "horizontal_align": "center"
                        }
                    ],
                    "rows": [
                        {
                            "period": "昨日",
                            "go_ratio": format_change_with_symbol(go_period_1d),
                            "gs_ratio": format_change_with_symbol(gs_period_1d)
                        },
                        {
                            "period": "近7天",
                            "go_ratio": format_change_with_symbol(go_period_7d),
                            "gs_ratio": format_change_with_symbol(gs_period_7d)
                        },
                        {
                            "period": "近1月",
                            "go_ratio": format_change_with_symbol(go_period_1m),
                            "gs_ratio": format_change_with_symbol(gs_period_1m)
                        },
                        {
                            "period": "近1季",
                            "go_ratio": format_change_with_symbol(go_period_1q),
                            "gs_ratio": format_change_with_symbol(gs_period_1q)
                        }
                    ]
                },
                {"tag": "hr"},

                # 分析要点（融合金油比 + 金银比）
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**💡 分析要点**\n"
                            f"当前金油比 **<font color='{header_color}'>{ratio:.2f}</font>** {ratio_level}于历史常态区间"
                            f"（{HISTORICAL_RATIO_MIN}:1~{HISTORICAL_RATIO_MAX}:1）。{ratio_comment}。\n"
                            f"当前金银比 **<font color='{gs_color}'>{gs_ratio:.2f}</font>** {gs_level}于历史常态区间"
                            f"（{GS_RATIO_MIN}:1~{GS_RATIO_MAX}:1）。{gs_comment}。\n"
                            f"历史经验：金油比突破25通常预示危机，超过35则预示重大危机；"
                            f"金银比突破85意味着白银被严重低估，超过100则为极端信号。"
                        )
                    }
                },

                # 数据来源备注
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "<font color='grey'>⚠️ 数据来源：TradingEconomics (实时) ｜ 仅供研究参考，不构成投资建议</font>"
                    }
                }
            ]
        }
    }
    feishu_card = json.dumps(card, ensure_ascii=False)

    # 飞书降级纯文本（卡片发送失败时使用）
    feishu_fallback = (
        f"📊 金油银哨兵 | {session}\n"
        f"{now.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"🥇 伦敦金现: {gold_price:.2f} USD/盎司 {gold_chg_str}\n"
        f"🛢️ 布伦特原油: {oil_price:.2f} USD/桶 {oil_chg_str}\n"
        f"🥈 伦敦银现: {silver_price:.2f} USD/盎司 {silver_chg_str}\n\n"
        f"🎯 金油比: {ratio:.2f}（{ratio_level}）\n"
        f"🥈 金银比: {gs_ratio:.2f}（{gs_level}）\n\n"
        f"📊 数据对比:\n"
        f"  金油比 | 昨日: {format_change_with_symbol(go_period_1d)}\n"
        f"  金银比 | 昨日: {format_change_with_symbol(gs_period_1d)}\n"
        f"  金油比 | 近7天: {format_change_with_symbol(go_period_7d)}\n"
        f"  金银比 | 近7天: {format_change_with_symbol(gs_period_7d)}\n"
        f"  金油比 | 近1月: {format_change_with_symbol(go_period_1m)}\n"
        f"  金银比 | 近1月: {format_change_with_symbol(gs_period_1m)}\n"
        f"  金油比 | 近1季: {format_change_with_symbol(go_period_1q)}\n"
        f"  金银比 | 近1季: {format_change_with_symbol(gs_period_1q)}\n\n"
        f"💡 {ratio_comment}\n"
        f"💡 {gs_comment}\n\n"
        f"⚠️ 仅供研究参考"
    )

    return {
        'feishu_card': feishu_card,
        'fallback_text': feishu_fallback,
        'ratio': ratio,
        'gs_ratio': gs_ratio,
        'date': now.strftime('%Y-%m-%d'),
        'time': now.strftime('%H:%M:%S'),
        'session': session,
        'multi_period': multi_period_data,
        'gs_multi_period': gs_multi_period_data
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
    """执行每日报告主流程（v8 金油银哨兵，含金油比+金银比）
    
    参数:
        manual_session: 手动指定时段（用于测试），None则自动判断
    """
    now = datetime.now(CST)

    print("=" * 65)
    print(f"  金油银哨兵 v8 (GitHub Actions + 飞书推送)")
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
    gold_price, oil_price, gold_chg, oil_chg, silver_price, silver_chg = get_realtime_prices()

    if gold_price is None or oil_price is None:
        print("\n  数据获取不完整，无法生成日报")
        return False

    ratio = calculate_ratio(gold_price, oil_price)

    # 银价获取失败时给出警告但不中断
    if silver_price is None:
        print("\n  警告: 银价获取失败，金银比部分将使用默认值 0")
        silver_price = 0.0
        silver_chg = None

    gs_ratio = calculate_gs_ratio(gold_price, silver_price)

    print(f"\n  今日行情:")
    print(f"    伦敦金现: {gold_price} USD/盎司")
    print(f"    布伦特原油: {oil_price} USD/桶")
    print(f"    伦敦银现: {silver_price} USD/盎司")
    print(f"    金油比: {ratio}")
    print(f"    金银比: {gs_ratio}")

    # 保存数据到本地（传入时段参数 + 银价 + 金银比）
    print("\n[2/4] 保存历史数据...")
    add_record(gold_price, oil_price, ratio, session,
               silver_price=silver_price, gs_ratio=gs_ratio)
    print(f"  数据汇总: {get_data_summary()}")

    # 计算多维度对比数据（金油比 + 金银比）
    print("\n[3/4] 计算数据对比...")
    multi_period_data = get_multi_period_changes(ratio, ratio_field="ratio")
    gs_multi_period_data = get_multi_period_changes(gs_ratio, ratio_field="gs_ratio")
    
    print("  金油比涨跌幅:")
    for period, data in multi_period_data.items():
        symbol = data.get('symbol', '❓')
        change = data.get('change')
        label = data.get('label', period)
        if change is not None:
            sign = "+" if change > 0 else ""
            print(f"    {label}: {symbol} {sign}{change:.2f}%")
        else:
            print(f"    {label}: {symbol} --")

    print("  金银比涨跌幅:")
    for period, data in gs_multi_period_data.items():
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
    report = generate_report(gold_price, oil_price, gold_chg, oil_chg,
                             silver_price, silver_chg,
                             multi_period_data, gs_multi_period_data)

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
    print(f"  金银比: {gs_ratio:.2f}")
    print("=" * 65)

    return all_success or partial


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='金油银哨兵 - 商品比价追踪系统')
    parser.add_argument('--session', '-s', 
                       choices=['亚盘收盘', '美盘收盘'],
                       help='手动指定时段（用于测试），不指定则根据当前时间自动判断')
    
    args = parser.parse_args()
    
    success = run_daily_report(manual_session=args.session)
    sys.exit(0 if success else 1)
