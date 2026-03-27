import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from FinMind.data import DataLoader
api = DataLoader()


st.set_page_config(
    page_title="樂活五線譜",
    page_icon="📈",
    layout="wide"
)

# 側邊欄：參數設定
with st.sidebar:
    st.header("參數設定")
    
    # 股票代號輸入
    ticker = st.text_input("股票代號", value="").strip()
    
    # 日期範圍選擇
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365 * 2)  # 預設2年資料
    
    col1, col2 = st.columns(2)
    with col1:
        start_date_input = st.date_input("開始日期", value=start_date)
    with col2:
        end_date_input = st.date_input("結束日期", value=end_date)
    
    if st.button("開始分析"):
        analysis_triggered = True
    else:
        analysis_triggered = False

    # 計算參數
    st.subheader("計算參數")
    window = st.slider("移動平均週期(日)", min_value=10, max_value=100, value=20, step=5)
    std_multiplier = st.slider("標準差倍數", min_value=1.0, max_value=3.0, value=2.0, step=0.5)
    
    # 顏色設定
    st.subheader("圖表顏色設定")
    price_color = st.color_picker("價格線顏色", "#1f77b4")
    ma_color = st.color_picker("移動平均線顏色", "#ff7f0e")
    upper_color = st.color_picker("上軌線顏色", "#2ca02c")
    lower_color = st.color_picker("下軌線顏色", "#d62728")

