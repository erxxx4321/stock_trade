import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from FinMind.data import DataLoader

api = DataLoader()


def calculate_candle_parts(df):
    """
    計算 K 棒的各部分長度
    """
    # 計算實體長度 (絕對值)
    body = abs(df["Close"] - df["Open"])
    # 計算上影線長度
    upper_wick = df["High"] - df[["Open", "Close"]].max(axis=1)
    # 計算下影線長度
    lower_wick = df[["Open", "Close"]].min(axis=1) - df["Low"]
    # 計算總範圍
    total_range = df["High"] - df["Low"]

    # 避免除以零
    total_range[total_range == 0] = 0.0001

    # 計算比例
    body_ratio = body / total_range
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range

    return body_ratio, upper_wick_ratio, lower_wick_ratio


def classify_single_candle(df):
    """
    分類單根 K 棒型態
    """
    body_ratio, upper_wick_ratio, lower_wick_ratio = calculate_candle_parts(df)

    conditions = []
    classifications = []

    is_bullish = df["Close"] > df["Open"]
    is_bearish = df["Close"] < df["Open"]

    # 1. 實體很小的紡錘線/十字線
    condition = body_ratio < 0.3
    conditions.append(condition)
    classifications.append("Spinning_Top")

    # 2. 實體很長的長陽線/長陰線
    condition = body_ratio > 0.7
    conditions.append(condition)
    classifications.append("Long_Body")

    # 3. 錘子線 (下影線很長，實體在上部)
    condition = (lower_wick_ratio > 0.6) & (body_ratio < 0.4) & is_bullish
    conditions.append(condition)
    classifications.append("Hammer")

    # 4. 吊頸線 (形態同錘子，但出現在上升趨勢後)
    condition = (lower_wick_ratio > 0.6) & (body_ratio < 0.4) & is_bearish
    conditions.append(condition)
    classifications.append("Hanging_Man")

    # 5. 射擊之星 (上影線很長，實體在下部)
    condition = (upper_wick_ratio > 0.6) & (body_ratio < 0.4)
    conditions.append(condition)
    classifications.append("Shooting_Star")

    # 6. 十字線 (實體極小)
    condition = body_ratio < 0.1
    conditions.append(condition)
    classifications.append("Doji")

    # 預設為一般 K 棒
    result = pd.Series(["Normal"] * len(df), index=df.index)

    # 依優先級套用分類 (從最特殊的開始)
    for cond, classification in zip(conditions[::-1], classifications[::-1]):
        result[cond] = classification

    return result


def candle_strength(df):
    """
    判斷 K 棒的多空強度
    """
    # 計算實體長度 (帶方向)
    body = df["Close"] - df["Open"]
    # 計算實體佔總範圍的比例 (帶方向)
    total_range = df["High"] - df["Low"]
    body_ratio = body / total_range

    # 強度分類
    conditions = [
        body_ratio > 0.3,  # 強力多頭
        body_ratio > 0.1,  # 溫和多頭
        body_ratio < -0.3,  # 強力空頭
        body_ratio < -0.1,  # 溫和空頭
    ]
    choices = ["Strong_Bull", "Mild_Bull", "Strong_Bear", "Mild_Bear"]

    strength = pd.Series("Neutral", index=df.index)
    for cond, choice in zip(conditions, choices):
        strength[cond] = choice

    return strength


with st.form(key="form"):
    col_1, col_2, col_3 = st.columns(3)
    with col_1:
        ticker = st.text_input("請輸入股票代號:", value="")
    with col_2:
        tw_us = st.selectbox("台美", options=["TW", "US"], key="country_selector")
    with col_3:
        months_ago = st.selectbox(
            "選擇歷史資料月數:", options=[1, 2, 3], index=2, key="months_selector"
        )
    submitted = st.form_submit_button("執行")

if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(months=months_ago)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        if tw_us == "TW":
            df = api.taiwan_stock_daily(
                stock_id=ticker, start_date=start_date, end_date=end_date
            )
        else:
            df = api.us_stock_price(
                stock_id=ticker, start_date=start_date, end_date=end_date
            )

        df.rename(
            columns={
                "open": "Open",
                "max": "High",
                "min": "Low",
                "close": "Close",
                "spread": "Spread",
                "Trading_Volume": "Volume",
                "Trading_turnover": "Turnover",
            },
            inplace=True,
        )

        df["Strength"] = candle_strength(df)
        df["Candle_Type"] = classify_single_candle(df)
        df["20MA"] = df["Close"].rolling(window=20).mean().round(2)

        if "^" in ticker:
            df = df.drop(
                columns=["stock_id", "Adj_Close", "Open", "High", "Low", "Volume"]
            )
        else:
            df = df.drop(columns=["stock_id", "Open", "High", "Low", "Trading_money", "Spread", "Turnover"])

        df = df.sort_index(ascending=False)
        if not df.empty:
            st.dataframe(df)
    except Exception as e:
        st.error(f"發生錯誤: {e}")
