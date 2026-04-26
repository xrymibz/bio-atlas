# 动植物图鉴数据库

本目录包含从 MySQL 数据库导出的完整数据。

## 数据量

- **植物**：189 条记录
- **动物**：167 条记录

## 文件说明

- `plants.json` — 植物数据（含中文名、学名、分类、特征、分布、濒危等级等）
- `animals.json` — 动物数据（含中文名、学名、分类、特征、分布、濒危等级等）

## 数据库结构（供参考）

### plants 表字段
id, name_cn, name_en, scientific_name, kingdom, phylum, class_name, order_name, family, genus, species, subspecies, category, feature, is_endangered, region, description, flower_color, leaf_type, fruit_type, habitat

### animal 表字段
id, name_cn, name_en, scientific_name, kingdom, phylum, class_name, order_name, family, genus, species, subspecies, category, feature, is_endangered, region, description, habitat

## 原始数据

原始数据存储于 `plants_data.json`（JSON 格式备份）
