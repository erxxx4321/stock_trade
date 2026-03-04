import streamlit as st
import streamlit.components.v1 as components

# 1. 設置頁面為寬螢幕模式 (非常重要，否則一行三個會太擠)
st.set_page_config(layout="wide", page_title="Polymarket Dashboard")

# 2. 定義你的市場清單 (這裡可以替換成你想要的 market ID 或完整連結)
# 為了方便示範，我用你提供的同一個 ID 重複三次
market_ids = [
    "will-the-iranian-regime-fall-by-june-30",
    "us-x-iran-ceasefire-by-march-6",
    "us-seizes-an-iran-linked-oil-tanker-by-march-7",
    "fed-rate-cut-by-june-2026-meeting",
]

# 3. 建立 Columns (一行三個)
cols = st.columns(3)

# 4. 迴圈填入內容
for idx, m_id in enumerate(market_ids):
    # 使用 modulo 確保在正確的 column 渲染
    with cols[idx % 3]:
        # 這裡將 width 改為 100% 讓它自動填滿 column 寬度
        embed_code = f"""
        <div style="border: 1px solid #e6e9ef; border-radius: 10px; overflow: hidden; background: white;">
            <iframe
                src="https://embed.polymarket.com/market?market={m_id}&creator=0x1d27EDF2c2Bf930f4BcD0bF5c9AD787325b67054-1772503064609"
                width="100%"
                height="400"
                frameborder="0"
                allowtransparency="true">
            </iframe>
        </div>
        """
        # 渲染組件
        components.html(embed_code, height=410)
        st.caption(f"市場 ID: {m_id}")
