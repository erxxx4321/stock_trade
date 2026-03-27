import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# 頁面設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="下半身・逆下半身 分析器",
    layout="wide",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }

    .main-title {
        font-size: 2.2rem; font-weight: 900;
        background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
        color: #e94560; padding: 1.2rem 1.8rem; border-radius: 12px;
        margin-bottom: 0.5rem; letter-spacing: 2px; text-align: center;
    }
    .subtitle { color: #888; font-size: 0.95rem; margin-bottom: 1.5rem; text-align: center; }

    .signal-box {
        border-radius: 12px !important; padding: 1.5rem 2rem !important;
        text-align: center !important; margin: 0.5rem 0 !important;
        color: #ffffff !important;
    }
    .signal-buy  {
        background: linear-gradient(135deg,#1b4332,#2d6a4f) !important;
        border: 2px solid #52b788 !important;
    }
    .signal-sell {
        background: linear-gradient(135deg,#641220,#a4133c) !important;
        border: 2px solid #ff4d6d !important;
    }
    .signal-none {
        background: linear-gradient(135deg,#212529,#343a40) !important;
        border: 2px solid #6c757d !important;
    }
    .signal-box .signal-title {
        font-size: 1.3rem !important; font-weight: 700 !important;
        margin-bottom: 0.3rem !important; color: #ffffff !important;
    }
    .signal-box .signal-desc {
        font-size: 0.9rem !important; color: rgba(255,255,255,0.85) !important;
    }

    .info-card {
        background: #1e1e2e; border: 1px solid #333;
        border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 0.5rem;
    }
    .info-label { font-size: 0.78rem; color: #aaa; margin-bottom: 2px; }
    .info-value { font-size: 1.2rem; font-weight: 700; color: #f0f0f0; }

    .theory-box {
        background: #12121f; border-left: 4px solid #e94560;
        padding: 0.8rem 1.2rem; border-radius: 0 8px 8px 0;
        margin-bottom: 0.8rem; font-size: 0.88rem; color: #ccc;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# 核心函式
# ──────────────────────────────────────────────


@st.cache_data(ttl=300)
def fetch_stock_data(stock_id: str, start_date: str) -> pd.DataFrame:
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
        "token": os.environ["FINMIND_API"],
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


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if len(df) < 5:
        df["MA5"] = None
        df["MA5_slope"] = None
        df["Signal"] = "無資料"
        df["Is_New"] = False
        return df

    df["MA5"] = df["Close"].rolling(window=5).mean()
    df["MA5_slope"] = df["MA5"].diff()

    signals = []
    is_new_list = []

    for i in range(len(df)):
        row = df.iloc[i]
        if i < 5 or pd.isna(row["MA5"]):
            signals.append("無資料")
            is_new_list.append(False)
            continue

        prev_row = df.iloc[i - 1]
        o, c, ma5 = row["Open"], row["Close"], row["MA5"]
        slope = row["MA5_slope"]
        body_top, body_bottom = max(o, c), min(o, c)
        body_len = abs(o - c)

        if body_len > 0:
            above_ratio = (body_top - ma5) / body_len
            below_ratio = (ma5 - body_bottom) / body_len
        else:
            above_ratio = 1 if c > ma5 else 0
            below_ratio = 1 if c < ma5 else 0

        is_kahanshin = (
            (c >= o) and (slope >= -0.05) and (above_ratio >= 0.5 or body_bottom > ma5)
        )
        is_inverse = (
            (c < o) and (slope <= 0.05) and (below_ratio >= 0.5 or body_top < ma5)
        )

        is_new = False
        if is_kahanshin:
            signals.append("下半身")
            is_new = prev_row["Close"] <= prev_row["MA5"]
        elif is_inverse:
            signals.append("逆下半身")
            is_new = prev_row["Close"] >= prev_row["MA5"]
        else:
            signals.append("無訊號")
        is_new_list.append(is_new)

    df["Signal"] = signals
    df["Is_New"] = is_new_list
    return df


def build_candlestick_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="K線",
            increasing_line_color="#52b788",
            decreasing_line_color="#ff4d6d",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["MA5"],
            mode="lines",
            name="5日均線",
            line=dict(color="#f4d03f", width=1.5),
        )
    )
    buy_df = df[df["Signal"] == "下半身"]
    fig.add_trace(
        go.Scatter(
            x=buy_df["date"],
            y=buy_df["Low"] * 0.995,
            mode="markers",
            name="下半身(買)",
            marker=dict(symbol="triangle-up", size=12, color="#52b788"),
        )
    )
    sell_df = df[df["Signal"] == "逆下半身"]
    fig.add_trace(
        go.Scatter(
            x=sell_df["date"],
            y=sell_df["High"] * 1.005,
            mode="markers",
            name="逆下半身(賣)",
            marker=dict(symbol="triangle-down", size=12, color="#ff4d6d"),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d0d1a",
        plot_bgcolor="#0d0d1a",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.08),
        font=dict(family="Noto Sans TC"),
    )
    return fig


# 理論說明
with st.expander("📖 理論說明（點擊展開）"):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="theory-box"><b>🟢 下半身（買入）</b><br>5日均線走平或向上時，紅K實體過半穿越5MA。</div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            '<div class="theory-box"><b>🔴 逆下半身（賣出）</b><br>5日均線走平或向下時，黑K實體過半跌破5MA。</div>',
            unsafe_allow_html=True,
        )

# ──────────────────────────────────────────────
# 主要輸入區
# ──────────────────────────────────────────────
with st.container():
    search_col1, search_col2, search_col3 = st.columns([2, 2, 1])

    with search_col1:
        stock_id = st.text_input("📌 股票代碼", value="", placeholder="")

    with search_col2:
        days_back = st.select_slider("分析範圍（天）", options=[30, 60, 90], value=30)

    with search_col3:
        st.write("##")  # 垂直對齊用
        analyze_btn = st.button("🔍 開始分析", use_container_width=True, type="primary")

# ──────────────────────────────────────────────
# 執行分析
# ──────────────────────────────────────────────
if analyze_btn:
    if not stock_id.strip():
        st.warning("請輸入股票代碼！")
    else:
        start_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        with st.spinner(f"📡 正在取得 {stock_id} 數據..."):
            try:
                df_raw = fetch_stock_data(stock_id.strip(), start_date)

                if df_raw.empty:
                    st.error(f"⚠️ 找不到「{stock_id}」的資料，請確認代碼是否正確。")
                else:
                    df = compute_signals(df_raw)
                    latest = df.iloc[-1]

                    # 顯示最新訊號
                    st.markdown(
                        f"### 📌 {stock_id} 最新訊號 ({latest['date'].strftime('%Y-%m-%d')})"
                    )

                    sig = latest["Signal"]
                    is_new = latest["Is_New"]

                    if sig == "下半身":
                        box_cls, emoji, title = (
                            "signal-buy",
                            "🟢",
                            "【新突破】下半身！" if is_new else "下半身（多頭持續）",
                        )
                        desc = "陽線實體站上5日均線。"
                    elif sig == "逆下半身":
                        box_cls, emoji, title = (
                            "signal-sell",
                            "🔴",
                            "【警戒】逆下半身！" if is_new else "逆下半身（空頭持續）",
                        )
                        desc = "陰線實體跌破5日均線。"
                    else:
                        box_cls, emoji, title, desc = (
                            "signal-none",
                            "⚪",
                            "無特定訊號",
                            "目前處於整理區間或未符合規則。",
                        )

                    st.markdown(
                        f'<div class="signal-box {box_cls}"><div class="signal-title">{emoji} {title}</div><div class="signal-desc">{desc}</div></div>',
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
                    card(c2, "5日均線", f"${latest['MA5']:.2f}")
                    card(
                        c3,
                        "均線斜率",
                        f"{latest['MA5_slope']:.2f}",
                        "#52b788" if latest["MA5_slope"] > 0 else "#ff4d6d",
                    )
                    card(
                        c4,
                        "累計訊號數",
                        f"買:{ (df['Signal']=='下半身').sum() } / 賣:{ (df['Signal']=='逆下半身').sum() }",
                    )

                    # 圖表
                    st.plotly_chart(
                        build_candlestick_chart(df), use_container_width=True
                    )

                    # 歷史紀錄
                    with st.expander("🗂️ 查看近期訊號紀錄"):
                        hist = (
                            df[df["Signal"].isin(["下半身", "逆下半身"])]
                            .copy()
                            .tail(10)
                        )
                        if not hist.empty:
                            hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
                            st.dataframe(
                                hist[["date", "Close", "MA5", "Signal"]].sort_values(
                                    "date", ascending=False
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )
                        else:
                            st.write("近期無訊號。")

            except Exception as e:
                st.error(f"執行時發生錯誤: {e}")

else:
    st.info("請在上方輸入代碼並點擊「開始分析」以查看結果。")
