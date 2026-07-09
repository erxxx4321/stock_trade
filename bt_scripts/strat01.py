import pandas as pd
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
from FinMind.data import DataLoader


def run_free_tier_scan():
    api = DataLoader()

    # 1. 取得所有股票代號 (此功能通常免費)
    print("📋 正在取得台股代號清單...")
    stock_info = api.taiwan_stock_info()
    # 過濾出上市、上櫃的普通股 (4 碼)
    all_tickers = stock_info[
        (stock_info["type"].isin(["twse", "otc"]))
        & (stock_info["stock_id"].str.len() == 4)
    ]["stock_id"].tolist()

    # 測試用：可以先取前 100 檔測試速度，確認沒問題再跑全場
    # all_tickers = all_tickers[:100]

    start_date = (datetime.now() - relativedelta(months=2)).strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")

    print(f"🚀 開始掃描市場 (共 {len(all_tickers)} 檔)...")
    final_winners = []

    for ticker in tqdm(all_tickers):
        try:
            # --- 第一關：抓取日股價 ---
            # 使用 api.data_loader.taiwan_stock_daily (視你的載入方式而定)
            df = api.taiwan_stock_daily(
                stock_id=ticker, start_date=start_date, end_date=today_str
            )

            if df is None or df.empty or len(df) < 20:
                continue

            # --- [漏斗過濾 1]：成交金額是否達 6,000 萬 ---
            curr = df.iloc[-1]
            turnover = curr["close"] * curr["Trading_Volume"]
            if turnover < 60000000:
                continue  # 不達標，直接跳過後續昂貴的資券查詢

            # --- 第二關：抓取信用交易 (僅針對量能過關的) ---
            df_margin = api.taiwan_stock_margin_purchase_short_sale(
                stock_id=ticker, start_date=start_date, end_date=today_str
            )
            if df_margin is None or df_margin.empty:
                continue

            # --- 第三關：計算技術指標與邏輯判定 ---
            df = pd.merge(
                df, df_margin, on=["date", "stock_id"], how="left"
            ).sort_values("date")

            # 1. 券資比
            df["short_ratio"] = (
                df["ShortSaleTodayBalance"] / df["MarginPurchaseTodayBalance"]
            ) * 100

            # 2. KD (9, 3, 3) 手動計算
            low_9 = df["low"].rolling(9).min()
            high_9 = df["high"].rolling(9).max()
            df["rsv"] = (df["close"] - low_9) / (high_9 - low_9) * 100
            df["K"] = df["rsv"].fillna(50).ewm(com=2, adjust=False).mean()

            # 3. MA20 與 10日高低差
            df["MA20"] = df["close"].rolling(20).mean()
            df["range_10d"] = (
                df["high"].rolling(10).max() - df["low"].rolling(10).min()
            ) / df["low"].rolling(10).min()

            # 策略條件
            curr = df.iloc[-1]
            past_15 = df.iloc[-15:-1]

            cond1 = curr["range_10d"] >= 0.20
            cond2 = (past_15["K"] > 80).any()
            cond3 = curr["K"] < 50
            cond4 = curr["close"] > curr["MA20"]
            cond5 = curr["short_ratio"] >= 5.0

            if all([cond1, cond2, cond3, cond4, cond5]):
                final_winners.append(
                    {
                        "代號": ticker,
                        "收盤": curr["close"],
                        "券資比%": round(curr["short_ratio"], 2),
                        "K值": round(curr["K"], 1),
                        "10日振幅%": round(curr["range_10d"] * 100, 1),
                        "金額(萬)": int(turnover / 10000),
                    }
                )

            # 免費版 API 通常有頻率限制，建議停頓
            time.sleep(0.1)

        except Exception as e:
            # print(f"Error processing {ticker}: {e}") # 調試時可開啟
            continue

    # --- 輸出報表 ---
    if final_winners:
        df_res = pd.DataFrame(final_winners)
        print(f"\n✅ 掃描完成！符合條件標的 ({len(final_winners)} 檔):")
        print(df_res.to_string(index=False))
        df_res.to_csv(f"scan_result_{today_str}.csv", index=False, encoding="utf-8-sig")
    else:
        print("\n今日查無符合條件之標的。")


if __name__ == "__main__":
    run_free_tier_scan()

# 1. 10 天高低差 20%：篩選「有活性的強勢股」
# 理由：如果一檔股票 10 天內波動不到 10%，代表市場對它沒興趣，或者是股性太溫。

# 邏輯：20% 的振幅確保這檔股票是**「當前市場熱點」**。只有具備這種爆發力的股票，拉回後的二次噴發才會有足夠的力道。

# 2. KD 從 K > 80 以上拉回：確認「強勢後的降溫」
# 理由：K 值曾大於 80 代表該股先前處於極度強勢（Overbought）。

# 邏輯：我們不買「正在跌」的股票，我們買的是「強勢回檔」的股票。這確保了這檔股票具備「多頭基因」，現在的下跌只是為了走更長遠的路。

# 3. K 值小於 50：尋找「性價比買點」
# 理由：避免追高風險。

# 邏輯：當 K 值從 80 修正到 50 以下，短線的超買壓力已經釋放完畢。這是一個**「安全邊際」**，讓你在技術指標相對低位進場，而非在市場瘋狂時進場。

# 4. 股價在「月空方成本」之上：維持「趨勢護城河」
# 理由：這通常指 20 日均線（20MA）。股價高於 20MA，代表近一個月買入的人平均是賺錢的。

# 邏輯：這是軋空策略的關鍵。 只要股價撐在月線之上，那些在近期放空的人（空頭）就會面臨極大的帳面虧損與心理壓力。只要股價稍有轉強，空頭就容易引發連鎖停損回補潮。

# 5. 券資比 5% 以上：埋下「軋空燃料」
# 理由：券資比代表融券（看空）相對於融資（看多）的比例。

# 邏輯：5% 是一個基本門檻（高標甚至會到 20%）。有空單，才有**「未來潛在的買盤」**。當股價回檔不破月線又重新轉強時，這些空單就是推升股價二次噴發的最強推手。

# 6. 六千萬成交金額：確保「流動性與真實性」
# 理由：過濾掉成交稀疏的「殭屍股」。

# 邏輯：如果成交量太小，技術指標容易失真，且容易被少數大戶操控。六千萬是一個初步過濾網，確保這檔股票有法人或中實戶參與，你的技術分析才具備統計上的意義。
