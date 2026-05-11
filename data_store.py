#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贵金属数据存储模块 (v6 - AES-256-GCM 加密版)
- 持久化每日金油比、金银比数据，按日期+时段存储
- 数据对比按时段类型分别计算（亚盘对比亚盘，美盘对比美盘）
- AES-256-GCM + 随机盐值加密，密钥通过环境变量 DATA_ENCRYPT_KEY 传入
- 无密钥时退化为明文存储（本地开发兼容）
- 数据维度严格按实际天数判定，不足则不显示
"""

import json
import os
import base64
import hashlib
from datetime import datetime, timezone, timedelta

# 时区：中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))

# 数据文件路径
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DATA_DIR, 'gold_oil_data.json')
DATA_FILE_ENCRYPTED = os.path.join(DATA_DIR, 'gold_oil_data.enc')

# 有效时段列表
VALID_SESSIONS = ["亚盘收盘", "美盘收盘"]

# 加密密钥（从环境变量读取）
ENCRYPT_KEY = os.environ.get("DATA_ENCRYPT_KEY", "")


# ==================== AES-256-GCM 加密/解密模块 ====================

def _derive_key(password: str, salt: bytes) -> bytes:
    """从密码 + 随机盐值派生 256 位 AES 密钥"""
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)


def encrypt_data(data: dict) -> bytes:
    """
    使用 AES-256-GCM 加密数据
    
    格式: Base64( salt(16) + nonce(12) + ciphertext + tag(16) )
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
    
    # 每次加密使用随机盐值和随机 nonce
    salt = os.urandom(16)
    key = _derive_key(ENCRYPT_KEY, salt)
    nonce = os.urandom(12)
    
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, json_bytes, None)
    
    # 拼接: salt + nonce + ciphertext(含tag)
    encrypted = salt + nonce + ciphertext_with_tag
    return base64.b64encode(encrypted)


def decrypt_data(encrypted_bytes: bytes) -> dict:
    """
    使用 AES-256-GCM 解密数据
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    encrypted = base64.b64decode(encrypted_bytes)
    
    # 提取各部分
    salt = encrypted[:16]
    nonce = encrypted[16:28]
    ciphertext_with_tag = encrypted[28:]
    
    key = _derive_key(ENCRYPT_KEY, salt)
    
    aesgcm = AESGCM(key)
    json_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return json.loads(json_bytes.decode('utf-8'))


def is_encryption_enabled():
    """检查是否启用了加密"""
    return bool(ENCRYPT_KEY)


# ==================== 数据读写模块 ====================

def get_today_str():
    """获取今日日期字符串 (YYYY-MM-DD)"""
    return datetime.now(CST).strftime('%Y-%m-%d')


def load_data():
    """加载历史数据（自动识别加密/明文）"""
    # 优先尝试加载加密文件
    if os.path.exists(DATA_FILE_ENCRYPTED):
        if is_encryption_enabled():
            try:
                with open(DATA_FILE_ENCRYPTED, 'rb') as f:
                    encrypted_bytes = f.read()
                data = decrypt_data(encrypted_bytes)
                print(f"  加载数据成功（AES-256-GCM，{len(data.get('records', []))} 条记录）")
                return data
            except Exception as e:
                print(f"  解密数据失败: {e}")
                return {"records": []}
        else:
            print(f"  警告: 发现加密文件但未提供 DATA_ENCRYPT_KEY，无法读取")
            return {"records": []}
    
    # 回退到明文文件
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"  加载数据成功（明文模式，{len(data.get('records', []))} 条记录）")
            return data
        except Exception as e:
            print(f"  加载历史数据失败: {e}")
    
    return {"records": []}


def save_data(data):
    """保存数据到文件（根据配置选择加密/明文）"""
    try:
        if is_encryption_enabled():
            encrypted_bytes = encrypt_data(data)
            with open(DATA_FILE_ENCRYPTED, 'wb') as f:
                f.write(encrypted_bytes)
            print(f"  数据已保存（AES-256-GCM 加密，{len(data.get('records', []))} 条记录）")
        else:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  数据已保存（明文模式，{len(data.get('records', []))} 条记录）")
        return True
    except Exception as e:
        print(f"  保存数据失败: {e}")
        return False


def add_record(gold_price, oil_price, ratio, session=None, silver_price=None, gs_ratio=None):
    """
    添加记录（支持时段分离，支持银价和金银比）
    
    参数:
        gold_price: 黄金价格
        oil_price: 原油价格
        ratio: 金油比
        session: 时段标签（亚盘收盘/美盘收盘）
        silver_price: 银价（可选）
        gs_ratio: 金银比（可选）
    
    存储逻辑:
        - 按 date + session 作为唯一键
        - 同一日期+时段多次运行会更新，不会重复
        - 同一天可存储多条不同时段的记录
        - 不限制总记录数，永久保存所有历史数据
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
            if silver_price is not None:
                record["silver_price"] = silver_price
            if gs_ratio is not None:
                record["gs_ratio"] = gs_ratio
            record["updated_at"] = now
            existing = True
            break
    
    if not existing:
        new_record = {
            "date": today,
            "session": session,
            "gold_price": gold_price,
            "oil_price": oil_price,
            "ratio": ratio,
            "created_at": now
        }
        if silver_price is not None:
            new_record["silver_price"] = silver_price
        if gs_ratio is not None:
            new_record["gs_ratio"] = gs_ratio
        data["records"].append(new_record)
    
    # 按日期排序（不限制条数）
    data["records"] = sorted(data["records"], key=lambda x: (x["date"], x.get("session", "")))
    
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


