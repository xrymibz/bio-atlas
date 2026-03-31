# 习惯打卡器 - 微信小程序

> 一个简单实用的每日习惯追踪小程序，支持打卡、连续天数统计

## 功能特性

- ✅ 每日打卡
- 🔥 连续打卡天数统计
- 📊 今日完成率展示
- 😊 16种图标可选
- 📱 数据本地存储

## 上传步骤

1. 打开 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 新建项目 -> 选择本文件夹
3. AppID 填写你的小程序 AppID（或使用测试号）
4. 编译运行

## 文件结构

```
habit-tracker/
├── app.js              # 小程序入口
├── app.json            # 全局配置
├── app.wxss            # 全局样式
├── sitemap.json        # sitemap 配置
├── pages/
│   ├── index/          # 首页（打卡）
│   └── add/            # 添加习惯页
└── images/             # 图标资源（需自备）
```

## 预览截图

- 首页展示所有习惯、连续打卡天数、今日打卡状态
- 添加页可自定义习惯名称和图标
- 点击打卡按钮完成每日打卡

## 注意事项

- tabBar 图标需在 `images/` 目录放入 check.png、check-active.png、add.png、add-active.png
- 或在 app.json 中注释掉 tabBar 配置

## 开源协议

MIT License
