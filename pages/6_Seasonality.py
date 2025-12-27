import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from neuralprophet import NeuralProphet
from FinMind.data import DataLoader
import matplotlib.pyplot as plt
import utils

api = DataLoader()

ticker = st.text_input("輸入股票代碼", "")

if st.button("分析季節性"):
    with st.spinner("分析中..."):
        try:
            # 載入資料
            today = datetime.today()
            start_date = (today - relativedelta(years=3)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

            df = api.taiwan_stock_daily(
                stock_id=ticker, start_date=start_date, end_date=end_date
            )
            df = df[["date", "close"]]
            df.columns = ["ds", "y"]
            df["ds"] = pd.to_datetime(df["ds"])

            # 訓練模型
            m = NeuralProphet(
                n_changepoints=0,
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                n_lags=utils.best_pacf_lag(df["y"]),
            )
            m.fit(df, epochs=30, batch_size=32, early_stopping=True)
            forecast = m.predict(df, decompose=True)
            m.plot_components(forecast, components=["seasonality"])

            # 顯示結果
            st.success("分析完成！")

            # 只顯示季節性組件
            fig_seasonality = m.plot_components(forecast, components=["seasonality"])
            st.plotly_chart(fig_seasonality, use_container_width=True)

        except Exception as e:
            st.error(f"❌ 發生未預期的錯誤: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
