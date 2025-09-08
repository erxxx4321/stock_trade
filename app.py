import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from FinMind.data import DataLoader
import utils
from enum import Enum
api = DataLoader()

class BuyStrategy(Enum):
    BOLL_KD30 = '布林下軌KD<30'
    BOLL_RSI30 = '布林下軌RSI<30'
    VOL_KD30 = '成交量KD<30'

class SellStrategy(Enum):
    BOLL = '布林上軌'
    FIVE_MA_VOL = '5MA成交量'

st.set_page_config(
    page_title="First Trade",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={}
)
# st.title('Taiwan Stock Data Viewer')
# st.markdown('---')

with st.form(key='form'):
    ticker = st.text_input('請輸入股票代號:', value='')
    buy_strategy = st.selectbox(
        '買點條件:',
        options=[strategy.value for strategy in BuyStrategy]
    )
    sell_strategy = st.selectbox(
        '賣點條件:',
        options=[strategy.value for strategy in SellStrategy]
    )
    show_high_close_signal = st.checkbox('高檔', True)
    show_high_vol_signal = st.checkbox('爆量', True)
    submitted = st.form_submit_button("執行")

if submitted:
    try:
        today = datetime.today()
        start_date = (today - relativedelta(months=36)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        st.write(f"正在取得 **{ticker}** 從 **{start_date}** 到 **{end_date}** 的資料")

        # 1. 取得每日股價資料
        df_stock = api.taiwan_stock_daily(
            stock_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        df_stock.rename(columns={'max': 'High', 'min': 'Low', 'close': 'Close', 'Trading_Volume': 'Volume'}, inplace=True)

        # 取得外資、投信買賣超資料
        df_investor = api.taiwan_stock_institutional_investors(
            stock_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        df_investor['value'] = df_investor['buy'] - df_investor['sell']
        df_investor = df_investor.pivot_table(index='date', columns='name', values='value')
        df_investor = df_investor.reset_index()

        # 取得PER、PBR、殖利率
        df_per = api.taiwan_stock_per_pbr(
            stock_id=ticker,
            start_date=start_date,
            end_date=end_date
        )

        # 2. 使用自訂函式計算 KDJ 和布林通道
        df_kdj = utils.calculate_kdj(df_stock.copy())
        df_bb = utils.calculate_bollinger_bands(df_stock.copy())
        df_rsi = utils.calculate_rsi(df_stock.copy())

        # 3. 將計算結果合併回股價資料
        df = pd.merge(df_stock, df_kdj[['k', 'd']], left_index=True, right_index=True, how='left')
        df = pd.merge(df, df_bb, left_index=True, right_index=True, how='left')
        df = pd.merge(df, df_rsi, left_index=True, right_index=True, how='left')
        df = pd.merge(df, df_investor[['date', 'Foreign_Investor', 'Investment_Trust']], on='date', how='left')
        df = pd.merge(df, df_per[['date', 'PER', 'PBR']], on='date', how='left')

        # 4. 定義買點和賣點的條件
        if buy_strategy == BuyStrategy.VOL_KD30.value:
            buy_condition = (df['Volume'] > df['Volume'].rolling(window=5).mean()) & (df['k'] < 30) & (df['d'] < 30)
        elif buy_strategy == BuyStrategy.BOLL_KD30.value:
            buy_condition =  (df['Close'] <= df['Lower']) & (df['k'] < 30) & (df['d'] < 30)
        elif buy_strategy == BuyStrategy.BOLL_RSI30.value:
            buy_condition =  (df['Close'] <= df['Lower']) & (df['rsi'] < 30)
        
        if sell_strategy == SellStrategy.BOLL.value:
            sell_condition = df['Close'] >= df['Upper']
        elif sell_strategy == SellStrategy.FIVE_MA_VOL.value:
            sell_condition = (df['Close'] <  df['Close'].rolling(window=5).mean()) & (df['Volume'] > df['Volume'].rolling(window=10).mean())
        
        # 新增訊號欄位
        df['Signal'] = np.select(
            [buy_condition, sell_condition],
            ['Buy', 'Sell'],
            default=''
        )

        # 高檔爆量判斷
        df['High_Close'] = df['Close'] == df['Close'].rolling(window=60, min_periods=1).max()
        df['High_Volume'] = df['Volume'] == df['Volume'].rolling(window=60, min_periods=1).max()
 
        # 5. 排序並顯示資料
        df = df.sort_index(ascending=False)
        df_display = df[['date', 'High', 'Low', 'Close', 'Signal', 'Volume', 'k', 'd', 'rsi', 'Upper', 'Lower', 'High_Close', 'High_Volume', 'Foreign_Investor', 'Investment_Trust', 'PER', 'PBR']]
        def style_rsi(val):
            if isinstance(val, (int, float)) and val < 30:
                return 'background-color: #d4edda'
            return ''
        def style_df(df):
            styles = pd.DataFrame('', index=df.index, columns=df.columns)
            styles.loc[df['Signal'] == 'Buy', 'Signal'] = 'color: #7CFC00'
            styles.loc[df['Signal'] == 'Sell', 'Signal'] = 'color: #FF0000'

            if show_high_close_signal:
                styles.loc[df['High_Close'], ['Close']] = 'background-color: #f8d7da'
            if show_high_vol_signal:
                styles.loc[df['High_Volume'], ['Volume']] = 'background-color: #f8d7da'
            return styles
        
        if not df_display.empty:
            styled_df = df_display.style.apply(style_df, axis=None)
            st.dataframe(styled_df, column_config={'High_Close':None, 'High_Volume': None, 'Foreign_Investor': None, 'Investment_Trust': None, 'PER': None, 'PBR': None})
            # styled_df = styled_df.map(style_rsi, subset=['rsi'])
            
            st.success("資料取得與計算成功！")
        else:
            st.warning("查無此股票代號的資料，請確認代號是否正確。")

    except Exception as e:
        st.error(f"發生錯誤: {e}")