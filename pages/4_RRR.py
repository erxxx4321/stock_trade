import streamlit as st


def calculate_rrr(entry_price, stop_loss_price, target_price):
    """
    計算風險回報比 (Risk-Reward Ratio)

    公式:
    潛在虧損 (風險) = abs(買入價 - 止損價)
    潛在盈利 (利潤) = abs(目標價 - 買入價)
    風險回報比 (RRR) = 潛在虧損 / 潛在盈利
    回報風險比 (R:R) = 潛在盈利 / 潛在虧損

    Args:
        entry_price (float): 買入價
        stop_loss_price (float): 止損價
        target_price (float): 目標價

    Returns:
        tuple: (風險回報比 RRR, 潛在虧損, 潛在盈利)
    """

    # 判斷交易方向 (多頭或空頭)
    # 假設是「買入價 > 止損價」且「目標價 > 買入價」為**多頭 (做多)**
    # 假設是「買入價 < 止損價」且「目標價 < 買入價」為**空頭 (做空)**

    # 潛在虧損 (風險)
    potential_loss = abs(entry_price - stop_loss_price)

    # 潛在盈利 (利潤)
    potential_profit = abs(target_price - entry_price)

    # 檢查是否為零，避免除以零錯誤
    if potential_profit == 0 or potential_loss == 0:
        return 0.0, potential_loss, potential_profit

    # 風險回報比 (Risk-Reward Ratio) = 潛在虧損 ÷ 潛在盈利
    risk_reward_ratio = potential_loss / potential_profit

    return risk_reward_ratio, potential_loss, potential_profit


# --- Streamlit 介面設定 ---
st.set_page_config(page_title="風險回報比計算器", layout="centered")

st.title("💰 風險回報比 (RRR) 計算器")
st.markdown("輸入您的交易參數，計算這筆交易的**風險**和**潛在利潤**之間的比例。")

st.info(
    "💡 **提示：** 程式會自動判斷做多或做空。您只需要輸入價格，確保**目標價**是您預期的平倉獲利點，而**止損價**是您設定的止損點即可。"
)

# --- 輸入欄位 ---
col1, col2, col3 = st.columns(3)

with col1:
    entry_price = st.number_input(
        "**買入價 (Entry Price)**",
        min_value=0.01,
        value=10.00,
        step=0.01,
        format="%.2f",
        help="您進場時的價格。",
    )

with col2:
    stop_loss_price = st.number_input(
        "**止損價 (Stop Loss)**",
        min_value=0.01,
        value=9.50,
        step=0.01,
        format="%.2f",
        help="您願意承受的最大虧損價格。",
    )

with col3:
    target_price = st.number_input(
        "**目標價 (Target Price)**",
        min_value=0.01,
        value=11.50,
        step=0.01,
        format="%.2f",
        help="您預期獲利出場的價格。",
    )

# --- 執行計算 ---
if st.button("🚀 計算風險回報比"):
    if (entry_price == stop_loss_price) or (entry_price == target_price):
        st.error("🚨 錯誤：買入價不能等於止損價或目標價。請重新輸入。")
    else:
        rrr, loss, profit = calculate_rrr(entry_price, stop_loss_price, target_price)

        # 判斷交易方向
        if entry_price > stop_loss_price:
            trade_type = "多頭 (做多) 📈"
            # 檢查是否為合理的多頭設定
            if target_price < entry_price:
                st.warning(
                    f"⚠️ 您的交易設定看起來像**做多**，但**目標價**低於**買入價**。請檢查價格是否輸入正確。"
                )
        else:
            trade_type = "空頭 (做空) 📉"
            # 檢查是否為合理的空頭設定
            if target_price > entry_price:
                st.warning(
                    f"⚠️ 您的交易設定看起來像**做空**，但**目標價**高於**買入價**。請檢查價格是否輸入正確。"
                )

        st.subheader("📊 計算結果")

        # 使用表格展示核心數據
        results_df = {
            "項目": [
                "交易類型",
                "潛在虧損 (風險)",
                "潛在盈利 (利潤)",
                "風險回報比 (RRR)",
                "回報風險比 (R:R)",
            ],
            "數值": [
                trade_type,
                f"${loss:.2f}",
                f"${profit:.2f}",
                f"{rrr:.2f}",
                f"1 : {1/rrr:.2f}" if rrr != 0 else "N/A",
            ],
        }
        st.table(results_df)

        st.markdown("---")

        # --- 判斷與建議 ---
        st.subheader("⭐ 風險判斷與建議")

        # 您提供的判斷邏輯
        if rrr > 1:
            st.error(f"**風險回報比 (RRR) 為 {rrr:.2f} > 1**")
            st.markdown(
                f"**結論：風險 ({loss:.2f}) 大於潛在利潤 ({profit:.2f})。** 這是一筆**不值得**考慮的交易。"
            )
        elif rrr == 1:
            st.warning(f"**風險回報比 (RRR) 為 {rrr:.2f} = 1**")
            st.markdown(
                f"**結論：風險和利潤對等。** 考慮到交易手續費和失敗機率，長期來看通常**不建議**。"
            )
        elif 0 < rrr < 1:
            r_r_ratio = 1 / rrr
            st.success(
                f"**風險回報比 (RRR) 為 {rrr:.2f} < 1** (即 回報風險比為 **1 : {r_r_ratio:.2f}**)"
            )
            if r_r_ratio >= 2.0:
                st.balloons()  # 達到優良比例時放氣球慶祝
                st.markdown(
                    f"**結論：利潤 ({profit:.2f}) 大於風險 ({loss:.2f})。** 您的回報風險比達到 **1 : {r_r_ratio:.2f}**，**這是一筆值得考慮的優良交易！** (建議通常為 1:2 或 1:3 以上)"
                )
            else:
                st.markdown(
                    f"**結論：利潤 ({profit:.2f}) 大於風險 ({loss:.2f})。** 這是一筆值得考慮的交易，但您可以試著將比例調整到 **1:2** (RRR = 0.5) 以上。"
                )
        else:
            st.markdown("**請檢查輸入價格，確保目標價和止損價皆不同於買入價。**")

# --- 顯示公式說明 ---
st.markdown("---")
st.markdown("### 📘 公式說明")
st.latex(
    r"""
\text{潛在虧損 (風險)} = |\text{買入價} - \text{止損價}|
"""
)
st.latex(
    r"""
\text{潛在盈利 (利潤)} = |\text{目標價} - \text{買入價}|
"""
)
st.latex(
    r"""
\text{風險回報比 (RRR)} = \frac{\text{潛在虧損}}{\text{潛在盈利}}
"""
)
st.markdown("> **風險回報比 < 1 (即 回報風險比 $\ge 1:1$)** 才是值得考慮的交易。")
