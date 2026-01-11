import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from FinMind.data import DataLoader
import utils

api = DataLoader()
watch_list = utils.query_data(
    "SELECT stock_code, buy_strategy, sell_strategy FROM watch_list;"
)
strategy_map = {}
for stock_code, buy_strategy, sell_strategy in watch_list:
    strategy_map[stock_code] = (buy_strategy, sell_strategy)

note_dates = utils.query_data("SELECT note_name, note_date FROM note_date;")
notedate_map = {}
for note_name, note_date in note_dates:
    notedate_map[note_date] = note_name


def get_buy_sell_strategy():
    buy_val, sell_val = strategy_map.get(
        st.session_state.my_input,
        ("", ""),
    )
    st.session_state["buy_select"] = buy_val
    st.session_state["sell_select"] = sell_val


st.set_page_config(
    page_title="First Trade",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)


ticker = st.text_input(
    "請輸入股票代號:",
    key="my_input",
    on_change=get_buy_sell_strategy,
)

with st.form(key="form"):
    select_col1, select_col2 = st.columns(2)
    with select_col1:
        buy_strategy = st.selectbox(
            "買點條件:",
            options=[""] + [strategy.value for strategy in utils.BuyStrategy],
            key="buy_select",
        )
    with select_col2:
        sell_strategy = st.selectbox(
            "賣點條件:",
            options=[""] + [strategy.value for strategy in utils.SellStrategy],
            key="sell_select",
        )
    check_col1, check_col2, check_col3, check_col4 = st.columns(4)
    with check_col1:
        show_high_close_signal = st.checkbox("高檔", True)
    with check_col2:
        show_high_vol_signal = st.checkbox("爆量", True)
    submitted = st.form_submit_button("執行")

