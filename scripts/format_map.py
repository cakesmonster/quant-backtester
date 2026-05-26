#!/usr/bin/env python3
"""raw_sectors.json → stock_sector_map.json
{板块名: [股票列表]} → {股票代码: {行业: [...], 概念: [...]}}
"""

import json
from collections import defaultdict
from pathlib import Path

import akshare as ak

RAW = Path(__file__).parent / "raw_sectors.json"
OUT = Path(__file__).parent / "stock_sector_map.json"

with open(RAW, encoding="utf-8") as f:
    raw = json.load(f)

# 获取概念和行业名集合
concept_names = set(ak.stock_board_concept_name_ths()["name"])
industry_names = set(ak.stock_board_industry_name_ths()["name"])

stock_map = defaultdict(lambda: {"行业": [], "概念": []})

for board_name, codes in raw.items():
    if board_name in concept_names:
        key = "概念"
    elif board_name in industry_names:
        key = "行业"
    else:
        print(f"未知板块: {board_name}")
        continue

    for code in codes:
        stock_map[code][key].append(board_name)

# 排序 + 去重
for code in stock_map:
    stock_map[code]["概念"] = sorted(set(stock_map[code]["概念"]))
    stock_map[code]["行业"] = sorted(set(stock_map[code]["行业"]))

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(stock_map, f, ensure_ascii=False, indent=2)

total = len(stock_map)
avg_concept = sum(len(v["概念"]) for v in stock_map.values()) / total
avg_industry = sum(len(v["行业"]) for v in stock_map.values()) / total
no_concept = sum(1 for v in stock_map.values() if len(v["概念"]) == 0)

print(f"股票: {total} 只")
print(f"平均概念: {avg_concept:.1f}, 平均行业: {avg_industry:.1f}")
print(f"无概念: {no_concept} 只")
print(f"文件: {OUT} ({OUT.stat().st_size/1024:.0f}KB)")
