#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金油比数据存储模块 (v2 - 时段分离版)
- 持久化每日金油比数据，按日期+时段存储
- 支持查询历史数据用于多维度对比
- 同一天可存储亚盘收盘、美盘收盘两条记录
"""

import json
import os
from datetime import datetime, timezone, timedelta

# 时区：中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))

# 数据文件路径
DATA_FILE = os.path.join(os.path.dirname(__file__), 'gold_oil_data.json')

# 有效时段列表
VALID_SESSIONS = ["亚盘收盘", "美盘收盘", "欧盘时段"]


def get_today_str():
    """获取今日日期字符串 (YYYY-MM-DD)"""
    return datetime.now(CST).strftime('%Y-%m-%d')


def load_data():
    """加载历史数据"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  加载历史数据失败: {e}")
    return {"records": []}


def save_data(data):
    """保存数据到文件"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"  保存数据失败: {e}")
        return False


def add_record(gold_price, oil_price, ratio, session=None):
    """
    添加记录（支持时段分离）
    
    参数:
        gold_price: 黄金价格
        oil_price: 原油价格
        ratio: 金油比
        session: 时段标签（亚盘收盘/美盘收盘/欧盘时段）
    
    存储逻辑:
        - 按 date + session 作为唯一键
        - 同一日期+时段多次运行会更新，不会重复
        - 同一天可存储多条不同时段的记录
    """
    data = load_data()
    today = get_today_str()
    now = datetime.now(CST).isoformat()
    
    # 如果没有传入时段，自动判断
    if session is None:
        session = get_current_session()
    
    # 检查是否已有相同日期+时段的记录
    existing = False
    for record in data["records"]:
        if record["date"] == today and record.get("session") == session:
            record["gold_price"] = gold_price
            record["oil_price"] = oil_price
            record["ratio"] = ratio
            record["updated_at"] = now
            existing = True
            break
    
    if not existing:
        data["records"].append({
            "date": today,
            "session": session,
            "gold_price": gold_price,
            "oil_price": oil_price,
            "ratio": ratio,
            "created_at": now
        })
    
    # 按日期排序，保留最近 240 条记录（约 4 个月，每天最多 2 条）
    data["records"] = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")))[-240:]
    
    save_data(data)
    return True


def get_current_session():
    """根据当前北京时间判断时段"""
    now_cst = datetime.now(CST)
    hour = now_cst.hour
    if 0 <= hour < 12:
        return "美盘收盘"
    elif 12 <= hour < 18:
        return "亚盘收盘"
    else:
        return "欧盘时段"


def get_latest_records(n=1):
    """
    获取最近 n 条记录（按时段计算）
    
    返回: 按时间倒序排列的记录列表
    """
    data = load_data()
    records = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")), reverse=True)
    return records[:n]


def get_previous_session_ratio():
    """
    获取上一个时段的金油比
    
    逻辑: 取最近一条非当天的记录，或当天不同时段的记录
    """
    data = load_data()
    records = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")), reverse=True)
    
    if len(records) < 2:
        return None
    
    # 返回倒数第二条记录（上一时段）
    return records[1]["ratio"]


def get_ratio_n_sessions_avg(n):
    """
    获取最近 n 个时段的平均金油比（不包括当前时段）
    
    参数:
        n: 时段数量（7个时段约等于3-4天）
    """
    data = load_data()
    records = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")), reverse=True)
    
    if len(records) < 2:
        return None
    
    # 取最近 n 条（不包括当前记录）
    recent = records[1:n+1]
    
    if not recent:
        return None
    
    avg_ratio = sum(r["ratio"] for r in recent) / len(recent)
    return round(avg_ratio, 2)


def calculate_change_percent(current, previous):
    """计算涨跌幅百分比"""
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def get_multi_period_changes(current_ratio):
    """
    获取多时间维度涨跌幅（基于时段计算）
    
    时段对应关系:
        - 上一时段: 约 6-18 小时前
        - 近7时段: 约 3-4 天
        - 近20时段: 约 10-14 天（近半月）
        - 近60时段: 约 1 个月
    
    返回: {
        "1s": {"ratio": x, "change": y, "symbol": "📈/📉"},
        "7s": {...},
        "20s": {...},
        "60s": {...}
    }
    """
    data = load_data()
    records = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")), reverse=True)
    
    result = {}
    
    # 1. 上一时段对比
    prev_ratio = get_previous_session_ratio()
    change = calculate_change_percent(current_ratio, prev_ratio)
    result["1s"] = {
        "ratio": prev_ratio,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "上一时段"
    }
    
    # 2. 近7时段平均对比
    avg_7s = get_ratio_n_sessions_avg(7)
    change = calculate_change_percent(current_ratio, avg_7s)
    result["7s"] = {
        "ratio": avg_7s,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近7时段"
    }
    
    # 3. 近20时段平均对比（约半月）
    avg_20s = get_ratio_n_sessions_avg(20)
    change = calculate_change_percent(current_ratio, avg_20s)
    result["20s"] = {
        "ratio": avg_20s,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近半月"
    }
    
    # 4. 近60时段平均对比（约1月）
    avg_60s = get_ratio_n_sessions_avg(60)
    change = calculate_change_percent(current_ratio, avg_60s)
    result["60s"] = {
        "ratio": avg_60s,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近1月"
    }
    
    return result


def get_change_symbol(change_percent):
    """
    根据涨跌幅返回符号
    涨: 📈  跌: 📉  平: ➖  无数据: ❓
    """
    if change_percent is None:
        return "❓"
    if change_percent > 0:
        return "📈"
    elif change_percent < 0:
        return "📉"
    else:
        return "➖"


def get_data_summary():
    """获取数据汇总信息（用于调试）"""
    data = load_data()
    records = data["records"]
    
    if not records:
        return "暂无历史数据"
    
    sorted_records = sorted(records, key=lambda x: (x["date"], x.get("session", "")))
    
    # 统计日期数和时段数
    dates = set(r["date"] for r in records)
    sessions = set(r.get("session", "未知") for r in records)
    
    return {
        "total_records": len(records),
        "total_dates": len(dates),
        "sessions": list(sessions),
        "earliest_date": sorted_records[0]["date"],
        "latest_date": sorted_records[-1]["date"]
    }


if __name__ == "__main__":
    # 测试代码
    print("数据存储模块测试 (v2 - 时段分离版)")
    print(f"数据文件: {DATA_FILE}")
    print(f"数据汇总: {get_data_summary()}")
    print(f"最近记录: {get_latest_records(3)}")
