"""
每日訊號掃描腳本。

讀取 Google Sheet「Backtest」分頁中既有的個股／策略／參數組合，
以既定(非優化)參數重新回測到今天，判斷最新交易日是否觸發進場、
出場、停損或停利，並將最近一次觸發的訊息寫回「通知」欄位。

用法:
    python scan_signals.py
    python scan_signals.py --years 3

建議透過 Windows工作排程器，於每個交易日收盤後執行。
"""

import sys
import time
import warnings
from datetime import datetime
import argparse

from dateutil.relativedelta import relativedelta

import backtest as bt_mod

sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")


def scan(years: int = 2, sleep_sec: float = 1.0):
    ws = bt_mod.get_backtest_worksheet()
    records = ws.get_all_values()
    if len(records) <= 1:
        print("Backtest 分頁目前沒有任何項目。")
        return

    header, rows = records[0], records[1:]
    today = datetime.today()
    start_date = (today - relativedelta(years=years)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    for i, row in enumerate(rows, start=2):
        row = row + [""] * (len(bt_mod.BACKTEST_COLS) - len(row))
        ticker, name, strategy_name, param_str, _old_notification = row[:5]

        ticker = ticker.strip()
        strategy_name = strategy_name.strip()
        if not ticker or not strategy_name:
            continue

        print(f"\n{'='*50}\n掃描 {ticker} ({name}) - {strategy_name}\n{'='*50}")
        try:
            params = bt_mod.parse_params(param_str)
            df = bt_mod.get_data("tw", ticker, start_date, end_date)
            if df is None or df.empty:
                print(f"⚠️ 無法取得 {ticker} 資料，略過。")
                continue

            stats = bt_mod.run_with_params(df, strategy_name, params)
            notification = bt_mod.determine_notification(stats)

            ws.update(
                range_name=f"E{i}",
                values=[[notification]],
            )
            print(f"🔔 通知: {notification}")
        except Exception as e:
            print(f"⚠️ {ticker} 掃描失敗: {e}")
        finally:
            time.sleep(sleep_sec)  # 避免觸發 Google Sheets API 速率限制


def main():
    parser = argparse.ArgumentParser(description="每日訊號掃描 (讀取 Backtest 分頁)")
    parser.add_argument(
        "-y", "--years", type=int, default=2, help="下載歷史資料年數（預設 2 年）"
    )
    args = parser.parse_args()
    scan(years=args.years)


if __name__ == "__main__":
    main()
