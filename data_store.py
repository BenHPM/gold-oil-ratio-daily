#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金油比数据存储模块 (v3 - 按天对比版)
- 持久化每日金油比数据，按日期+时段存储
- 数据对比按时段类型分别计算（亚盘对比亚盘，美盘对比美盘）
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
VALID_SESSIONS = ["亚盘收盘", "美盘收盘"]


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
    """根据当前北京时间判断时段（仅亚盘收盘/美盘收盘两种）
    
    亚盘收盘: 15:00 - 次日05:59（北京时间）
    美盘收盘: 06:00 - 14:59（北京时间）
    """
    now_cst = datetime.now(CST)
    hour = now_cst.hour
    if 6 <= hour < 15:
        return "美盘收盘"
    else:
        return "亚盘收盘"


def get_records_by_session(session):
    """
    获取指定时段的所有记录（按日期倒序）
    
    参数:
        session: 时段类型（亚盘收盘/美盘收盘/欧盘时段）
    
    返回: 该时段的记录列表，按日期倒序排列
    """
    data = load_data()
    records = [r for r in data["records"] if r.get("session") == session]
    # 按日期倒序，每天只保留一条
    seen_dates = set()
    unique_records = []
    for r in sorted(records, key=lambda x: x["date"], reverse=True):
        if r["date"] not in seen_dates:
            seen_dates.add(r["date"])
            unique_records.append(r)
    return unique_records


def get_yesterday_ratio(session):
    """
    获取昨天的金油比（同类型时段）
    
    参数:
        session: 当前时段类型
    
    返回: 昨日金油比，如果没有则返回 None
    """
    records = get_records_by_session(session)
    today = get_today_str()
    
    # 找到今天之后的第一条记录（即昨天或更早）
    for r in records:
        if r["date"] < today:
            return r["ratio"]
    
    return None


def get_n_days_avg_ratio(session, n_days):
    """
    获取近 n 天的平均金油比（同类型时段）
    
    参数:
        session: 时段类型
        n_days: 天数
    
    返回: 近 n 天的平均金油比，如果数据不足则返回 None
    """
    records = get_records_by_session(session)
    today = get_today_str()
    
    # 排除今天，取近 n 天
    past_records = [r for r in records if r["date"] < today][:n_days]
    
    if not past_records:
        return None
    
    avg_ratio = sum(r["ratio"] for r in past_records) / len(past_records)
    return round(avg_ratio, 2)


def calculate_change_percent(current, previous):
    """计算涨跌幅百分比"""
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def get_multi_period_changes(current_ratio, session=None):
    """
    获取多时间维度涨跌幅（按天对比，同类型时段）
    
    对比维度:
        - 昨日: 同类型时段的昨天数据
        - 近7天: 同类型时段的近7天平均
        - 近1月: 同类型时段的近30天平均
        - 近1季: 同类型时段的近90天平均
    
    返回: {
        "1d": {"ratio": x, "change": y, "symbol": "📈/📉", "label": "昨日"},
        "7d": {...},
        "1m": {...},
        "1q": {...}
    }
    """
    # 如果没有传入时段，自动获取当前时段
    if session is None:
        session = get_current_session()
    
    result = {}
    
    # 1. 昨日对比
    yesterday_ratio = get_yesterday_ratio(session)
    change = calculate_change_percent(current_ratio, yesterday_ratio)
    result["1d"] = {
        "ratio": yesterday_ratio,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "昨日"
    }
    
    # 2. 近7天平均对比
    avg_7d = get_n_days_avg_ratio(session, 7)
    change = calculate_change_percent(current_ratio, avg_7d)
    result["7d"] = {
        "ratio": avg_7d,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近7天"
    }
    
    # 3. 近1月平均对比（30天）
    avg_1m = get_n_days_avg_ratio(session, 30)
    change = calculate_change_percent(current_ratio, avg_1m)
    result["1m"] = {
        "ratio": avg_1m,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近1月"
    }
    
    # 4. 近1季平均对比（90天）
    avg_1q = get_n_days_avg_ratio(session, 90)
    change = calculate_change_percent(current_ratio, avg_1q)
    result["1q"] = {
        "ratio": avg_1q,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近1季"
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
    print("数据存储模块测试 (v3 - 按天对比版)")
    print(f"数据文件: {DATA_FILE}")
    print(f"数据汇总: {get_data_summary()}")
    
    # 测试多维度对比
    session = get_current_session()
    print(f"当前时段: {session}")
    changes = get_multi_period_changes(46.5, session)
    print(f"多维度对比: {changes}")
