-- =============================================================
-- A股数据库 a_stock_data 无损升级 SQL
-- 保留原有 stock_basic / stock_daily_price / stock_chip_distribution
-- 新增 5 张日线增强表
-- 执行方式：mysql -u root -p'OpenClaw@2026' a_stock_data < upgrade_a_stock.sql
-- =============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ─────────────────────────────────────────────────────────────
-- 表1：stock_daily_indicator  每日技术指标增强表
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `stock_daily_indicator` (
  `id`          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `ts_code`     VARCHAR(20)      NOT NULL                  COMMENT '证券代码，如 000001.SZ',
  `trade_date`  DATE             NOT NULL                  COMMENT '交易日期',

  -- 均线
  `ma5`         DECIMAL(10,3)    DEFAULT NULL              COMMENT '5日均线收盘价',
  `ma10`        DECIMAL(10,3)    DEFAULT NULL              COMMENT '10日均线收盘价',
  `ma20`        DECIMAL(10,3)    DEFAULT NULL              COMMENT '20日均线收盘价',
  `ma60`        DECIMAL(10,3)    DEFAULT NULL              COMMENT '60日均线收盘价',
  `ma120`       DECIMAL(10,3)    DEFAULT NULL              COMMENT '120日均线收盘价',
  `ma250`       DECIMAL(10,3)    DEFAULT NULL              COMMENT '250日均线收盘价',

  -- MACD（默认参数12,26,9）
  `dif`         DECIMAL(10,4)    DEFAULT NULL              COMMENT 'DIF 快线 = EMA12 - EMA26',
  `dea`         DECIMAL(10,4)    DEFAULT NULL              COMMENT 'DEA 信号线 = DIF的EMA9',
  `macd`        DECIMAL(10,4)    DEFAULT NULL              COMMENT 'MACD 柱 = (DIF-DEA)*2',

  -- RSI（默认6/12/24）
  `rsi_6`       DECIMAL(8,4)     DEFAULT NULL              COMMENT 'RSI6 相对强弱指标6日',
  `rsi_12`      DECIMAL(8,4)     DEFAULT NULL              COMMENT 'RSI12 相对强弱指标12日',
  `rsi_24`      DECIMAL(8,4)     DEFAULT NULL              COMMENT 'RSI24 相对强弱指标24日',

  -- BOLL布林带（默认20日，2倍标准差）
  `boll_upper`  DECIMAL(10,3)    DEFAULT NULL              COMMENT '布林上轨 = MA20 + 2*STD',
  `boll_mid`     DECIMAL(10,3)    DEFAULT NULL              COMMENT '布林中轨 = MA20',
  `boll_lower`   DECIMAL(10,3)    DEFAULT NULL              COMMENT '布林下轨 = MA20 - 2*STD',

  -- KDJ（默认9,3,3）
  `kdj_k`       DECIMAL(8,4)     DEFAULT NULL              COMMENT 'KDJ K值（随机指标）',
  `kdj_d`       DECIMAL(8,4)     DEFAULT NULL              COMMENT 'KDJ D值',
  `kdj_j`       DECIMAL(8,4)     DEFAULT NULL              COMMENT 'KDJ J值',

  -- 振幅 / 换手率 / 量比
  `swing`        DECIMAL(8,4)     DEFAULT NULL              COMMENT '振幅 = (最高-最低)/昨收*100 单位：%',
  `turnover_rate` DECIMAL(8,4)   DEFAULT NULL              COMMENT '换手率 单位：%',
  `volume_ratio`  DECIMAL(8,4)   DEFAULT NULL              COMMENT '量比 = 当日成交量/前5日均量',

  `updated_at`   DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY  `uk_code_date`     (`ts_code`, `trade_date`),
  KEY         `idx_trade_date`    (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每日技术指标增强表（均线/MACD/RSI/BOLL/KDJ/振幅/换手率/量比）';

-- ─────────────────────────────────────────────────────────────
-- 表2：stock_daily_capital  每日资金流向数据
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `stock_daily_capital` (
  `id`          BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `ts_code`     VARCHAR(20)      NOT NULL                  COMMENT '证券代码',
  `trade_date`  DATE             NOT NULL                  COMMENT '交易日期',

  -- 按资金规模分档的净流入（单位：元）
  `main_inflow`   DECIMAL(20,2)   DEFAULT NULL              COMMENT '主力净流入 = 超大单+大单净流入',
  `super_inflow`  DECIMAL(20,2)  DEFAULT NULL              COMMENT '超大单净流入（>=100万）',
  `big_inflow`    DECIMAL(20,2)  DEFAULT NULL              COMMENT '大单净流入（20~100万）',
  `mid_inflow`    DECIMAL(20,2)  DEFAULT NULL              COMMENT '中单净流入（4~20万）',
  `small_inflow`  DECIMAL(20,2)  DEFAULT NULL              COMMENT '小单净流入（<4万）',

  -- 北向资金（沪深港通）
  `north_money`   DECIMAL(20,2)  DEFAULT NULL              COMMENT '北向资金当日持股变动（元）',
  `north_hold`    DECIMAL(20,2)  DEFAULT NULL              COMMENT '北向资金持仓总市值（元）',

  -- 融资融券
  `margin`        DECIMAL(20,2)   DEFAULT NULL              COMMENT '融资余额（元）',
  `margin_change` DECIMAL(20,2)  DEFAULT NULL              COMMENT '融资余额变动（元）',

  `updated_at`   DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY  `uk_code_date`     (`ts_code`, `trade_date`),
  KEY         `idx_trade_date`    (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每日资金流向数据（主力/北向/融资融券）';

-- ─────────────────────────────────────────────────────────────
-- 表3：stock_daily_events  每日事件与风险标记
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `stock_daily_events` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `ts_code`       VARCHAR(20)     NOT NULL                  COMMENT '证券代码',
  `trade_date`    DATE            NOT NULL                  COMMENT '交易日期',

  -- 涨跌停标记（不区分ST，原始涨跌停）
  `is_limit_up`   TINYINT         DEFAULT 0                COMMENT '是否涨停：0否 1是',
  `is_limit_down` TINYINT         DEFAULT 0                COMMENT '是否跌停：0否 1是',

  -- 均线跌破/突破
  `is_break_ma20` TINYINT         DEFAULT 0                COMMENT '是否跌破20日均线：0否 1是',
  `is_break_ma60` TINYINT         DEFAULT 0                COMMENT '是否跌破60日均线：0否 1是',

  -- 高低点标记
  `is_high_1y`    TINYINT         DEFAULT 0                COMMENT '是否创1年新高：0否 1是',
  `is_low_1y`     TINYINT         DEFAULT 0                COMMENT '是否创1年新低：0否 1是',

  -- 限售股解禁
  `is_unlock_day` TINYINT         DEFAULT 0                COMMENT '当日是否有解禁：0否 1是',
  `unlock_ratio`   DECIMAL(8,4)   DEFAULT NULL              COMMENT '解禁数量占总股本比例 单位：%',

  `updated_at`     DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY  `uk_code_date`     (`ts_code`, `trade_date`),
  KEY         `idx_trade_date`    (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每日事件与风险标记（涨跌停/均线突破/高低点/解禁）';

-- ─────────────────────────────────────────────────────────────
-- 表4：stock_daily_funda  每日基本面估值数据
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `stock_daily_funda` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `ts_code`         VARCHAR(20)     NOT NULL                  COMMENT '证券代码',
  `trade_date`      DATE            NOT NULL                  COMMENT '交易日期',

  -- 估值指标
  `pe_ttm`          DECIMAL(12,4)  DEFAULT NULL              COMMENT 'PE-TTM 市盈率（滚动市盈率）',
  `pb_mrq`          DECIMAL(12,4)  DEFAULT NULL              COMMENT 'PB-MRQ 市净率（MRQ净资产）',
  `ps_ttm`          DECIMAL(12,4)  DEFAULT NULL              COMMENT 'PS-TTM 市销率（滚动）',

  -- 股息率
  `dividend_yield`  DECIMAL(10,4)  DEFAULT NULL              COMMENT '股息率（近12个月）单位：%',

  -- 股本结构（单位：万股）
  `total_share`     DECIMAL(20,2)  DEFAULT NULL              COMMENT '总股本',
  `float_share`     DECIMAL(20,2)  DEFAULT NULL              COMMENT '流通股本',

  -- 市值（单位：元）
  `market_cap`      DECIMAL(20,2)  DEFAULT NULL              COMMENT '总市值 = 股价*总股本',
  `float_cap`       DECIMAL(20,2)  DEFAULT NULL              COMMENT '流通市值 = 股价*流通股本',

  -- 股东数据
  `holder_num`      INT             DEFAULT NULL              COMMENT '股东户数（人）',
  `holder_change`   DECIMAL(10,4)  DEFAULT NULL              COMMENT '股东户数环比变化 单位：%',

  `updated_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY  `uk_code_date`     (`ts_code`, `trade_date`),
  KEY         `idx_trade_date`    (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='每日基本面估值数据（PE/PB/PS/股息率/股本/市值/股东数）';

-- ─────────────────────────────────────────────────────────────
-- 表5：stock_market_overview  全市场每日情绪数据
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `stock_market_overview` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `trade_date`      DATE            NOT NULL                  COMMENT '交易日期',

  -- 涨跌家数统计
  `rise_count`      INT             DEFAULT NULL              COMMENT '上涨家数',
  `fall_count`      INT             DEFAULT NULL              COMMENT '下跌家数',
  `limit_up_count`  INT             DEFAULT NULL              COMMENT '涨停家数（含ST）',
  `limit_down_count` INT            DEFAULT NULL              COMMENT '跌停家数（含ST）',

  -- 全市场成交量/额
  `total_volume`    DECIMAL(24,2)   DEFAULT NULL              COMMENT '全市场总成交量（股）',
  `total_amount`    DECIMAL(24,2)   DEFAULT NULL              COMMENT '全市场总成交额（元）',

  -- 沪指（沪深300或上证指数）
  `index_close`     DECIMAL(10,4)   DEFAULT NULL              COMMENT '沪指收盘点位',
  `index_pct`       DECIMAL(10,4)   DEFAULT NULL              COMMENT '沪指涨跌幅 单位：%',

  -- 赚钱效应
  `earn_ratio`      DECIMAL(8,4)    DEFAULT NULL              COMMENT '全市场赚钱效应 = 上涨家数/总交易股票数 单位：%',

  `updated_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY  `uk_date`           (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='全市场每日情绪数据（涨跌家数/涨停/成交量/沪指/赚钱效应）';

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================
-- 验证：确认原有3张表仍然完整
-- =============================================================
-- SELECT '=== 原有表检查 ===';
-- SELECT COUNT(*) AS stock_basic_rows    FROM stock_basic;
-- SELECT COUNT(*) AS daily_price_rows   FROM stock_daily_price;
-- SELECT COUNT(*) AS chip_dist_rows     FROM stock_chip_distribution;
-- SELECT '=== 新增表检查 ===';
-- SELECT COUNT(*) AS indicator_rows      FROM stock_daily_indicator;
-- SELECT COUNT(*) AS capital_rows        FROM stock_daily_capital;
-- SELECT COUNT(*) AS events_rows         FROM stock_daily_events;
-- SELECT COUNT(*) AS funda_rows         FROM stock_daily_funda;
-- SELECT COUNT(*) AS overview_rows      FROM stock_market_overview;
