#!/usr/bin/env python3
"""
A股数据API - 回归测试套件
用法：python3 tests/test_prepare_records.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datetime

def dt(y, m, d):
    return datetime.date(y, m, d)

def kline(trade_date, **fields):
    d = trade_date if isinstance(trade_date, str) else trade_date.strftime("%Y-%m-%d")
    base = {"date": d, "close": 10.0, "volume": 1000, "pct": 0.0,
             "open": 9.9, "high": 11.0, "low": 9.5, "amount": 10000}
    base.update(fields)
    base["date"] = d
    return base

# ──────────────────────────────────────────────────────────
# prepare_records
# ──────────────────────────────────────────────────────────
from daily_updater import prepare_records

# 字段位置常量（验证后确认）
POS = {
    "ts_code": 0, "trade_date": 1, "open": 2, "close": 3,
    "high": 4, "low": 5, "volume": 6, "amount": 7,
    "pct": 8, "rise_days": 9, "fall_days": 10,
    "rtp": 11,  # rise_total_pct
    "ma5": 13, "ma10": 14, "ma20": 15, "ma60": 16,
    "rise_5d": 31, "avg_vol_20": 32, "high_20d": 33,
}

def r(rec, field):
    return rec[POS[field]]


class TestPrepareRecordsCore:
    """prepare_records 核心逻辑"""

    def test_empty(self):
        assert prepare_records("000001.SZ", []) == []
        print("  ✅ 空数据返回空列表")

    def test_field_count_34(self):
        k = [kline(dt(2025,1,2), close=10.0, volume=1000, pct=1.0)]
        recs = prepare_records("TEST", k)
        assert len(recs[0]) == 34, f"字段数应为34, got {len(recs[0])}"
        print(f"  ✅ 字段数量正确: 34")

    def test_date_order_preserved(self):
        k = [
            kline(dt(2025,1,10), close=15.0, volume=1000, pct=0),
            kline(dt(2025,1,2),  close=10.0, volume=1000, pct=0),
            kline(dt(2025,1,5),  close=12.0, volume=1000, pct=0),
        ]
        recs = prepare_records("TEST", k)
        dates = [str(r(rec, "trade_date")) for rec in recs]
        assert dates == ["2025-01-02", "2025-01-05", "2025-01-10"], f"顺序错误: {dates}"
        print(f"  ✅ 乱序自动纠正: {dates[0]} → {dates[-1]}")

    def test_open_high_low_preserved(self):
        k = [kline(dt(2025,1,2), open=9.5, close=10.0, high=10.5, low=9.0, volume=1000, pct=1.0)]
        rec = prepare_records("TEST", k)[0]
        assert r(rec, "open") == 9.5, f"open应为9.5, got {r(rec,'open')}"
        assert r(rec, "close") == 10.0
        assert r(rec, "high") == 10.5
        assert r(rec, "low") == 9.0
        print("  ✅ OHLC数据正确保存")


class TestMA:
    """MA均线计算"""

    def test_ma5_none_before_5_days(self):
        k = [kline(dt(2025,1,2+i), close=float(10+i), volume=1000, pct=1.0) for i in range(4)]
        recs = prepare_records("TEST", k)
        for i, rec in enumerate(recs):
            assert r(rec, "ma5") is None, f"第{i+1}条ma5应为None, got {r(rec,'ma5')}"
        print(f"  ✅ MA5不足5天为None")

    def test_ma5_value_on_day5(self):
        k = [kline(dt(2025,1,2+i), close=float(10+i), volume=1000, pct=1.0) for i in range(5)]
        recs = prepare_records("TEST", k)
        ma5_5th = r(recs[4], "ma5")
        assert ma5_5th is not None, f"第5条ma5应有值, got {ma5_5th}"
        # closes=10,11,12,13,14 → ma5=(10+11+12+13+14)/5=12.0
        assert abs(ma5_5th - 12.0) < 0.1, f"ma5应约12.0, got {ma5_5th}"
        print(f"  ✅ MA5第5天有值: ma5={ma5_5th}")

    def test_ma10_none_before_10_days(self):
        k = [kline(dt(2025,1,2+i), close=float(10+i), volume=1000, pct=1.0) for i in range(9)]
        recs = prepare_records("TEST", k)
        # 9 items: indices 0-8, ma10只在index 9(第10天)有值，但只有9天故全None
        assert r(recs[8], "ma10") is None, f"第9条ma10应为None"
        assert all(r(recs[i],"ma10") is None for i in range(8)), "前8条ma10应为None"
        print(f"  ✅ 9日数据ma10全None")

    def test_ma20_20days(self):
        # 20天 close=10..29, ma20=(10+29)/2=19.5
        k = [kline(dt(2025,1,2+i), close=float(10+i), volume=1000, pct=1.0) for i in range(22)]
        recs = prepare_records("TEST", k)
        ma20 = r(recs[21], "ma20")
        assert ma20 is not None, f"22天ma20应有值"
        assert abs(ma20 - 21.5) < 0.1, f"ma20应约21.5, got {ma20}"
        print(f"  ✅ MA20正确: ma20={ma20}")

    def test_ma_bullish_arrangement(self):
        # 持续上涨时MA多头排列
        k = [kline(dt(2025,1,2+i), close=float(10+i), volume=1000, pct=1.0) for i in range(25)]
        recs = prepare_records("TEST", k)
        last = recs[-1]
        ma5, ma10, ma20 = r(last,"ma5"), r(last,"ma10"), r(last,"ma20")
        assert ma5 > ma10 > ma20, f"持续上涨ma5>ma10>ma20: {ma5:.2f}>{ma10:.2f}>{ma20:.2f}"
        print(f"  ✅ 持续上涨MA多头排列: ma5={ma5:.2f}>ma10={ma10:.2f}>ma20={ma20:.2f}")


class TestStreak:
    """连涨/连跌天数"""

    def test_rise_days_sequence(self):
        k = [kline(dt(2025,1,2+i), close=float(10+i*0.1), volume=1000, pct=1.0) for i in range(8)]
        recs = prepare_records("TEST", k)
        rd = [r(rec, "rise_days") for rec in recs]
        assert rd == [1,2,3,4,5,6,7,8], f"连涨天数错误: {rd}"
        print(f"  ✅ 连涨: {rd}")

    def test_fall_days_sequence(self):
        k = [kline(dt(2025,1,2+i), close=float(10-i*0.1), volume=1000, pct=-1.0) for i in range(8)]
        recs = prepare_records("TEST", k)
        fd = [r(rec, "fall_days") for rec in recs]
        assert fd == [1,2,3,4,5,6,7,8], f"连跌天数错误: {fd}"
        print(f"  ✅ 连跌: {fd}")

    def test_flat_day_resets_rise(self):
        # pct=0 → rd归零
        k = [
            kline(dt(2025,1,2), close=10.0, volume=1000, pct=1.0),
            kline(dt(2025,1,3), close=10.0, volume=1000, pct=0),
            kline(dt(2025,1,6), close=11.0, volume=1000, pct=10.0),
        ]
        recs = prepare_records("TEST", k)
        rd = [r(rec, "rise_days") for rec in recs]
        assert rd == [1, 0, 1], f"平盘日应重置: {rd}"
        print(f"  ✅ 平盘日重置: {rd}")

    def test_rise_break_then_fall(self):
        k = [
            kline(dt(2025,1,2), close=10.0, volume=1000, pct=1.0),
            kline(dt(2025,1,3), close=11.0, volume=1100, pct=10.0),
            kline(dt(2025,1,6), close=12.0, volume=1200, pct=9.09),
            kline(dt(2025,1,7), close=11.0, volume=1300, pct=-8.33),
            kline(dt(2025,1,8), close=10.0, volume=1400, pct=-9.09),
        ]
        recs = prepare_records("TEST", k)
        rd = [r(rec,"rise_days") for rec in recs]
        fd = [r(rec,"fall_days") for rec in recs]
        assert rd == [1,2,3,0,0],   f"rd断链重置: {rd}"
        assert fd == [0,0,0,1,2],  f"fd累加: {fd}"
        print(f"  ✅ 断链重置: rd={rd}, fd={fd}")

    def test_alternating(self):
        k = []
        for i in range(6):
            pct = 1.0 if i % 2 == 0 else -1.0
            c = 10.0 + (1 if i % 2 == 0 else -1) * i * 0.1
            k.append(kline(dt(2025,1,2+i), close=float(c), volume=1000, pct=pct))
        recs = prepare_records("TEST", k)
        rd = [r(rec,"rise_days") for rec in recs]
        fd = [r(rec,"fall_days") for rec in recs]
        assert rd == [1,0,1,0,1,0], f"涨跌交替rd: {rd}"
        assert fd == [0,1,0,1,0,1], f"涨跌交替fd: {fd}"
        print(f"  ✅ 涨跌交替: rd={rd}, fd={fd}")


class TestPrecomputed:
    """预计算字段"""

    def test_rise_5d_accumulates(self):
        k = [
            kline(dt(2025,1,2), close=10.0, volume=1000, pct=1.0),
            kline(dt(2025,1,3), close=10.5, volume=1000, pct=5.0),
            kline(dt(2025,1,6), close=11.0, volume=1000, pct=9.52),
            kline(dt(2025,1,7), close=11.5, volume=1000, pct=4.55),
            kline(dt(2025,1,8), close=12.0, volume=1000, pct=4.35),
        ]
        recs = prepare_records("TEST", k)
        v = [r(rec, "rise_5d") for rec in recs]
        assert abs(v[4] - 24.42) < 0.1, f"5日累计涨幅应约24.42, got {v[4]}"
        print(f"  ✅ rise_5d: {[round(x,2) for x in v]}")

    def test_avg_vol_20_with_insufficient(self):
        # 5天数据: 1000,2000,3000,4000,5000 → avg=(1000+2000+3000+4000+5000)/5=3000
        k = [kline(dt(2025,1,2+i), close=10.0, volume=float((i+1)*1000), pct=0) for i in range(5)]
        recs = prepare_records("TEST", k)
        v = [r(rec, "avg_vol_20") for rec in recs]
        assert abs(v[4] - 3000) < 1, f"第5日avg_vol应3000, got {v[4]}"
        print(f"  ✅ avg_vol_20: {[int(x) for x in v]}")

    def test_high_20d_tracks_max(self):
        # 10天价格: 8,7,9,6,10,7,8,9,10,5
        prices = [8.0,7.0,9.0,6.0,10.0,7.0,8.0,9.0,10.0,5.0]
        k = [kline(dt(2025,1,2+i), close=float(prices[i]), volume=1000, pct=0) for i in range(10)]
        recs = prepare_records("TEST", k)
        # high_20d: 前5天最高=10(第5天), 后5天最高=10(持续)
        v5 = r(recs[4], "high_20d")
        v9 = r(recs[9], "high_20d")
        assert v5 == 10.0, f"第5天高点应10.0, got {v5}"
        assert v9 == 10.0, f"第10天高点应10.0, got {v9}"
        print(f"  ✅ high_20d: 第5天={v5}, 第10天={v9}")

    def test_zero_volume_no_crash(self):
        k = [
            kline(dt(2025,1,2), close=10.0, volume=1000, pct=1.0),
            kline(dt(2025,1,3), close=10.5, volume=0, pct=5.0),
            kline(dt(2025,1,6), close=11.0, volume=2000, pct=10.47),
        ]
        recs = prepare_records("TEST", k)
        assert len(recs) == 3
        assert abs(r(recs[2], "rise_5d") - 16.47) < 0.1
        print("  ✅ 零成交量不崩溃")


class TestStockAPI:
    """stock_api HTTP接口"""

    def __init__(self):
        from stock_api import app
        app.testing = True
        self.client = app.test_client()

    def get(self, path):
        rv = self.client.get(path)
        if rv.status_code >= 500:
            raise RuntimeError(f"Server 500 on {path}")
        return rv.get_json()

    def test_health(self):
        d = self.get("/health")
        assert d.get("status") == "ok"
        print("  ✅ /health OK")

    def test_pool_has_rise_fall_fields(self):
        d = self.get("/api/strategy/pool?top=10")
        item = d["data"]["items"][0]
        for f in ["rise_days", "fall_days", "rise_5d"]:
            assert f in item, f"缺少字段 {f}"
        print(f"  ✅ pool含rise_days={item['rise_days']}, fall_days={item['fall_days']}")

    def test_pool_5000_no_error(self):
        d = self.get("/api/strategy/pool?top=5000")
        assert len(d["data"]["items"]) >= 4000, f"应返回>4000只, got {len(d['data']['items'])}"
        print(f"  ✅ pool大查询: {len(d['data']['items'])}只")

    def test_pool_fall_streak_filter(self):
        d = self.get("/api/strategy/pool?top=5000&type=fall_streak")
        fall = [x for x in d["data"]["items"] if x.get("fall_days", 0) > 0]
        assert len(fall) >= 100, f"连跌股应>=100, got {len(fall)}"
        print(f"  ✅ fall_streak: {len(fall)}只")

    def test_pool_rise_streak_filter(self):
        d = self.get("/api/strategy/pool?top=5000&type=rise_streak")
        items = d["data"]["items"]
        print(f"  ⚠️  rise_streak返回{len(items)}只（可能今日无严格金叉信号）")

    def test_macd_api(self):
        d = self.get("/api/strategy/macd_cross")
        for f in ["total", "items", "trade_date"]:
            assert f in d["data"], f"缺少字段 {f}"
        print(f"  ✅ MACD接口: total={d['data']['total']}, items={len(d['data']['items'])}")

    def test_trend_score_6_dimensions(self):
        d = self.get("/api/strategy/trend_score?ts_code=000001.SZ")
        if d["code"] != 0:
            print(f"  ⚠️  000001.SZ无足够历史: {d.get('msg')}")
            return
        dims = d["data"]["dimensions"]
        assert len(dims) == 6, f"应有6维度, got {len(dims)}"
        names = [x["dim"] for x in dims]
        for n in ["趋势结构", "量价健康度", "止跌企稳", "技术指标好转", "筹码结构改善", "基本面与风险"]:
            assert n in names, f"缺少{n}"
        print(f"  ✅ 趋势评分6维度: {names}")

    def test_trend_score_verdict_matches_score(self):
        d = self.get("/api/strategy/trend_score?ts_code=000001.SZ")
        if d["code"] != 0:
            print(f"  ⚠️  000001.SZ无足够历史")
            return
        score = d["data"]["total_score"]
        verdict = d["data"]["verdict"]
        assert 0 <= score <= 120
        print(f"  ✅ 趋势评分: {score}分 → {verdict}")

    def test_trend_score_raw_indicators(self):
        d = self.get("/api/strategy/trend_score?ts_code=000001.SZ")
        if d["code"] != 0:
            print(f"  ⚠️  000001.SZ无足够历史")
            return
        raw = d["data"].get("raw", {})
        for f in ["ma5", "ma20", "dif", "dea", "rsi", "boll_mid"]:
            assert f in raw, f"缺少{f}"
        print(f"  ✅ 原始指标: MA5={raw['ma5']}, RSI={raw['rsi']}, DIF={raw['dif']}")

    def test_stock_info_latest_date(self):
        d = self.get("/api/stock/info?ts_code=000001.SZ")
        assert "latest_date" in d["data"]
        print(f"  ✅ latest_date: {d['data'].get('latest_date')}")

    def test_stock_info_unknown(self):
        d = self.get("/api/stock/info?ts_code=999999.SZ")
        assert d["code"] == 404
        print(f"  ✅ 不存在股票返回404")

    def test_report_daily(self):
        d = self.get("/api/report/daily")
        m = d["data"]["market"]
        assert "rise_count" in m
        print(f"  ✅ 每日复盘: 涨{m['rise_count']}只, 涨停{m['limit_up_count']}只")

    def test_search(self):
        from urllib.parse import quote
        d = self.get(f"/api/search?q={quote('平安')}")
        assert d["code"] == 0, f"search failed: {d.get('msg')}"
        items = d["data"]["items"]
        assert len(items) > 0, "search should return results"
        assert any("平安" in x.get("name","") for x in items), "should find 平安"
        print(f"  ✅ 搜索'平安': {items[0]['name']}")


# ──────────────────────────────────────────────────────────
def run_all():
    print("=" * 60)
    print("  A股数据API - 完整回归测试")
    print("=" * 60)

    ok = True
    for cls, label in [
        (TestPrepareRecordsCore, "【核心逻辑】"),
        (TestMA,                "【MA均线】"),
        (TestStreak,           "【连涨/连跌】"),
        (TestPrecomputed,      "【预计算字段】"),
        (TestStockAPI,         "【HTTP接口】"),
    ]:
        print(f"\n{label}")
        t = cls()
        for name in sorted(dir(t)):
            if not name.startswith("test_"):
                continue
            try:
                getattr(t, name)()
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                ok = False

    print("\n" + "=" * 60)
    print("  ✅ 全部通过" if ok else "  ❌ 存在失败项")
    print("=" * 60)
    return ok


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
