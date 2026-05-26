#!/usr/bin/env python3
"""分批拉同花顺板块原始数据，批间冷却，防反爬

产出: raw_sectors.json → {板块名: [股票代码列表]}
      行业和概念混存，后续再格式化
"""

import json
import re
import time
import sys
from pathlib import Path

import akshare as ak
import requests
from bs4 import BeautifulSoup
from akshare.datasets import get_ths_js
from py_mini_racer import MiniRacer

OUTPUT = Path(__file__).parent / "raw_sectors.json"
DELAY = 0.5          # 请求间隔
BATCH_SIZE = 75      # 每批板块数
COOL_DOWN = 180      # 批间冷却秒数（3分钟）
MAX_PAGES = 100      # 翻页上限
MAX_RETRY = 3        # 空返回重试次数


def get_v():
    js = MiniRacer()
    with open(get_ths_js("ths.js"), encoding="utf-8") as f:
        js.eval(f.read())
    return js.call("v")


def fetch(url, v):
    h = {"User-Agent": "Mozilla/5.0", "Cookie": f"v={v}"}
    r = requests.get(url, headers=h, timeout=10, allow_redirects=True)
    r.encoding = "gbk"
    return r.text


def parse_codes(html):
    soup = BeautifulSoup(html, "html.parser")
    codes = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            a = tds[1].find("a")
            if a and re.match(r"^\d{6}$", a.text.strip()):
                codes.append(a.text.strip())
    return codes


def get_total_pages(html):
    soup = BeautifulSoup(html, "html.parser")
    pi = soup.find("span", class_="page_info")
    if pi:
        m = re.search(r"/(\d+)", pi.text.strip())
        if m:
            return int(m.group(1))
    return 1


def fetch_board(url_template, names_df, board_type, start_idx=0):
    """拉取一批板块的原始数据"""
    results = {}
    total = len(names_df)

    for i, row in names_df.iterrows():
        name, code = row["name"], row["code"]
        idx = start_idx + i + 1

        codes = []
        v = get_v()
        try:
            url = url_template.format(code=code, page=1)
            html = fetch(url, v)
            codes = parse_codes(html)
            total_pages = get_total_pages(html)

            # 空返回重试
            retry = 0
            while len(codes) == 0 and retry < MAX_RETRY:
                retry += 1
                time.sleep(2)
                v = get_v()
                html = fetch(url, v)
                codes = parse_codes(html)
                total_pages = get_total_pages(html)

            if len(codes) == 0:
                print(f"  [{idx}/{total}] {name} 无数据，跳过")
                results[name] = []
                time.sleep(DELAY)
                continue

            # 翻页（跳过大板块）
            if 1 < total_pages <= MAX_PAGES:
                for page in range(2, total_pages + 1):
                    time.sleep(DELAY)
                    v = get_v()
                    url = url_template.format(code=code, page=page)
                    html = fetch(url, v)
                    page_codes = parse_codes(html)
                    if not page_codes:
                        # 翻页失败重试
                        time.sleep(2)
                        v = get_v()
                        html = fetch(url, v)
                        page_codes = parse_codes(html)
                    if not page_codes:
                        print(f"  [{idx}] {name} 翻页{page}/{total_pages} 失败，停止")
                        break
                    codes.extend(page_codes)

            results[name] = codes
            print(f"  [{idx}/{total}] {name}: {len(codes)}只 (共{total_pages}页)")

        except Exception as e:
            print(f"  [{idx}] {name} 异常: {e}")
            results[name] = []

        time.sleep(DELAY)

    return results


def main():
    # 加载已有数据（如果存在）
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            all_data = json.load(f)
        print(f"加载已有数据: {len(all_data)} 个板块")
    else:
        all_data = {}

    # 概念板块
    concept_names = ak.stock_board_concept_name_ths()
    print(f"概念板块: {len(concept_names)} 个")

    for batch_num in range(5):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(concept_names))
        batch_df = concept_names.iloc[start:end]

        # 跳过已完成的
        pending = batch_df[~batch_df["name"].isin(all_data)]
        if len(pending) == 0:
            print(f"\n=== 概念批次 {batch_num+1}/5 ({start+1}-{end}) 全部已拉，跳过 ===")
            continue

        print(f"\n=== 概念批次 {batch_num+1}/5 ({start+1}-{end}), 待拉 {len(pending)} 个 ===")
        new_data = fetch_board(
            "https://q.10jqka.com.cn/gn/detail/code/{code}/ajax/{page}/",
            pending, "概念", start
        )
        all_data.update(new_data)

        # 每批结束保存
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        total_stocks = sum(len(v) for v in all_data.values())
        print(f"批次 {batch_num+1} 完成, 累计: {len(all_data)} 个板块, {total_stocks} 条映射")

        if batch_num < 4:
            print(f"\n冷却 {COOL_DOWN} 秒...")
            time.sleep(COOL_DOWN)

    # 行业板块（分 2 批）
    industry_names = ak.stock_board_industry_name_ths()
    print(f"\n行业板块: {len(industry_names)} 个")

    for batch_num in range(2):
        start = batch_num * 45
        end = min(start + 45, len(industry_names))
        batch_df = industry_names.iloc[start:end]

        pending = batch_df[~batch_df["name"].isin(all_data)]
        if len(pending) == 0:
            print(f"\n=== 行业批次 {batch_num+1}/2 全部已拉，跳过 ===")
            continue

        print(f"\n=== 行业批次 {batch_num+1}/2 ({start+1}-{end}), 待拉 {len(pending)} 个 ===")
        new_data = fetch_board(
            "https://q.10jqka.com.cn/dy/detail/code/{code}/ajax/{page}/",
            pending, "行业", start
        )
        all_data.update(new_data)

        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        total_stocks = sum(len(v) for v in all_data.values())
        print(f"批次 {batch_num+1} 完成, 累计: {len(all_data)} 个板块, {total_stocks} 条映射")

        if batch_num < 1:
            print(f"\n冷却 {COOL_DOWN} 秒...")
            time.sleep(COOL_DOWN)

    # 最终汇总
    total_stocks = sum(len(v) for v in all_data.values())
    print(f"\n===== 全部完成 =====")
    print(f"板块: {len(all_data)} 个, 总映射: {total_stocks} 条")
    print(f"文件: {OUTPUT}")


if __name__ == "__main__":
    main()
