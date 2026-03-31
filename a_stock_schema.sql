-- ============================================================
-- A股数据仓库 - stock_a 数据库
-- 数据库名：a_stock_data
-- 字符集：utf8mb4 / 排序规则：utf8mb4_unicode_ci
-- ============================================================

CREATE DATABASE IF NOT EXISTS a_stock_data
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE a_stock_data;

-- ============================================================
-- 表1：stock_basic  股票基础信息表
-- ============================================================
DROP TABLE IF EXISTS stock_basic;
CREATE TABLE stock_basic (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    ts_code         VARCHAR(20) NOT NULL COMMENT '证券代码 (如 000001.SZ)',
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码 (如 000001)',
    name            VARCHAR(100) NOT NULL COMMENT '股票名称',
    industry        VARCHAR(100) DEFAULT NULL COMMENT '所属行业',
    sub_industry    VARCHAR(200) DEFAULT NULL COMMENT '细分行业',
    market          ENUM('主板','创业板','科创板','北交所','港股','其他') DEFAULT '主板' COMMENT '所在市场',
    list_date       DATE DEFAULT NULL COMMENT '上市日期',
    is_active       TINYINT(1) DEFAULT 1 COMMENT '是否正常上市 (1=是 0=退市/停牌)',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE KEY uk_ts_code   (ts_code),
    KEY          idx_symbol   (symbol),
    KEY          idx_industry (industry),
    KEY          idx_market   (market),
    KEY          idx_list_date(list_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='股票基础信息表';

-- ============================================================
-- 表2：stock_daily_price  股票每日行情与技术指标表
-- ============================================================
DROP TABLE IF EXISTS stock_daily_price;
CREATE TABLE stock_daily_price (
    id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    ts_code          VARCHAR(20) NOT NULL COMMENT '证券代码 (如 000001.SZ)',
    trade_date       DATE NOT NULL COMMENT '交易日期',

    -- 基础行情
    open             DECIMAL(10,2) DEFAULT NULL COMMENT '开盘价(元)',
    close            DECIMAL(10,2) DEFAULT NULL COMMENT '收盘价(元)',
    high             DECIMAL(10,2) DEFAULT NULL COMMENT '最高价(元)',
    low              DECIMAL(10,2) DEFAULT NULL COMMENT '最低价(元)',
    volume           BIGINT UNSIGNED DEFAULT NULL COMMENT '成交量(股)',
    amount           DECIMAL(20,2) DEFAULT NULL COMMENT '成交额(元)',
    pct_change       DECIMAL(10,4) DEFAULT NULL COMMENT '涨跌幅(%, ±0.0001精度)',

    -- 涨跌周期
    rise_days        SMALLINT UNSIGNED DEFAULT 0 COMMENT '连续上涨天数(连续上涨>0, 下跌或平=0)',
    fall_days        SMALLINT UNSIGNED DEFAULT 0 COMMENT '连续下跌天数(连续下跌>0, 上涨或平=0)',
    rise_total_pct   DECIMAL(10,4) DEFAULT NULL COMMENT '本轮连续上涨总幅度(%)',
    fall_total_pct   DECIMAL(10,4) DEFAULT NULL COMMENT '本轮连续下跌总幅度(%)',

    -- 均线指标
    ma5              DECIMAL(10,2) DEFAULT NULL COMMENT '5日均线收盘均价(元)',
    ma10             DECIMAL(10,2) DEFAULT NULL COMMENT '10日均线收盘均价(元)',
    ma20             DECIMAL(10,2) DEFAULT NULL COMMENT '20日均线收盘均价(元)',
    ma60             DECIMAL(10,2) DEFAULT NULL COMMENT '60日均线收盘均价(元)',
    ma120            DECIMAL(10,2) DEFAULT NULL COMMENT '120日均线收盘均价(元)',
    ma250            DECIMAL(10,2) DEFAULT NULL COMMENT '250日均线收盘均价(元)',

    -- 支撑压力位
    support_1        DECIMAL(10,2) DEFAULT NULL COMMENT '第一支撑位(元)',
    support_2        DECIMAL(10,2) DEFAULT NULL COMMENT '第二支撑位(元)',
    support_3        DECIMAL(10,2) DEFAULT NULL COMMENT '第三支撑位(元)',
    pressure_1       DECIMAL(10,2) DEFAULT NULL COMMENT '第一压力位(元)',
    pressure_2       DECIMAL(10,2) DEFAULT NULL COMMENT '第二压力位(元)',
    pressure_3       DECIMAL(10,2) DEFAULT NULL COMMENT '第三压力位(元)',

    -- 是否跌破/突破关键指标
    break_ma5        TINYINT(1) DEFAULT 0 COMMENT '是否跌破5日线 (1=跌破 0=未破)',
    break_ma10       TINYINT(1) DEFAULT 0 COMMENT '是否跌破10日线',
    break_ma20       TINYINT(1) DEFAULT 0 COMMENT '是否跌破20日线',
    break_ma60       TINYINT(1) DEFAULT 0 COMMENT '是否跌破60日线',
    break_support1   TINYINT(1) DEFAULT 0 COMMENT '是否跌破第一支撑位',
    break_pressure1  TINYINT(1) DEFAULT 0 COMMENT '是否突破第一压力位',

    -- 量价关系
    volume_ratio     DECIMAL(8,4) DEFAULT NULL COMMENT '量比 (当日成交量/前5日均量)',
    turn_over_rate   DECIMAL(10,4) DEFAULT NULL COMMENT '换手率(%)',

    -- 时间戳
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY  uk_ts_date    (ts_code, trade_date),
    KEY          idx_trade_date(trade_date),
    KEY          idx_close     (close),
    KEY          idx_pct_change(pct_change)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='股票每日行情与技术指标表';

-- ============================================================
-- 表3：stock_chip_distribution  每日筹码分布表
-- ============================================================
DROP TABLE IF EXISTS stock_chip_distribution;
CREATE TABLE stock_chip_distribution (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    ts_code             VARCHAR(20) NOT NULL COMMENT '证券代码',
    trade_date          DATE NOT NULL COMMENT '交易日期',

    -- 成本指标
    avg_cost            DECIMAL(12,4) DEFAULT NULL COMMENT '加权平均持仓成本(元)',
    median_cost         DECIMAL(12,4) DEFAULT NULL COMMENT '中位持仓成本(元)',

    -- 集中度
    concentration      DECIMAL(10,6) DEFAULT NULL COMMENT '筹码集中度 (标准差/均值, 越小越集中)',
    concentration_20    DECIMAL(10,6) DEFAULT NULL COMMENT '近20日集中度变化',

    -- 筹码区间
    chip_70_low        DECIMAL(10,2) DEFAULT NULL COMMENT '70%筹码区间-下限(元)',
    chip_70_up         DECIMAL(10,2) DEFAULT NULL COMMENT '70%筹码区间-上限(元)',
    chip_90_low        DECIMAL(10,2) DEFAULT NULL COMMENT '90%筹码区间-下限(元)',
    chip_90_up         DECIMAL(10,2) DEFAULT NULL COMMENT '90%筹码区间-上限(元)',

    -- 获利比例
    profit_ratio        DECIMAL(10,4) DEFAULT NULL COMMENT '获利筹码比例(%, 收盘价上方筹码占比)',
    loss_ratio          DECIMAL(10,4) DEFAULT NULL COMMENT '亏损筹码比例(%)',

    -- 筹码与价格位置
    chip_above_avg_pct DECIMAL(10,4) DEFAULT NULL COMMENT '平均成本以上筹码占比(%)',
    chip_below_avg_pct DECIMAL(10,4) DEFAULT NULL COMMENT '平均成本以下筹码占比(%)',
    price_vs_avg_pct    DECIMAL(10,4) DEFAULT NULL COMMENT '现价相对平均成本偏离度(%)',

    -- 峰谷分析
    peak_price          DECIMAL(10,2) DEFAULT NULL COMMENT '筹码峰值对应价格(元)',
    peak_ratio          DECIMAL(10,4) DEFAULT NULL COMMENT '峰值筹码占总筹码比例(%)',

    -- 时间戳
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_ts_date       (ts_code, trade_date),
    KEY     idx_trade_date      (trade_date),
    KEY     idx_concentration    (concentration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='股票每日筹码分布数据表';
