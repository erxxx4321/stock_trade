#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FactSet 新聞查詢系統 - Streamlit 應用程式
"""
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# 設定頁面配置
st.set_page_config(
    page_title="FactSet 新聞查詢系統",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自訂 CSS 樣式
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .stDataFrame {
        border: 2px solid #e0e0e0;
        border-radius: 0.5rem;
    }
    </style>
""", unsafe_allow_html=True)


class FactSetDB:
    """資料庫操作類別"""
    
    def __init__(self, db_name='mystock.db'):
        self.db_name = db_name
    
    def get_connection(self):
        """獲取資料庫連線"""
        return sqlite3.connect(self.db_name)
    
    def get_all_stock_codes(self):
        """獲取所有股票代碼"""
        conn = self.get_connection()
        query = "SELECT DISTINCT stock_code, stock_name FROM factset_news ORDER BY stock_code"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def get_all_news(self):
        """獲取所有新聞"""
        conn = self.get_connection()
        query = """
            SELECT stock_code, stock_name, eps, est_price, date, updated_at
            FROM factset_news
            ORDER BY date DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def get_news_by_stock_code(self, stock_code):
        """根據股票代碼查詢"""
        conn = self.get_connection()
        query = """
            SELECT stock_code, stock_name, eps, est_price, date, updated_at
            FROM factset_news
            WHERE stock_code = ?
        """
        df = pd.read_sql_query(query, conn, params=(stock_code,))
        conn.close()
        return df
  


def format_dataframe(df):
    """格式化 DataFrame 顯示"""
    if df.empty:
        return df
    
    # 複製 DataFrame 避免修改原始資料
    df_formatted = df.copy()
    
    # 格式化數字欄位
    if 'eps' in df_formatted.columns:
        df_formatted['eps'] = df_formatted['eps'].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
    
    if 'est_price' in df_formatted.columns:
        df_formatted['est_price'] = df_formatted['est_price'].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
    
    # 重新命名欄位為中文
    column_mapping = {
        'stock_code': '股票代碼',
        'stock_name': '股票名稱',
        'eps': 'EPS預估',
        'est_price': '目標價',
        'date': '新聞日期',
        'updated_at': '更新時間'
    }
    
    df_formatted = df_formatted.rename(columns=column_mapping)
    
    return df_formatted


def main():
    """主程式"""
    
    # 標題
    st.markdown('<div class="main-header">📊 FactSet news</div>', unsafe_allow_html=True)
    
    # 初始化資料庫
    db = FactSetDB('mystock.db')
    
    # 側邊欄
    with st.sidebar:
        st.header("🔍 查詢選項")
        
        # 查詢模式選擇
        query_mode = st.radio(
            "選擇查詢模式",
            ["查詢所有股票", "查詢指定股票"],
            index=0
        )
        
        st.divider()
        
        # 如果選擇指定股票查詢
        selected_stock_code = None
        if query_mode == "查詢指定股票":
            # 獲取所有股票代碼
            stock_list = db.get_all_stock_codes()
            
            if not stock_list.empty:
                # 創建選項列表（代碼 + 名稱）
                stock_options = [f"{row['stock_code']} - {row['stock_name']}" 
                                for _, row in stock_list.iterrows()]
                
                selected_option = st.selectbox(
                    "選擇股票",
                    options=stock_options,
                    index=0
                )
                
                # 提取股票代碼
                selected_stock_code = selected_option.split(" - ")[0]
                
                # 也提供直接輸入的選項
                st.divider()
                manual_input = st.text_input("或直接輸入股票代碼", "")
                if manual_input:
                    selected_stock_code = manual_input.strip()
            else:
                st.warning("⚠️ 資料庫中沒有資料")
        
        st.divider()
        
        # 刷新按鈕
        if st.button("🔄 重新整理", use_container_width=True):
            st.rerun()
        
        st.divider()
        
        # 顯示資料庫資訊
        st.caption(f"📁 資料庫: mystock.db")
        st.caption(f"🕐 查詢時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  
    # 查詢結果
    st.subheader("📋 查詢結果")
    
    if query_mode == "查詢所有股票":
        # 查詢所有股票
        df = db.get_all_news()
        
        if not df.empty:
            st.success(f"✅ 找到 {len(df)} 筆資料")
            
            # 格式化並顯示
            df_formatted = format_dataframe(df)
            
            # 使用 st.dataframe 提供互動式表格
            st.dataframe(
                df_formatted,
                use_container_width=True,
                hide_index=True,
                height=400
            )
            
            # 提供下載按鈕
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下載 CSV",
                data=csv,
                file_name=f"factset_news_all_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
            # 顯示詳細資訊
            with st.expander("📊 查看圖表分析"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("EPS 分布")
                    st.bar_chart(df.set_index('stock_name')['eps'])
                
                with col2:
                    st.subheader("目標價分布")
                    st.bar_chart(df.set_index('stock_name')['est_price'])
        else:
            st.warning("⚠️ 資料庫中沒有資料")
    
    else:
        # 查詢指定股票
        if selected_stock_code:
            df = db.get_news_by_stock_code(selected_stock_code)
            
            if not df.empty:
                st.success(f"✅ 找到股票代碼 {selected_stock_code} 的資料")
                
                # 顯示完整資料
                st.subheader("詳細資訊")
                df_formatted = format_dataframe(df)
                st.dataframe(
                    df_formatted,
                    use_container_width=True,
                    hide_index=True
                )
                
                # 提供下載按鈕
                # csv = df.to_csv(index=False, encoding='utf-8-sig')
                # st.download_button(
                #     label="📥 下載 CSV",
                #     data=csv,
                #     file_name=f"factset_news_{selected_stock_code}_{datetime.now().strftime('%Y%m%d')}.csv",
                #     mime="text/csv"
                # )
            else:
                st.error(f"❌ 找不到股票代碼 {selected_stock_code} 的資料")
        else:
            st.info("ℹ️ 請在左側選擇股票代碼")


if __name__ == "__main__":
    main()