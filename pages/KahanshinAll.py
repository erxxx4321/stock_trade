import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import concurrent.futures
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="KahanshinAll", layout="wide")


# --- FinMind API 基礎函數 ---
@st.cache_data(ttl=3600)
def get_full_stock_list():
    """獲取完整的股票清單包含產業資訊"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo"}
    resp = requests.get(url, params=params)
    df = pd.DataFrame(resp.json()["data"])
    # 只取普通股 (長度為 4 的數字代碼)
    return df[df["stock_id"].str.len() == 4].reset_index(drop=True)


def fetch_and_analyze(stock_id, stock_name, start_date, min_vol, price_range):
    """增加第一層量價篩選邏輯"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
        "token": os.environ["FINMIND_API"],
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json().get("data", [])
        if not data or len(data) < 6:
            return None

        df = pd.DataFrame(data)
        last_row = df.iloc[-1]

        # --- 第一層濾網：量價檢查 ---
        # 檢查昨日成交張數 (FinMind 的 Trading_Volume 單位通常是股)
        vol_lots = last_row["Trading_Volume"] / 1000
        curr_price = last_row["close"]

        if vol_lots < min_vol:
            return None
        if not (price_range[0] <= curr_price <= price_range[1]):
            return None

        # --- 第二層：下半身演算法 ---
        # (同前述邏輯...)
        df = df.rename(
            columns={"open": "Open", "max": "High", "min": "Low", "close": "Close"}
        )
        df["MA5"] = df["Close"].rolling(window=5).mean()
        df["MA5_slope"] = df["MA5"].diff()

        curr, prev = df.iloc[-1], df.iloc[-2]
        o, c, ma5 = curr["Open"], curr["Close"], curr["MA5"]
        slope = curr["MA5_slope"]

        # 判定下半身/逆下半身
        body_top, body_bottom = max(o, c), min(o, c)
        body_len = abs(o - c)
        above_ratio = (
            (body_top - ma5) / body_len if body_len > 0 else (1 if c > ma5 else 0)
        )
        below_ratio = (
            (ma5 - body_bottom) / body_len if body_len > 0 else (1 if c < ma5 else 0)
        )

        is_kahanshin = (
            (c >= o) and (slope >= -0.05) and (above_ratio >= 0.5 or body_bottom > ma5)
        )
        is_inverse = (
            (c < o) and (slope <= 0.05) and (below_ratio >= 0.5 or body_top < ma5)
        )

        if is_kahanshin or is_inverse:
            return {
                "Stock_ID": stock_id,
                "Stock_Name": stock_name,
                "Signal": "下半身" if is_kahanshin else "逆下半身",
                "Is_New": (is_kahanshin and prev["Close"] <= prev["MA5"])
                or (is_inverse and prev["Close"] >= prev["MA5"]),
                "Price": c,
                "Volume_Lots": int(vol_lots),
            }
    except:
        return None
    return None


with st.sidebar:
    st.header("⚙️ 第一層篩選設定")

    try:
        base_list = get_full_stock_list()
        all_industries = sorted(base_list["industry_category"].unique())
    except:
        st.error("無法取得清單，請檢查 Token")
        st.stop()

    selected_industries = st.multiselect("選擇產業 (不選則全掃)", all_industries)
    min_volume = st.number_input("最低成交量 (張)", value=1000, step=100)
    price_range = st.slider("股價區間", 0, 1000, (10, 500))

    max_threads = st.slider("掃描速度 (Thread)", 5, 20, 10)
    start_btn = st.button("開始精準掃描")

# --- 主程式邏輯 ---
if start_btn:
    # 根據產業初步過濾清單
    target_list = base_list.copy()
    if selected_industries:
        target_list = target_list[
            target_list["industry_category"].isin(selected_industries)
        ]

    st.info(f"符合清單條件共 {len(target_list)} 檔，開始進行技術面分析...")

    start_dt = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [
            executor.submit(
                fetch_and_analyze,
                row["stock_id"],
                row["stock_name"],
                start_dt,
                min_volume,
                price_range,
            )
            for _, row in target_list.iterrows()
        ]

        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            res = future.result()
            if res:
                results.append(res)
            # 每 5% 更新一次進度避免 UI 閃爍
            if i % (max(1, len(target_list) // 20)) == 0:
                progress_bar.progress((i + 1) / len(target_list))
                status_text.text(f"已檢查: {i+1} / {len(target_list)}")

    # 顯示結果
    if results:
        df_res = pd.DataFrame(results)
        up_col, down_col = st.columns(2)

        with up_col:
            st.subheader("🟢 符合下半身")
            st.dataframe(df_res[df_res["Signal"] == "下半身"], use_container_width=True)

        with down_col:
            st.subheader("🔴 符合逆下半身")
            st.dataframe(
                df_res[df_res["Signal"] == "逆下半身"], use_container_width=True
            )
    else:
        st.warning("篩選完成，符合條件的標的中無下半身訊號。")
