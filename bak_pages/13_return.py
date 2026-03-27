import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import matplotlib.pyplot as plt
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
    years_ago = st.selectbox(
        "選擇歷史資料年數:", options=[1, 2, 3, 5], index=2, key="years_selector"
    )
    submitted = st.form_submit_button("執行")
if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(years=years_ago)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        df = api.taiwan_stock_daily(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df["return"] = df["close"].pct_change() * 100

        # 將報酬率分為正負兩組
        positive_returns = df["return"][df["return"] > 0]
        negative_returns = df["return"][df["return"] < 0]
        overall_mean_return = df["return"].dropna().mean()

        plt.subplots(figsize=(10, 6))
        plt.hist(
            negative_returns.dropna(),
            bins=20,
            alpha=0.7,
            label="負報酬率",
            color="green",
        )
        plt.hist(
            positive_returns.dropna(), bins=20, alpha=0.7, label="正報酬率", color="red"
        )

        # 新增整體報酬率平均線
        plt.axvline(
            overall_mean_return,
            color="blue",
            linestyle="dashed",
            linewidth=1,
            label=f"整體平均報酬率: {overall_mean_return:.2f}%",
        )
        plt.legend()
        plt.xlabel("報酬率%")
        plt.ylabel("次數")
        plt.title(f"正負報酬率分布圖:{ticker}")
        st.pyplot(plt)
    except Exception as e:
        st.error(f"發生錯誤: {e}")
