# ===================== 接口17：稳中向好趋势评分 =====================
@app.route("/api/strategy/trend_score")
def strategy_trend_score():
    """
    稳中向好趋势评分 | 总分100分 | 6大维度各20分
    ts_code: 股票代码
    """
    ts_code = request.args.get("ts_code", "").strip()
    if not ts_code:
        return api_err("缺少ts_code参数", code=400)

    # 取足够历史（至少60日）
    rows_data = rows("""
        SELECT trade_date, open, close, high, low, volume, pct_change
        FROM stock_daily_price
        WHERE ts_code = %s
        ORDER BY trade_date ASC
        LIMIT 120
    """, (ts_code,))

    if not rows_data or len(rows_data) < 20:
        return api_err("历史数据不足，无法评分", code=404)

    # 转为正序列表
    bars = [(
        str(r[0]),        # trade_date
        float(r[1] or 0), # open
        float(r[2] or 0), # close
        float(r[3] or 0), # high
        float(r[4] or 0), # low
        float(r[5] or 0), # volume
        float(r[6] or 0), # pct_change
    ) for r in rows_data]

    N = len(bars)
    today = bars[-1]
    yest  = bars[-2] if N >= 2 else None

    # ─── 工具函数 ───────────────────────────────────────────────
    def _ma(data, period):
        d = [x for x in data if x is not None]
        if len(d) < period:
            return None
        return sum(d[-period:]) / period

    def _avg(data, n):
        d = [x for x in data if x is not None]
        if len(d) < n:
            return None
        return sum(d[-n:]) / min(n, len(d))

    def _max(data, n=None):
        d = data if n is None else data[-n:]
        d = [x for x in d if x is not None]
        return max(d) if d else None

    def _min(data, n=None):
        d = data if n is None else data[-n:]
        d = [x for x in d if x is not None]
        return min(d) if d else None

    # ─── 价格序列 ───────────────────────────────────────────────
    closes  = [b[2] for b in bars]  # 旧→新
    opens   = [b[1] for b in bars]
    highs   = [b[3] for b in bars]
    lows    = [b[4] for b in bars]
    vols    = [b[5] for b in bars]
    pcts    = [b[6] for b in bars]

    today_close = closes[-1]
    today_vol   = vols[-1]

    # ─── 均线 ─────────────────────────────────────────────────
    ma5_list  = [_ma(closes[:i+1], 5)  for i in range(N)]
    ma10_list = [_ma(closes[:i+1], 10) for i in range(N)]
    ma20_list = [_ma(closes[:i+1], 20) for i in range(N)]
    ma60_list = [_ma(closes[:i+1], 60) for i in range(N)]
    ma5_t  = ma5_list[-1]
    ma10_t = ma10_list[-1]
    ma20_t = ma20_list[-1]
    ma60_t = ma60_list[-1]

    # MA20趋势：前5日均值 vs 再前5日均值
    ma20_5d_avg_cur = _avg(ma20_list[-5:], 5)  # 近5日MA20均值
    ma20_5d_avg_old = _avg(ma20_list[-10:-5], 5)  # 再前5日MA20均值
    ma20_flat_or_up = (ma20_5d_avg_cur is not None and ma20_5d_avg_old is not None
                       and ma20_5d_avg_cur >= ma20_5d_avg_old)

    # MA60趋势
    ma60_5d_avg_cur = _avg(ma60_list[-5:], 5)
    ma60_5d_avg_old = _avg(ma60_list[-10:-5], 5)
    ma60_not_down = (ma60_5d_avg_cur is not None and ma60_5d_avg_old is not None
                     and ma60_5d_avg_cur >= ma60_5d_avg_old)

    # 近期低点：近20日最低点逐步抬高
    def low_n(n):
        mn = _min(lows[-n:], n) if len(lows) >= n else None
        return mn
    recent_lows = []
    for i in range(3, 0, -1):
        if len(lows) >= i * 5:
            recent_lows.append(_min(lows[-(i*5):], i*5))
    lows_rising = all(recent_lows[i] <= recent_lows[i+1]
                     for i in range(len(recent_lows)-1)) if len(recent_lows) >= 2 else False

    # ─── MACD ─────────────────────────────────────────────────
    def calc_macd_vals(close_series, n1=12, n2=26, n3=9):
        cs = close_series
        if len(cs) < n2 + n3:
            return None, None, None, None
        k1 = 2.0/(n1+1); k2 = 2.0/(n2+1); k3 = 2.0/(n3+1)
        e12 = sum(cs[:n1])/n1; e26 = sum(cs[:n2])/n2
        dif_list = []
        for i, c in enumerate(cs):
            if i >= n1: e12 = c*k1 + e12*(1-k1)
            if i >= n2: e26 = c*k2 + e26*(1-k2)
            if i >= n1: dif_list.append(e12 - e26)
        if len(dif_list) < n3:
            return None, None, None, None
        e_dea = sum(dif_list[:n3])/n3
        dea_list = []
        for i, d in enumerate(dif_list):
            if i >= n3: e_dea = d*k3 + e_dea*(1-k3)
            dea_list.append(e_dea)
        dif_t = dif_list[-1]; dea_t = dea_list[-1]
        dif_y = dif_list[-2] if len(dif_list) >= 2 else None
        dea_y = dea_list[-2] if len(dea_list) >= 2 else None
        hist_t = (dif_t - dea_t) * 2
        # 绿柱缩短：DIF更接近DEA（hist值变大/变红）
        return dif_t, dea_t, dif_y, hist_t

    dif_t, dea_t, dif_y, macd_hist_t = calc_macd_vals(closes)

    # 近5日MACD柱（判断是否在缩短）
    def get_macd_hist_n(n):
        cs = closes[:len(closes)-n] if n > 0 else closes
        dt, deat, dyt, ht = calc_macd_vals(cs)
        return ht
    macd_hist_2d_ago = get_macd_hist_n(2)  # 2天前
    macd_hist_1d_ago = get_macd_hist_n(1)  # 1天前

    # 金叉：dif_y < dea_y 且 dif_t >= dea_t
    macd_golden_cross = (dif_y is not None and dea_y is not None
                          and dif_y < dea_y and dif_t >= dea_t)

    # ─── RSI ─────────────────────────────────────────────────
    def calc_rsi(close_series, period=14):
        cs = close_series
        if len(cs) < period + 1:
            return None
        gains = []; losses = []
        for i in range(1, len(cs)):
            delta = cs[i] - cs[i-1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        if len(gains) < period:
            return None
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    rsi_t   = calc_rsi(closes)
    rsi_5d  = calc_rsi(closes[:-1]) if len(closes) > 1 else None

    # ─── KDJ ─────────────────────────────────────────────────
    def calc_kdj(high_series, low_series, close_series, n=9, m1=3, m2=3):
        hs = high_series; ls = low_series; cs = close_series
        if len(cs) < n:
            return None, None, None
        k_list = []; d_list = []
        for i in range(len(cs)):
            if i < n - 1:
                k_list.append(50); d_list.append(50)
                continue
           Hn = max(hs[max(0,i-n+1):i+1]); Hn = max([x for x in Hn if x is not None]) if any(x is not None for x in hs[max(0,i-n+1):i+1]) else cs[i]
            Ln = min(ls[max(0,i-n+1):i+1]); Ln = min([x for x in Ln if x is not None]) if any(x is not None for x in ls[max(0,i-n+1):i+1]) else cs[i]
            rsv = (cs[i] - Ln) / (Hn - Ln) * 100 if Hn != Ln else 50
            k = 2/3 * (k_list[-1] if k_list else 50) + 1/3 * rsv
            d = 2/3 * (d_list[-1] if d_list else 50) + 1/3 * k
            k_list.append(k); d_list.append(d)
        j_list = [3*k_list[i] - 2*d_list[i] for i in range(len(k_list))]
        return k_list[-1], d_list[-1], j_list[-1]

    k_t, d_t, j_t = calc_kdj(highs, lows, closes)
    k_5d, d_5d, _ = calc_kdj(highs[:-1], lows[:-1], closes[:-1]) if len(closes) > 1 else (None, None, None)

    # ─── 布林线 ───────────────────────────────────────────────
    def calc_boll(close_series, period=20, mult=2):
        cs = close_series
        if len(cs) < period:
            return None, None, None
        recent = cs[-period:]
        mid = sum(recent) / period
        std = math.sqrt(sum((x - mid)**2 for x in recent) / period)
        upper = mid + mult * std
        lower = mid - mult * std
        return upper, mid, lower

    boll_upper, boll_mid, boll_lower = calc_boll(closes)
    price_above_boll_mid = (boll_mid is not None and today_close > boll_mid)

    # ─── 量价分析 ─────────────────────────────────────────────
    # 统计近10日上涨/下跌日的平均成交量
    up_vols = [vols[i] for i in range(len(pcts)) if i >= len(pcts)-10 and pcts[i] > 0]
    dn_vols = [vols[i] for i in range(len(pcts)) if i >= len(pcts)-10 and pcts[i] < 0]
    avg_vol_up = sum(up_vols)/len(up_vols) if up_vols else 0
    avg_vol_dn = sum(dn_vols)/len(dn_vols) if dn_vols else 0
    vol_healthy = avg_vol_up > avg_vol_dn  # 涨时量多，跌时量少

    # 恐慌性放量长阴（近10日跌幅>5%且放量>2倍均量）
    has_panic = any(
        pcts[i] < -5 and vols[i] > _avg(vols, 20) * 2
        for i in range(max(0, N-10), N)
    )

    # 量能从地量温和放大
    vol_20_avg = _avg(vols, 20) or 1
    vol_5_avg  = _avg(vols, 5) or 0
    vol_gradual = vol_5_avg >= vol_20_avg * 0.8 and vol_5_avg <= vol_20_avg * 3

    # ─── 止跌企稳 ─────────────────────────────────────────────
    # 近10日未创60日新低
    low_60d  = _min(lows, 60) or float('inf')
    low_10d  = _min(lows[-10:], 10) if len(lows) >= 10 else low_60d
    no_new_low = low_10d > low_60d * 0.98  # 允许极小误差

    # 波动收窄：近5日振幅 vs 前5日振幅
    def avg_range(n):
        rngs = []
        for i in range(len(highs)-n, len(highs)):
            if highs[i] and lows[i]:
                rngs.append((highs[i] - lows[i]) / highs[i])
        return sum(rngs)/len(rngs) if rngs else None
    range_5d  = avg_range(5)
    range_10d = avg_range(10)
    range_shrink = (range_5d is not None and range_10d is not None
                    and range_5d < range_10d)

    # 无连续大跌（近10日最大单日跌幅<5%）
    max_dd_10d = min([pcts[i] for i in range(max(0,N-10), N)] or [0])
    no_consec_drop = max_dd_10d > -5

    # ─── 评分计算 ─────────────────────────────────────────────

    # ── 维度1：趋势结构（20分）─
    d1 = 0
    d1 += 5 if (ma20_t and today_close > ma20_t) else 0
    d1 += 5 if ma20_flat_or_up else 0
    d1 += 5 if ma60_not_down else 0
    d1 += 5 if lows_rising else 0

    # ── 维度2：量价健康度（20分）─
    d2 = 0
    d2 += 10 if vol_healthy else 0
    d2 += 5 if not has_panic else 0
    d2 += 5 if vol_gradual else 0

    # ── 维度3：止跌企稳（20分）─
    d3 = 0
    d3 += 10 if no_new_low else 0
    d3 += 5 if range_shrink else 0
    d3 += 5 if no_consec_drop else 0

    # ── 维度4：技术指标好转（20分）─
    d4 = 0
    # MACD：绿柱缩短 或 底背离 或 金叉
    macd_ok = False
    if macd_golden_cross:
        macd_ok = True
    elif macd_hist_t is not None and macd_hist_1d_ago is not None and macd_hist_2d_ago is not None:
        if macd_hist_t > macd_hist_1d_ago > macd_hist_2d_ago:  # 连续缩短
            macd_ok = True
    d4 += 10 if macd_ok else 0
    # KDJ/RSI从超卖区回升（RSI<40超卖，>40回升中）
    if rsi_t is not None and rsi_5d is not None and rsi_t < 40 and rsi_t > rsi_5d:
        d4 += 5
    elif rsi_t is not None and rsi_t > 40:
        d4 += 3  # 已在正常区
    # 股价在布林中轨以上
    d4 += 5 if price_above_boll_mid else 0

    # ── 维度5：筹码结构（20分）─
    # 注：数据库无筹码分布数据，根据成交量结构估算
    # 量能温和放大+无对倒迹象 → 隐含筹码改善
    d5 = 0
    if vol_gradual and not has_panic:
        d5 += 8  # 量能温和说明持仓稳定
    # 股价站上多条均线 → 持仓成本趋于集中
    ma_count = sum(1 for v in [ma5_t, ma10_t, ma20_t] if v and today_close > v)
    d5 += 6 if ma_count >= 2 else 3 if ma_count == 1 else 0
    # 近10日量能没有异常放大（无大资金出逃）
    d5 += 6 if not has_panic else 0

    # ── 维度6：基本面与风险稳定（20分）─
    # 数据库无公告/事件数据，根据技术面推断
    d6 = 0
    # 无连续跌停/大幅跳空缺口（近10日）
    gaps = []
    for i in range(1, min(10, N)):
        gap = (opens[N-i] - closes[N-i-1]) / closes[N-i-1] if closes[N-i-1] else 0
        gaps.append(gap)
    big_gap_down = any(g < -0.09 for g in gaps)  # >9%向下跳空
    d6 += 7 if not big_gap_down else 0
    # 近10日最大跌幅有限
    d6 += 7 if max_dd_10d > -7 else 0
    # RSI不过低（不是恐慌杀跌）
    d6 += 6 if rsi_t and rsi_t > 25 else 0

    total = d1 + d2 + d3 + d4 + d5 + d6

    # ─── 判断结论 ─────────────────────────────────────────────
    if total >= 80:
        verdict = "极强稳中向好 ✦"
        verdict_color = "#2ecc71"
    elif total >= 60:
        verdict = "温和稳中向好"
        verdict_color = "#27ae60"
    elif total >= 40:
        verdict = "震荡磨底，偏弱"
        verdict_color = "#f39c12"
    else:
        verdict = "仍在弱势 ▦"
        verdict_color = "#e63946"

    # ─── 诊断依据 ─────────────────────────────────────────────
    reasons = []

    # 维度1依据
    r1 = []
    if ma20_t and today_close > ma20_t: r1.append(f"股价({today_close:.2f})>MA20({ma20_t:.2f})")
    else: r1.append(f"股价({today_close:.2f})<MA20({ma20_t:.2f})" if ma20_t else "MA20数据不足")
    r1.append("MA20走平/向上" if ma20_flat_or_up else "MA20下行")
    r1.append("60日线企稳" if ma60_not_down else "60日线仍弱")
    r1.append("低点逐步抬高" if lows_rising else "低点未抬高")
    reasons.append({ "dim": "趋势结构", "score": d1, "max": 20,
                     "items": r1 })

    # 维度2依据
    r2 = []
    r2.append("涨时量多跌时量少" if vol_healthy else "量价配合一般")
    r2.append("无恐慌放量大阴" if not has_panic else "⚠️近10日出现恐慌放量")
    r2.append("量能从低位温和放大" if vol_gradual else "量能不足/异常")
    reasons.append({ "dim": "量价健康度", "score": d2, "max": 20,
                     "items": r2 })

    # 维度3依据
    r3 = []
    r3.append(f"近10日未创60日新低" if no_new_low else "⚠️近10日创60日新低")
    r3.append("波动收窄" if range_shrink else "波动未收窄")
    r3.append("无连续大跌" if no_consec_drop else "⚠️近期有连续大跌")
    reasons.append({ "dim": "止跌企稳", "score": d3, "max": 20,
                     "items": r3 })

    # 维度4依据
    r4 = []
    if macd_golden_cross: r4.append("MACD已金叉✅")
    elif macd_hist_t is not None and macd_hist_t > macd_hist_1d_ago: r4.append("MACD柱连续收短✅")
    else: r4.append("MACD仍弱" if macd_hist_t else "MACD数据不足")
    if rsi_t:
        r4.append(f"RSI={rsi_t:.1f}" + ("超卖" if rsi_t < 40 else "正常" if rsi_t < 70 else "偏高"))
    r4.append("股价>布林中轨" if price_above_boll_mid else "股价<布林中轨")
    reasons.append({ "dim": "技术指标好转", "score": d4, "max": 20,
                     "items": r4 })

    # 维度5依据
    r5 = []
    r5.append("量能温和，持仓稳定" if vol_gradual and not has_panic else "量能结构一般")
    r5.append(f"站上{ma_count}条均线" if ma_count else "均线压力重")
    r5.append("无对倒放量迹象" if not has_panic else "⚠️存在异常放量")
    reasons.append({ "dim": "筹码结构改善", "score": d5, "max": 20,
                     "items": r5 })

    # 维度6依据
    r6 = []
    r6.append("无大幅跳空缺口" if not big_gap_down else "⚠️存在向下跳空缺口")
    r6.append(f"近10日最大跌幅{Math.abs(max_dd_10d):.1f}%" if max_dd_10d else "")
    r6.append(f"RSI={rsi_t:.1f}（非恐慌区）" if rsi_t and rsi_t > 25 else "⚠️RSI偏低")
    reasons.append({ "dim": "基本面与风险", "score": d6, "max": 20,
                     "items": r6 })

    return api_ok({
        "ts_code": ts_code,
        "trade_date": today[0],
        "close": today_close,
        "total_score": total,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "dimensions": reasons,
        # 原始指标供前端展示
        "raw": {
            "ma5": round(ma5_t, 2) if ma5_t else None,
            "ma20": round(ma20_t, 2) if ma20_t else None,
            "ma60": round(ma60_t, 2) if ma60_t else None,
            "dif": round(dif_t, 4) if dif_t else None,
            "dea": round(dea_t, 4) if dea_t else None,
            "macd_hist": round(macd_hist_t, 4) if macd_hist_t else None,
            "rsi": round(rsi_t, 1) if rsi_t else None,
            "k": round(k_t, 1) if k_t else None,
            "d": round(d_t, 1) if d_t else None,
            "boll_upper": round(boll_upper, 2) if boll_upper else None,
            "boll_mid": round(boll_mid, 2) if boll_mid else None,
            "boll_lower": round(boll_lower, 2) if boll_lower else None,
            "vol_ratio": round(today_vol / vol_20_avg, 2) if vol_20_avg else None,
        }
    })