# 主畫面
if 'analysis_triggered' in locals() and analysis_triggered:
    try:
        
        # 取得台股資料
        with st.spinner("取得股票資料中..."):
            df = api.taiwan_stock_daily(
              stock_id=ticker, start_date=start_date, end_date=end_date
          )
            df.set_index('date', inplace=True)
            
        # 計算五線譜指標
        with st.spinner("計算五線譜指標中..."):
            df['MA'] = df['close'].rolling(window=window).mean()
            df['Std'] = df['close'].rolling(window=window).std()
            
            # 計算各軌道線
            df['upper_2'] = df['MA'] + std_multiplier * df['Std']
            df['upper_1'] = df['MA'] + (std_multiplier/2) * df['Std']
            df['lower_1'] = df['MA'] - (std_multiplier/2) * df['Std']
            df['lower_2'] = df['MA'] - std_multiplier * df['Std']
            
            # 識別買賣訊號
            df['buy_signal'] = df['close'] <= df['lower_2']
            df['sell_signal'] = df['close'] >= df['upper_2']
            
            # 計算目前位置百分比
            last_close = df['close'].iloc[-1]
            last_upper_2 = df['upper_2'].iloc[-1]
            last_lower_2 = df['lower_2'].iloc[-1]
            
            if last_upper_2 != last_lower_2:
                position_pct = ((last_close - last_lower_2) / (last_upper_2 - last_lower_2)) * 100
                position_pct = max(0, min(100, position_pct))
            else:
                position_pct = 50
        
        # 顯示關鍵資訊
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("當前價格", f"{last_close:.2f}")
        with col2:
            st.metric(f"移動平均({window}日)", f"{df['MA'].iloc[-1]:.2f}")
        with col3:
            st.metric("通道位置", f"{position_pct:.1f}%")
        with col4:
            if last_close <= df['lower_2'].iloc[-1]:
                st.metric("訊號", "買進區", delta="偏低", delta_color="inverse")
            elif last_close >= df['upper_2'].iloc[-1]:
                st.metric("訊號", "賣出區", delta="偏高", delta_color="inverse")
            else:
                st.metric("訊號", "持有區", delta="正常")
        
        # 使用 Plotly 建立互動式圖表
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            vertical_spacing=0.05,
            shared_xaxes=True
        )
        
        # 股價與五線譜
        fig.add_trace(
            go.Scatter(x=df.index, y=df['close'], name='收盤價',
                      line=dict(color=price_color, width=2),
                      hovertemplate='日期: %{x}<br>價格: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(x=df.index, y=df['MA'], name=f'MA{window}',
                      line=dict(color=ma_color, width=1.5, dash='dash'),
                      hovertemplate='日期: %{x}<br>MA: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        # 通道區域（填充色）
        fig.add_trace(
            go.Scatter(x=df.index, y=df['upper_2'], name=f'+{std_multiplier}σ',
                      line=dict(color=upper_color, width=1, dash='dot'),
                      hovertemplate='日期: %{x}<br>上軌: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(x=df.index, y=df['upper_1'], name=f'+{std_multiplier/2}σ',
                      line=dict(color=upper_color, width=0.5, dash='dot'),
                      showlegend=False,
                      hovertemplate='日期: %{x}<br>上中軌: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(x=df.index, y=df['lower_1'], name=f'-{std_multiplier/2}σ',
                      line=dict(color=lower_color, width=0.5, dash='dot'),
                      showlegend=False,
                      hovertemplate='日期: %{x}<br>下中軌: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(x=df.index, y=df['lower_2'], name=f'-{std_multiplier}σ',
                      line=dict(color=lower_color, width=1, dash='dot'),
                      hovertemplate='日期: %{x}<br>下軌: %{y:.2f}<extra></extra>'),
            row=1, col=1
        )
        
        # 填充通道區域
        fig.add_trace(
            go.Scatter(x=df.index, y=df['upper_2'],
                      fill=None,
                      mode='lines',
                      line_color='rgba(255,255,255,0)',
                      showlegend=False),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(x=df.index, y=df['lower_2'],
                      fill='tonexty',
                      fillcolor='rgba(46, 134, 222, 0.1)',
                      mode='lines',
                      line_color='rgba(255,255,255,0)',
                      name='通道範圍',
                      hovertemplate='日期: %{x}<br>通道範圍<extra></extra>'),
            row=1, col=1
        )
        
        # 買賣訊號點
        buy_signals = df[df['buy_signal']]
        sell_signals = df[df['sell_signal']]
        
        if not buy_signals.empty:
            fig.add_trace(
                go.Scatter(x=buy_signals.index, y=buy_signals['close'],
                          mode='markers',
                          marker=dict(color='green', size=10, symbol='triangle-up'),
                          name='買進訊號',
                          hovertemplate='日期: %{x}<br>買進價: %{y:.2f}<extra></extra>'),
                row=1, col=1
            )
        
        if not sell_signals.empty:
            fig.add_trace(
                go.Scatter(x=sell_signals.index, y=sell_signals['close'],
                          mode='markers',
                          marker=dict(color='red', size=10, symbol='triangle-down'),
                          name='賣出訊號',
                          hovertemplate='日期: %{x}<br>賣出價: %{y:.2f}<extra></extra>'),
                row=1, col=1
            )
        
        fig.add_trace(
            go.Bar(x=df.index, y=df['Trading_Volume'], name='成交量',
                  marker_color='lightblue',
                  opacity=0.6,
                  hovertemplate='日期: %{x}<br>成交量: %{y:,}<extra></extra>'),
            row=2, col=1
        )
        
        # 更新佈局
        fig.update_layout(
            height=800,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            title=f"股票 {ticker} 樂活五線譜分析 (週期: {window}日, 標準差倍數: {std_multiplier})"
        )
        
        fig.update_xaxes(title_text="日期", row=2, col=1)
        fig.update_yaxes(title_text="價格", row=1, col=1)
        fig.update_yaxes(title_text="成交量", row=2, col=1)
        
        # 顯示圖表
        st.plotly_chart(fig, use_container_width=True)
        
        # 顯示數據表格
        with st.expander("查看詳細數據"):
            st.dataframe(df.tail(50).style.format({
                'close': '{:.2f}',
                'MA': '{:.2f}',
                'upper_2': '{:.2f}',
                'upper_1': '{:.2f}',
                'lower_1': '{:.2f}',
                'lower_2': '{:.2f}'
            }))
        
        # 顯示統計資訊
        st.subheader("統計分析")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**買進訊號統計**")
            if not buy_signals.empty:
                st.write(f"出現次數: {len(buy_signals)}")
                st.write(f"平均買進價: {buy_signals['close'].mean():.2f}")
            else:
                st.write("近期無買進訊號")
        
        with col2:
            st.write("**賣出訊號統計**")
            if not sell_signals.empty:
                st.write(f"出現次數: {len(sell_signals)}")
                st.write(f"平均賣出價: {sell_signals['close'].mean():.2f}")
            else:
                st.write("近期無賣出訊號")
        
        # 策略說明
        st.markdown("---")
        st.subheader("樂活五線譜策略說明")
        st.markdown("""
        ### 交易規則：
        1. **買進訊號**：當股價跌破 **-2σ 下軌線** 時，視為超跌買入機會
        2. **賣出訊號**：當股價突破 **+2σ 上軌線** 時，視為超漲賣出機會
        3. **持有區間**：股價在上下軌之間時，建議持有觀望
        
        ### 參數說明：
        - **移動平均週期**：計算平均值和標準差的時間窗口
        - **標準差倍數**：決定通道寬度，通常使用 2 倍標準差
        - **通道位置百分比**：顯示當前價格在通道中的相對位置（0% = 下軌，100% = 上軌）
        """)
        
    except Exception as e:
        st.error(f"分析過程中發生錯誤：{str(e)}")
        st.info("請確認：\n1. 股票代號是否正確\n2. 日期範圍是否合理\n3. 網路連線是否正常")

