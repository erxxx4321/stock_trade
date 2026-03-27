import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import matplotlib.pyplot as plt
import seaborn as sns
from FinMind.data import DataLoader

api = DataLoader()

with st.form(key="form"):
    ticker = st.text_input("請輸入股票代號:", value="")
    submitted = st.form_submit_button("執行")

if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(months=36)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        df = api.taiwan_stock_daily(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df_margin = api.taiwan_stock_margin_purchase_short_sale(
            stock_id=ticker,
            start_date=start_date,
            end_date=end_date,
        )
        df_investor = api.taiwan_stock_institutional_investors(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df_investor["value"] = df_investor["buy"] - df_investor["sell"]
        df_investor = df_investor.pivot_table(
            index="date", columns="name", values="value"
        )
        df_investor = df_investor.reset_index()

        df = pd.merge(df, df_margin, on="date", how="left")
        df = pd.merge(df, df_investor, on="date", how="left")
        df = df.sort_index(ascending=False)

        matrix = df[
            [
                "close",
                "MarginPurchaseTodayBalance",
                "ShortSaleTodayBalance",
                "Foreign_Investor",
                "Investment_Trust",
            ]
        ].corr()
        plt.figure(figsize=(6, 4))
        sns.heatmap(matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
        plt.title(f"Correlation Heatmap : {ticker}.TW")
        st.pyplot(plt)

    except Exception as e:
        st.error(f"發生錯誤: {e}")
