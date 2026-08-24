#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
選股程式：從證交所抓取上市/上櫃股票清單，再以 yfinance 5 日均量做過濾
"""
import argparse
import json
import os
import time

import pandas as pd
import requests
import yfinance as yf
from tqdm import tqdm

TWSE_BASE_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
VOLUME_THRESHOLD_LOTS = 1000  # 5 日均量門檻（張）
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "my_stock.json")

# strMode=2 上市，strMode=4 上櫃
MARKETS = {
    "listed": {"strMode": 2, "suffix": ".TW", "json_key": "listed_{cond}", "label": "上市"},
    "otc": {"strMode": 4, "suffix": ".TWO", "json_key": "otc_{cond}", "label": "上櫃"},
}


def fetch_twse_stock_list(strMode, label):
    """從證交所（TWSE）爬取最新的上市/上櫃股票清單"""
    print(f"正在從證交所獲取{label}股票清單...")
    response = requests.get(TWSE_BASE_URL.format(mode=strMode), timeout=15)
    response.encoding = "big5"

    dfs = pd.read_html(response.text)
    df = dfs[0]

    df.columns = df.iloc[0]
    df = df.iloc[1:]
    df = df.dropna(subset=["產業別"])

    df["代號"] = df["有價證券代號及名稱"].apply(lambda x: x.split("　")[0].strip())
    df["名稱"] = df["有價證券代號及名稱"].apply(lambda x: x.split("　")[-1].strip())

    df_stocks = df[df["代號"].str.match(r"^\d{4}$")]
    print(f"✓ 共取得 {len(df_stocks)} 檔{label}個股")
    return df_stocks[["代號", "名稱"]].reset_index(drop=True)


def filter_by_volume(df_stocks, suffix, threshold_lots=VOLUME_THRESHOLD_LOTS):
    """以 yfinance 5 日均量過濾，門檻為 threshold_lots 張（1 張 = 1000 股）"""
    print(f"正在以 yfinance 篩選 5 日均量 > {threshold_lots} 張的個股...")
    threshold_shares = threshold_lots * 1000

    selected = []
    for code, name in tqdm(list(df_stocks.itertuples(index=False, name=None))):
        ticker = f"{code}{suffix}"
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty or "Volume" not in hist:
                continue
            avg_volume = hist["Volume"].tail(5).mean()
            if avg_volume > threshold_shares:
                selected.append(code)
        except Exception as e:
            print(f"  ✗ {code} {name} 取得資料失敗: {e}")
        time.sleep(0.1)

    print(f"✓ 篩選出 {len(selected)} 檔符合條件的個股")
    return selected


def load_existing_output():
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="從證交所爬取上市/上櫃股票並依 5 日均量篩選")
    parser.add_argument(
        "--market",
        choices=["listed", "otc", "all"],
        default="all",
        help="選擇要爬取的市場：listed（上市）、otc（上櫃）、all（兩者皆抓，預設）",
    )
    args = parser.parse_args()

    markets = ["listed", "otc"] if args.market == "all" else [args.market]

    result = load_existing_output()
    for market in markets:
        cfg = MARKETS[market]
        df_stocks = fetch_twse_stock_list(cfg["strMode"], cfg["label"])
        selected = filter_by_volume(df_stocks, cfg["suffix"])
        json_key = cfg["json_key"].format(cond="5vol")
        result[json_key] = selected

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✓ 已儲存至 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