def get_records_by_session(session, cached_data=None):
    """
    获取指定时段的所有记录（按日期倒序，每天只保留一条）
    
    参数:
        session: 时段类型（亚盘收盘/美盘收盘）
        cached_data: 可选的缓存数据，避免重复加载
    
    返回: 该时段的记录列表，按日期倒序排列
    """
    if cached_data is None:
        cached_data = load_data()
    records = [r for r in cached_data["records"] if r.get("session") == session]
    # 按日期倒序，每天只保留一条
    seen_dates = set()
    unique_records = []
    for r in sorted(records, key=lambda x: x["date"], reverse=True):
        if r["date"] not in seen_dates:
            seen_dates.add(r["date"])
            unique_records.append(r)
    return unique_records


def get_yesterday_value(session, field, cached_data=None):
    """
    获取昨天的指定字段值（同类型时段）
    
    参数:
        session: 当前时段类型
        field: 要查询的字段名（如 "ratio" 或 "gs_ratio"）
        cached_data: 可选的缓存数据
    
    返回: 昨日该字段的值，如果没有则返回 None
    """
    records = get_records_by_session(session, cached_data)
    today = get_today_str()
    
    # 找到今天之后的第一条记录（即昨天或更早）
    for r in records:
        if r["date"] < today:
            val = r.get(field)
            if val is not None:
                return val
    
    return None


def get_yesterday_ratio(session, cached_data=None):
    """
    获取昨天的金油比（同类型时段）- 兼容旧接口
    
    参数:
        session: 当前时段类型
        cached_data: 可选的缓存数据
    
    返回: 昨日金油比，如果没有则返回 None
    """
    return get_yesterday_value(session, "ratio", cached_data)


def get_n_days_avg_value(session, field, n_days, cached_data=None):
    """
    获取近 n 天指定字段的平均值（同类型时段）
    
    参数:
        session: 时段类型
        field: 要查询的字段名（如 "ratio" 或 "gs_ratio"）
        n_days: 天数
        cached_data: 可选的缓存数据
    
    返回: 近 n 天该字段的平均值，如果数据天数不足则返回 None
    """
    records = get_records_by_session(session, cached_data)
    today = get_today_str()
    
    # 排除今天，取近 n 天
    past_records = [r for r in records if r["date"] < today][:n_days]
    
    # 过滤掉不含该字段的记录
    valid_records = [r for r in past_records if r.get(field) is not None]
    
    # 数据天数不足时不计算，避免误导
    if len(valid_records) < n_days:
        return None
    
    avg_val = sum(r[field] for r in valid_records) / len(valid_records)
    return round(avg_val, 2)


def get_n_days_avg_ratio(session, n_days, cached_data=None):
    """
    获取近 n 天的平均金油比（同类型时段）- 兼容旧接口
    
    参数:
        session: 时段类型
        n_days: 天数
        cached_data: 可选的缓存数据
    
    返回: 近 n 天的平均金油比，如果数据天数不足则返回 None
    """
    return get_n_days_avg_value(session, "ratio", n_days, cached_data)


def calculate_change_percent(current, previous):
    """计算涨跌幅百分比"""
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def get_multi_period_changes(current_ratio, session=None, ratio_field="ratio"):
    """
    获取多时间维度涨跌幅（按天对比，同类型时段）
    
    对比维度（严格按实际天数判定）:
        - 昨日: 需要 >= 1 条历史记录
        - 近7天: 需要 >= 7 条历史记录
        - 近1月: 需要 >= 30 条历史记录
        - 近1季: 需要 >= 90 条历史记录
    
    参数:
        current_ratio: 当前比值
        session: 时段类型（None则自动判断）
        ratio_field: 字段名，"ratio" 为金油比，"gs_ratio" 为金银比
    
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
    
    # 预加载数据，避免多次重复加载
    cached_data = load_data()
    
    result = {}
    
    # 1. 昨日对比
    yesterday_val = get_yesterday_value(session, ratio_field, cached_data)
    change = calculate_change_percent(current_ratio, yesterday_val)
    result["1d"] = {
        "ratio": yesterday_val,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "昨日"
    }
    
    # 2. 近7天平均对比（需要 >= 7 天数据）
    avg_7d = get_n_days_avg_value(session, ratio_field, 7, cached_data)
    change = calculate_change_percent(current_ratio, avg_7d)
    result["7d"] = {
        "ratio": avg_7d,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近7天"
    }
    
    # 3. 近1月平均对比（需要 >= 30 天数据）
    avg_1m = get_n_days_avg_value(session, ratio_field, 30, cached_data)
    change = calculate_change_percent(current_ratio, avg_1m)
    result["1m"] = {
        "ratio": avg_1m,
        "change": change,
        "symbol": get_change_symbol(change),
        "label": "近1月"
    }
    
    # 4. 近1季平均对比（需要 >= 90 天数据）
    avg_1q = get_n_days_avg_value(session, ratio_field, 90, cached_data)
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
        "latest_date": sorted_records[-1]["date"],
        "encrypted": is_encryption_enabled()
    }


if __name__ == "__main__":
    # 测试代码
    print("数据存储模块测试 (v5 - AES-256-GCM 加密版)")
    print(f"数据文件: {DATA_FILE}")
    print(f"加密文件: {DATA_FILE_ENCRYPTED}")
    print(f"加密模式: {'AES-256-GCM' if is_encryption_enabled() else '未启用'}")
    print(f"数据汇总: {get_data_summary()}")
    
    # 测试多维度对比
    session = get_current_session()
    print(f"当前时段: {session}")
    changes = get_multi_period_changes(46.5, session)
    print(f"多维度对比: {changes}")
