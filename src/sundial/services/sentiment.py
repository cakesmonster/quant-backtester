"""情绪指标计算 — 基于 push2ex + Baostock 实时计算"""

from sundial.data.eastmoney_api import fetch_all_limit_data
from sundial.data.baostock_api import fetch_index


async def compute_sentiment(target_date: str) -> dict:
    """计算某日情绪仪表盘所有指标"""
    # 并发获取涨停数据 + 指数数据
    limit_data = await fetch_all_limit_data(target_date)
    index_data = await fetch_index(target_date)

    limit_up_count = len(limit_data["limit_up"])
    limit_down_count = len(limit_data["limit_down"])
    broken_count = len(limit_data["broken"])
    broken_rate = round(broken_count / limit_up_count * 100, 1) if limit_up_count else 0

    # 连板晋级率：昨日涨停池中今日继续涨停的 / 昨日涨停总数
    yesterday_pool = limit_data["yesterday"]
    yesterday_codes = {item["code"] for item in yesterday_pool}
    today_continued = sum(1 for item in limit_data["limit_up"] if item["code"] in yesterday_codes)
    promotion_rate = round(today_continued / len(yesterday_pool) * 100, 1) if yesterday_pool else 0

    # 指数
    idx = index_data
    total_amount = round(idx["sh"]["amount"] + idx["sz"]["amount"])

    # 情绪温度计 0-100
    temp_score = 0
    # 涨停家数 (30%)
    temp_score += min(limit_up_count / 80, 1.0) * 30
    # 炸板率 (20%) — 越低越好
    if broken_rate <= 30:
        temp_score += (1 - broken_rate / 30) * 20
    # 晋级率 (20%)
    temp_score += min(promotion_rate / 50, 1.0) * 20
    # 指数涨跌 (15%) — 取上证
    sh_pct = idx["sh"]["change_pct"]
    temp_score += max(min(sh_pct / 3, 1.0), -0.5) * 15 + 7.5
    # 成交额 (15%) — 万亿以上正常
    temp_score += min(total_amount / 15000, 1.0) * 15

    temp_score = min(max(round(temp_score), 0), 100)
    stage = (
        "冰点" if temp_score <= 30 else
        "偏冷" if temp_score <= 50 else
        "正常" if temp_score <= 70 else
        "偏热" if temp_score <= 85 else
        "过热"
    )

    return {
        "date": target_date,
        "indices": {
            "sh": {"close": idx["sh"]["close"], "change_pct": idx["sh"]["change_pct"]},
            "sz": {"close": idx["sz"]["close"], "change_pct": idx["sz"]["change_pct"]},
            "cyb": {"close": idx["cyb"]["close"], "change_pct": idx["cyb"]["change_pct"]},
            "kcb": {"close": idx["kcb"]["close"], "change_pct": idx["kcb"]["change_pct"]},
        },
        "amount": {"total": total_amount, "sh": idx["sh"]["amount"], "sz": idx["sz"]["amount"]},
        "limit": {
            "up_count": limit_up_count,
            "down_count": limit_down_count,
            "broken_count": broken_count,
            "broken_rate": broken_rate,
        },
        "promotion_rate": promotion_rate,
        "sentiment_temp": temp_score,
        "sentiment_stage": stage,
    }
