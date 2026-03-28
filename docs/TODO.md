# TODO - 项目整理与重构

> 整理时间：2026-03-28

---

## 一、动植物图鉴（bio_server）

### 1.1 数据问题
- [x] `animal` 表混入了 45 条植物记录 → **已清理**
- [ ] 部分植物在 animal 表、部分是 plants 表（梅花/桃花/樱花/海棠等）→ **待合并确认**
- [x] `plants_data.json` 缓存文件需与数据库同步 → **已改为实时查询**

### 1.2 功能问题
- [ ] 脑图页面 `/mindmap` 渲染逻辑复杂，节点/连线有重复 → **待重构**
- [x] seen.html 页面脑图入口按钮找不到 → **已修复**（flex-wrap）
- [ ] 搜索无结果时代码 400（URL中文编码问题）→ **待修复**
- [ ] 物种详情页照片显示 `/photos/<id>` 找不到 → **待查**

### 1.3 代码结构问题
- [x] 所有业务逻辑写在 `bio_server.py` 单文件 → **需拆分**
- [ ] 无单元测试
- [ ] 日志输出分散
- [ ] 数据库密码硬编码
- [ ] `bio_server_new.py` 重复文件需清理

### 1.4 待新增功能
- [ ] 用户注册/登录（当前只有 admin 账户）
- [ ] 物种详情页可查看其他用户拍的照
- [ ] 导出见过记录为 Excel/CSV

---

## 二、A股风向标（stock_app）⭐ 重构进行中

### 2.1 新项目结构（已完成）✅
- [x] Blueprint 模块化拆分（stock/strategy/market/search）
- [x] 工具模块分离（db.py, helpers.py）
- [x] config.py 配置管理
- [x] run.py 启动入口
- [x] requirements.txt

### 2.2 API 修复
- [x] `stock_basic.is_hs` → 修正为 `is_active`
- [x] `stock_daily_indicator.name` → 改为 JOIN `stock_basic`
- [x] `volume_ratio` 为 NULL 的处理（COALESCE）
- [x] 最新交易日无 MA 数据 → 改为取最近有 MA 的日期
- [x] `stock_market_overview` 空表时降级为从 price 表实时计算
- [x] `golden_cross_track` 与 `stock_daily_price` collation 冲突 → 用 CONVERT() 子查询解决
- [x] 前端 fetch 改用 XMLHttpRequest，加 8 秒超时，禁用缓存
- [ ] **待验证**：前端页面实际运行效果

### 2.3 待处理
- [ ] stock_daily_indicator 表 MA 金叉标记数据不完整（近5日几乎无数据）
- [ ] 添加数据库索引优化查询
- [ ] 添加单元测试
- [ ] systemd service 脚本

---

## 三、重构目标

### 项目结构（已完成 stock_app）
```
projects/
  bio_app/              # 动植物图鉴（待重构）
  stock_app/            # A股风向标 ✅ 已完成
    app/
      routes/          # stock.py | strategy.py | market.py | search.py
      services/
      models/
      utils/           # db.py | helpers.py
    static/
    templates/
    config.py
    run.py
    requirements.txt
    tests/
```

### 技术栈
- **后端**：Python 3.12 + Flask（保持现有依赖最小化）
- **数据库**：MySQL（现有）
- **前端**：原生 HTML/JS（保持轻量，不引入 React/Vue）
- **测试**：pytest + coverage
- **部署**：systemd service + nginx 反向代理

---

## 四、执行计划

### ✅ Phase 1：文档 & 清理（今天）
- [x] 写 TODO.md
- [ ] 清理废弃脚本（animal_server.py, bio_server_new.py 等）

### ✅ Phase 2：A股风向标重构
- [x] 拆分 stock_api.py（Blueprint 结构）
- [x] 修复所有 API 路由列名/数据问题
- [x] 添加超时、缓存控制
- [ ] 验证前端页面实际运行
- [ ] 添加单元测试

### Phase 3：动植物图鉴重构
- [ ] 拆分 bio_server.py
- [ ] 重构脑图页面（简洁 N 叉树布局）
- [ ] 修复物种照片路径问题
- [ ] 添加用户注册/登录
- [ ] 添加单元测试

### Phase 4：部署 & 监控
- [ ] systemd service 脚本
- [ ] nginx 配置
- [ ] 日志管理