if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(years=3)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        # 1. 取得每日股價資料
        df_stock = api.taiwan_stock_daily(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df_stock.rename(
            columns={
                "max": "High",
                "min": "Low",
                "close": "Close",
                "open": "Open",
                "Trading_Volume": "Volume",
            },
            inplace=True,
        )
        
        # 取得外資、投信買賣超資料
        df_investor = api.taiwan_stock_institutional_investors(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df_investor["value"] = df_investor["buy"] - df_investor["sell"]
        df_investor = df_investor.pivot_table(
            index="date", columns="name", values="value"
        )
        df_investor = df_investor.reset_index()

        # 取得PER、PBR、殖利率
        df_per = api.taiwan_stock_per_pbr(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )

        # 2. 使用自訂函式計算 KDJ 和布林通道
        df_kdj = utils.calculate_kdj(df_stock.copy())
        df_bb = utils.calculate_bollinger_bands(df_stock.copy())
        df_rsi = utils.calculate_rsi(df_stock.copy())

        # 3. 將計算結果合併回股價資料
        df = pd.merge(df_stock, df_kdj[["k", "d"]], left_index=True, right_index=True, how="left")
        df = pd.merge(df, df_bb, left_index=True, right_index=True, how="left")
        df = pd.merge(df, df_rsi, left_index=True, right_index=True, how="left")
        df = pd.merge(
            df,
            df_investor[["date", "Foreign_Investor", "Investment_Trust"]],
            on="date",
            how="left",
        )
        if df_per.empty:
            df_per = pd.DataFrame(columns=["date", "PER", "PBR"])
        df = pd.merge(df, df_per[["date", "PER", "PBR"]], on="date", how="left")

        buy_condition, sell_condition = utils.get_trade_condition(
            df, buy_strategy, sell_strategy
        )

        # 使用 .shift(1) 取得前一日收盤價
        df["Prev_Close"] = df["Close"].shift(1)

        # 計算漲跌幅百分比
        df["Change"] = ((df["Close"] - df["Prev_Close"]) / df["Prev_Close"]) * 100

        # 刪除輔助欄位
        df.drop(columns=["Prev_Close"], inplace=True)

        # 新增訊號欄位
        df["Signal"] = np.select(
            [buy_condition, sell_condition], ["Buy", "Sell"], default=""
        )

        # 高檔爆量判斷
        df["High_Close"] = (
            df["Close"] == df["Close"].rolling(window=60, min_periods=1).max()
        )
        df["High_Volume"] = (
            df["Volume"] == df["Volume"].rolling(window=60, min_periods=1).max()
        )

        # --- 增加輔助指標計算 ---
        df["Vol_MA5"] = df["Volume"].rolling(window=5).mean()
        df["Close_MA5"] = df["Close"].rolling(window=5).mean()

        # 計算 K 線組成，用於判斷「長上影線」
        df["Body"] = abs(df["Close"] - df["Open"]) # 這裡需確保 df 有 Open 欄位
        df["Upper_Shadow"] = df["High"] - df[["Close", "Open"]].max(axis=1)

        # 1. 天量見頂 (Blow-off Top)
        # 條件：成交量 > 5日均量 2.5 倍 且 有長上影線 且 位於 60 日高點
        df["Signal_BlowOff"] = (
            (df["Volume"] > df["Vol_MA5"] * 2.5) & 
            (df["Upper_Shadow"] > df["Body"]) & 
            df["High_Close"]
        )

        # 2. 量價背離 (Divergence) - 簡化版：股價創 20 日新高但量卻低於 5 日均量
        df["Signal_Divergence"] = (
            (df["Close"] > df["Close"].rolling(window=20).max().shift(1)) & 
            (df["Volume"] < df["Vol_MA5"])
        )

        # 3. 高檔爆量長黑 (Bearish Volume)
        # 條件：跌幅 > 3% 且 成交量大於 5 日均量 且 股價低於 5 日線
        df["Signal_Bearish"] = (
            (df["Change"] < -3) & 
            (df["Volume"] > df["Vol_MA5"]) & 
            (df["Close"] < df["Close_MA5"])
        )

        # 4. 警示文字整合
        def get_warning_text(row):
            warnings = []
            if row["Signal_BlowOff"]: warnings.append("⚠️天量見頂")
            if row["Signal_Divergence"]: warnings.append("📉量價背離")
            if row["Signal_Bearish"]: warnings.append("🚫爆量長黑")
            return " ".join(warnings)

        df["Warning"] = df.apply(get_warning_text, axis=1)

        # 5. 排序並顯示資料
        df = df.sort_index(ascending=False)
        df_display = df[
            [
                "date",
                "High",
                "Low",
                "Close",
                "Change",
                "Warning",
                "Signal",
                "Volume",
                "k",
                "d",
                "rsi",
                "Upper",
                "Lower",
                "High_Close",
                "High_Volume",
                "Foreign_Investor",
                "Investment_Trust",
                "PER",
                "PBR",
            ]
        ]

        def style_rsi(val):
            if isinstance(val, (int, float)) and val < 30:
                return "background-color: #d4edda"
            return ""

        def style_df(df):
            styles = pd.DataFrame("", index=df.index, columns=df.columns)
            styles.loc[df["Signal"] == "Buy", "Signal"] = "color: #7CFC00"
            styles.loc[df["Signal"] == "Sell", "Signal"] = "color: #FF0000"

            if show_high_close_signal:
                styles.loc[df["High_Close"], ["Close"]] = "background-color: #f8d7da"
            if show_high_vol_signal:
                styles.loc[df["High_Volume"], ["Volume"]] = "background-color: #f8d7da"

            df_dates = df["date"]
            for index, date_str in df_dates.items():
                curr_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                for note_date, note_name in notedate_map.items():
                    note_date = datetime.strptime(note_date, "%Y-%m-%d").date()
                    date_diff = (note_date - curr_date).days
                    if 0 <= date_diff <= 10:
                        date_style = "background-color: #FFB3C1; font-weight: bold;"
                        styles.loc[index, "date"] = date_style
                        df.loc[index, "date"] = f"{date_str} ({note_name})"

            return styles

        if not df_display.empty:
            styled_df = df_display.style.apply(style_df, axis=None).format(
                {"Volume": "{:,.0f}"}
            )
            st.dataframe(
                styled_df,
                column_config={
                    "High": None,
                    "Low": None,
                    "High_Close": None,
                    "High_Volume": None,
                    "Foreign_Investor": None,
                    "Investment_Trust": None,
                    "PER": None,
                    "PBR": None,
                    "Upper": None,
                    "Lower": None,
                    "Change": st.column_config.NumberColumn(
                        format="%.2f%%",  # 格式：小數點後兩位，並加上 % 符號
                        help="當日收盤價相較於前一日的漲跌幅百分比",
                    ),
                },
            )
            # styled_df = styled_df.map(style_rsi, subset=['rsi'])

            st.success("資料取得與計算成功！")
        else:
            st.warning("查無此股票代號的資料，請確認代號是否正確。")

    except Exception as e:
        st.error(f"發生錯誤: {e}")
