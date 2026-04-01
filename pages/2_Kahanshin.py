import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()


st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
    .main-title { font-size: 2.2rem; font-weight: 900; background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460); color: #e94560; padding: 1.2rem 1.8rem; border-radius: 12px; margin-bottom: 0.5rem; letter-spacing: 2px; text-align: center; }
    .signal-box { border-radius: 12px !important; padding: 1.5rem 2rem !important; text-align: center !important; margin: 0.5rem 0 !important; color: #ffffff !important; }
    .signal-sell  { background: linear-gradient(135deg,#1b4332,#2d6a4f) !important; border: 2px solid #52b788 !important; }
    .signal-buy { background: linear-gradient(135deg,#641220,#a4133c) !important; border: 2px solid #ff4d6d !important; }
    .signal-none { background: linear-gradient(135deg,#212529,#343a40) !important; border: 2px solid #6c757d !important; }
    .info-card { background: #1e1e2e; border: 1px solid #333; border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 0.5rem; }
    .info-label { font-size: 0.78rem; color: #aaa; margin-bottom: 2px; }
    .info-value { font-size: 1.2rem; font-weight: 700; color: #f0f0f0; }
</style>
""",
    unsafe_allow_html=True,
)

st.set_page_config(layout="wide")

# ──────────────────────────────────────────────
# 核心函式
# ──────────────────────────────────────────────


@st.cache_data(ttl=300)
def fetch_stock_data(stock_id: str, start_date: str) -> pd.DataFrame:
    # 為了計算 MA50，我們需要比顯示範圍更早的資料 (多抓60天)
    buffer_start = (
        datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=90)
    ).strftime("%Y-%m-%d")

    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": buffer_start,
        "token": os.environ.get("FINMIND_API", ""),
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("data"):
        return pd.DataFrame()
    df = pd.DataFrame(data["data"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    rename_map = {
        "open": "Open",
        "max": "High",
        "min": "Low",
        "close": "Close",
        "Trading_Volume": "Volume",
    }
    df = df.rename(columns=rename_map)
    return df


def compute_signals(df: pd.DataFrame, display_start_date: str) -> pd.DataFrame:
    df = df.copy()

    # 計算均線
    df["MA5"] = df["Close"].rolling(window=5).mean()
    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["MA60"] = df["Close"].rolling(window=60).mean()

    signals = []

    for i in range(len(df)):
        if i < 60:  # 確保 MA60 已經算出來
            signals.append("無資料")
            continue

        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        c, o, ma5 = curr["Close"], curr["Open"], curr["MA5"]
        body_center = (o + c) / 2

        # 條件 1: 昨日收盤在線下 (最標準的突破前)
        # 條件 2: 昨日是黑K且昨日黑 K 實體大於過去 5 天平均實體的 1.2 倍
        prev_body = abs(prev["Open"] - prev["Close"])
        avg_body = df["Close"].diff().abs().rolling(5).mean().iloc[i-1]
        yesterday_was_weak = (prev["Close"] <= prev["MA5"]) and (prev["Close"] < prev["Open"])

        is_kahanshin = (c > o) and (body_center > ma5) and yesterday_was_weak

        yesterday_was_strong = (prev["Close"] >= prev["MA5"]) and (prev["Close"] > prev["Open"])
        is_inverse = yesterday_was_strong and c < o and (body_center < ma5)

        if is_kahanshin:
            signals.append("下半身")
        elif is_inverse:
            signals.append("逆下半身")
        else:
            signals.append("無訊號")

    df["Signal"] = signals

    # 只回傳使用者要求的日期範圍
    df = df[df["date"] >= pd.to_datetime(display_start_date)].reset_index(drop=True)
    return df


def build_candlestick_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    # K線圖
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="K線",
            increasing_line_color="#ff4d6d",
            decreasing_line_color="#52b788",
        )
    )

    # 均線群
    colors = {"MA5": "#f4d03f", "MA20": "#3498db", "MA60": "#9b59b6"}
    for ma in ["MA5", "MA20", "MA60"]:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df[ma],
                mode="lines",
                name=ma,
                line=dict(color=colors[ma], width=1.5),
            )
        )

    # 標註訊號
    buy_df = df[df["Signal"] == "下半身"]
    fig.add_trace(
        go.Scatter(
            x=buy_df["date"],
            y=buy_df["Low"] * 0.98,
            mode="markers+text",
            name="下半身(買)",
            text=["買"] * len(buy_df),
            textposition="bottom center",
            marker=dict(symbol="triangle-up", size=15, color="#ff4d6d"),
        )
    )

    sell_df = df[df["Signal"] == "逆下半身"]
    fig.add_trace(
        go.Scatter(
            x=sell_df["date"],
            y=sell_df["High"] * 1.02,
            mode="markers+text",
            name="逆下半身(賣)",
            text=["賣"] * len(sell_df),
            textposition="top center",
            marker=dict(symbol="triangle-down", size=15, color="#52b788"),
        )
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d0d1a",
        plot_bgcolor="#0d0d1a",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.05, font=dict(color="#f0f0f0")),
    )
    return fig


# ──────────────────────────────────────────────
# 主要輸入區
# ──────────────────────────────────────────────

with st.container():
    search_col1, search_col2, search_col3 = st.columns([1, 1, 1])
    with search_col1:
        stock_id = st.text_input("股票代碼", value="")
    with search_col2:
        options_map = {
            "30天 (約1個月)": 30,
            "60天 (約2個月)": 60,
            "90天 (約1季)": 90,
            "180天 (半年)": 180,
        }

        selected_label = st.selectbox(
            "顯示範圍", options=list(options_map.keys()), index=0
        )
        days_back = options_map[selected_label]
    with search_col3:
        st.write("##")
        analyze_btn = st.button("開始分析", use_container_width=True, type="primary")

# ──────────────────────────────────────────────
# 執行分析
# ──────────────────────────────────────────────
if analyze_btn:
    display_start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with st.spinner(f"正在分析 {stock_id}..."):
        try:
            df_raw = fetch_stock_data(stock_id.strip(), display_start)

            if df_raw.empty:
                st.error(f"⚠️ 找不到「{stock_id}」的資料。")
            else:
                df = compute_signals(df_raw, display_start)
                if df.empty:
                    st.warning("計算範圍內資料不足。")
                else:
                    latest = df.iloc[-1]

                    # 頂部狀態顯示
                    sig = latest["Signal"]
                    if sig == "下半身":
                        box_cls, title, desc = (
                            "signal-buy",
                            "🔴 觸發「下半身」買入訊號",
                            "今日首度突破 5MA 且均線呈多頭排列。",
                        )
                    elif sig == "逆下半身":
                        box_cls, title, desc = (
                            "signal-sell",
                            "🟢 觸發「逆下半身」賣出訊號",
                            "今日首度跌破 5MA 且均線呈空頭排列。",
                        )
                    else:
                        box_cls, title, desc = (
                            "signal-none",
                            "⚪ 目前無首日突破訊號",
                            "股價處於趨勢中或整理區間。",
                        )

                    st.markdown(
                        f'<div class="signal-box {box_cls}"><div class="signal-title">{title}</div><div class="signal-desc">{desc}</div></div>',
                        unsafe_allow_html=True,
                    )

                    # 數據卡片
                    c1, c2, c3, c4 = st.columns(4)

                    def card(col, label, value, color="#f0f0f0"):
                        col.markdown(
                            f'<div class="info-card"><div class="info-label">{label}</div><div class="info-value" style="color:{color}">{value}</div></div>',
                            unsafe_allow_html=True,
                        )

                    card(c1, "最新收盤", f"${latest['Close']:.2f}")
                    card(
                        c2,
                        "MA5/20/60",
                        f"{latest['MA5']:.1f} / {latest['MA20']:.1f} / {latest['MA60']:.1f}",
                    )

                    # 排列檢查
                    is_bull = latest["MA5"] > latest["MA20"] > latest["MA60"]
                    is_bear = latest["MA60"] > latest["MA20"] > latest["MA5"]
                    trend_text = (
                        "多頭排列"
                        if is_bull
                        else ("空頭排列" if is_bear else "糾結/無趨勢")
                    )
                    trend_color = (
                        "#ff4d6d" if is_bull else ("#52b788" if is_bear else "#aaa")
                    )

                    card(c3, "目前趨勢", trend_text, trend_color)
                    card(
                        c4,
                        "分析區間訊號數",
                        f"買:{ (df['Signal']=='下半身').sum() } / 賣:{ (df['Signal']=='逆下半身').sum() }",
                    )

                    # 圖表
                    st.plotly_chart(
                        build_candlestick_chart(df), use_container_width=True
                    )

        except Exception as e:
            st.error(f"執行時發生錯誤: {e}")
