import streamlit as st
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from FinMind.data import DataLoader

api = DataLoader()
plt.rcParams["font.sans-serif"] = [
    "Arial Unicode MS",
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK TC",
]
plt.rcParams["axes.unicode_minus"] = False

with st.form(key="form"):
    ticker = st.text_input("請輸入股票代號:", value="")
    submitted = st.form_submit_button("執行")
if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(months=12)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        df = api.taiwan_stock_daily(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )

        diff_close = df["close"].diff()
        df["OBV_Direction"] = np.where(
            diff_close > 0,
            df["Trading_Volume"],
            np.where(diff_close < 0, -df["Trading_Volume"], 0),
        )
        df["OBV"] = df["OBV_Direction"].cumsum().fillna(0)

        # --- 繪製股價與OBV走勢圖 ---
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
        plt.rcParams["axes.unicode_minus"] = False

        fig, (ax1, ax2) = plt.subplots(
            2, 1, sharex=True, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]}
        )

        # 繪製第一個子圖 (ax1): 股價走勢
        ax1.plot(
            df["date"],
            df["close"],
            label="股價走勢 (收盤價)",
            color="blue",
            linewidth=2,
        )
        ax1.set_title("股價走勢與 OBV 能量潮指標", fontsize=14)
        ax1.set_ylabel("收盤價 (Close)", fontsize=14)
        ax1.legend(loc="upper left", fontsize=12)
        ax1.grid(True, linestyle="--", alpha=0.6)

        # 繪製第二個子圖 (ax2): OBV 走勢
        ax2.plot(df["date"], df["OBV"], label="OBV (能量潮)", color="red", linewidth=2)
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=15))
        ax2.set_xlabel("日期", fontsize=14)
        ax2.set_ylabel("OBV 值", fontsize=14)
        ax2.legend(loc="upper left", fontsize=12)
        ax2.grid(True, linestyle="--", alpha=0.6)

        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(plt)
    except Exception as e:
        st.error(f"發生錯誤: {e}")
