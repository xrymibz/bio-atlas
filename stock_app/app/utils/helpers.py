"""
技术指标计算工具
"""
import math


def calc_rsi(closes, period=14):
    """计算 RSI，失败返回 None"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = (closes[i] or 0) - (closes[i - 1] or 0)
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 4)


def calc_ma(closes, period):
    """计算简单移动平均，失败返回 None"""
    if len(closes) < period:
        return None
    valid = [c for c in closes[-period:] if c is not None]
    if len(valid) < period:
        return None
    return round(sum(valid) / period, 4)


def calc_macd(closes, fast=12, slow=26, signal=9):
    """计算 MACD，返回 (dif, dea, macd_hist) 或 None"""
    if len(closes) < slow + signal:
        return None

    def ema(data, period):
        if not data or len(data) < period:
            return None
        k = 2 / (period + 1)
        result = [data[0]]
        for v in data[1:]:
            if v is None:
                v = result[-1]
            result.append(v * k + result[-1] * (1 - k))
        return result

    closes = list(closes)
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    if ema_fast is None or ema_slow is None:
        return None
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    if dea is None:
        return None
    # 对齐长度
    offset = len(dif) - len(dea)
    macd_hist = [(dif[i + offset] - dea[i]) * 2 for i in range(len(dea))]
    return round(dif[-1], 4), round(dea[-1], 4), round(macd_hist[-1], 4)


def pct_str(v):
    """百分比字符串格式化"""
    if v is None:
        return "-"
    return f"{v:+.2f}%"


def pct_cls(v):
    """百分比颜色类名"""
    if v is None or v == 0:
        return "flat"
    return "up" if v > 0 else "down"
