import argparse
import sys
import warnings
import os
from itertools import product
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from backtesting import Backtest
from FinMind.data import DataLoader
import helper
import numpy as np
import gspread
from google.oauth2.service_account import Credentials

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1alMqZ1cRn8onmy16RfB0T4n_PMPpSG6RKvHaD_LDewA"
GOOGLE_CREDS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BACKTEST_SHEET = "Backtest"
BACKTEST_COLS = ["個股代號", "個股名稱", "策略名稱", "策略條件", "狀態"]

# python backtest.py 2344 --strategy LEFT_SIDE_MA

warnings.filterwarnings("ignore")
os.environ["BACKTESTING_DISABLE_TQDM"] = "1"


def _tuple(v):
    return v if isinstance(v, (list, tuple)) else (v,)


def print_result(stats, strategy_name=None):
    if strategy_name:
        print(f"\n{'='*50}")
        print(f"策略: {strategy_name}")
        print(f"{'='*50}")

    stats_display = stats.loc[
        [
            "Start",
            "End",
            "Equity Final [$]",  # 最終資產淨值
            "Equity Peak [$]",
            "Return [%]",  # 總報酬率
            "Buy & Hold Return [%]",  # 買入並持有報酬率（基準）
            "# Trades",
            "Win Rate [%]",  # 勝率
            "Avg. Trade [%]",  # 平均盈利率 EV表現形式
            "Sharpe Ratio",  # 夏普比率
            "Max. Drawdown [%]",  # 最大回撤
            "SQN",  # 系統品質數字
            "_trades",
            "_strategy",
        ]
    ]
    print("------------------回測表現-----------------")
    print(stats_display)
    print("------------------交易紀錄-----------------")
    trades = stats_display["_trades"]
    for _, trade in trades.iterrows():
        print(f"Buy date: {trade['EntryTime']}, Sell date: {trade['ExitTime']}")
        # 對數收益率計算
        trade["Log_Return"] = np.log(1 + trade["ReturnPct"])
        print(
            f"Buy price: {trade['EntryPrice']}, Sell price: {trade['ExitPrice']}, P/L: {trade['ReturnPct']:.2%}, rt: {trade['Log_Return']:.2%}, PnL: {trade['PnL']:.2f}"
        )


def run_strategy(df, strategy_name):
    strategy_config = {
        "EMA_KD": {
            "class": helper.EMA_KD,
            "optimize": True,
            "params": {"n1": [5, 10, 20], "n2": [20, 50, 60, 100, 120], "kd": 75},
        },
        "EMA_VWAP_KD": {
            "class": helper.EMA_VWAP_KD,
            "optimize": True,
            "params": {"n1": [5, 10, 20], "n2": [10, 20, 50, 60, 100, 120], "kd": 75},
        },
        "SmaCross": {
            "class": helper.SmaCross,
            "optimize": True,
            "params": {
                "n1": [5, 10, 20],
                "n2": [10, 20, 50, 60, 100, 120],
                "stop_loss": [0.05, 0.08, 0.1, 0.15, 0.2],
            },
        },
        "SMA_KD": {
            "class": helper.SMA_KD,
            "optimize": True,
            "params": {"n1": [5, 10, 20], "n2": [10, 20, 50, 60, 100, 120], "kd": 75},
        },
        "BOLL_KD30": {
            "class": helper.BOLL_KD30,
            "optimize": False,
            "params": {},
        },
        "BOX_RANGE": {
            "class": helper.BOX_RANGE,
            "optimize": False,
            "params": {},
        },
        "LEFT_SIDE_MA": {
            "class": helper.LEFT_SIDE_MA,
            "optimize": True,
            "params": {
                "ma_period": [5, 10, 20, 60, 100, 120],
                "take_profit": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 1],
                "stop_loss": [0.05, 0.08, 0.1, 0.15, 0.2],
            },
        },
        "NEURAL_SEASONALITY": {
            "class": helper.NEURAL_SEASONALITY,
            "optimize": True,
            "sequential": True,  # NeuralProphet 內部使用多執行緒，與 bt.optimize() 的 Pool 併用會卡死
            "params": {
                "take_profit": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 1],
            },
        },
    }

    if strategy_name not in strategy_config:
        raise ValueError(
            f"未知策略: {strategy_name}。可用策略: {list(strategy_config.keys())}"
        )

    config = strategy_config[strategy_name]
    bt = Backtest(
        df, config["class"], cash=100_000, commission=0.001425, trade_on_close=True
    )

    if config["optimize"] and config.get("sequential"):
        param_names = list(config["params"].keys())
        best_stats = None
        best_equity = -np.inf
        for values in product(*(_tuple(v) for v in config["params"].values())):
            params = dict(zip(param_names, values))
            candidate_stats = bt.run(**params)
            equity = candidate_stats["Equity Final [$]"]
            if equity > best_equity:
                best_equity = equity
                best_stats = candidate_stats
        stats = best_stats
    elif config["optimize"]:
        stats = bt.optimize(
            maximize="Equity Final [$]",
            **config["params"],
            constraint=lambda p: p.n1 < p.n2 if "n2" in p else True,
        )
    else:
        helper.BOLL_KD30.buy_strategy = helper.BuyStrategy.BOLL_KD30
        stats = bt.run()

    return stats


def get_stock_name(ticker: str) -> str:
    try:
        api = DataLoader()
        info = api.taiwan_stock_info()
        row = info[info["stock_id"] == ticker]
        if not row.empty:
            return str(row.iloc[0]["stock_name"])
    except Exception as e:
        print(f"⚠️ 查詢個股名稱失敗: {e}")
    return ""


def get_backtest_worksheet():
    if not os.path.exists(GOOGLE_CREDS_PATH):
        raise FileNotFoundError(f"找不到 Google 服務帳戶金鑰：{GOOGLE_CREDS_PATH}")

    creds = Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH, scopes=GOOGLE_SCOPES
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)

    try:
        ws = spreadsheet.worksheet(BACKTEST_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=BACKTEST_SHEET, rows=1000, cols=10)
        ws.update(range_name="A1", values=[BACKTEST_COLS])
        ws.format(
            "A1:E1",
            {
                "backgroundColor": {"red": 0.13, "green": 0.24, "blue": 0.45},
                "textFormat": {
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    "bold": True,
                },
                "verticalAlignment": "MIDDLE",
            },
        )
        ws.freeze(rows=1)
        ws.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": ws.id,
                                "dimension": "COLUMNS",
                                "startIndex": 4,
                                "endIndex": 5,
                            },
                            "properties": {"pixelSize": 260},
                            "fields": "pixelSize",
                        }
                    }
                ]
            }
        )

    return ws


def sync_backtest_position(
    ticker: str, name: str, strategy_name: str, params: dict, status: str
):
    param_str = ",".join(f"{k}={v}" for k, v in params.items())
    try:
        ws = get_backtest_worksheet()
        codes = ws.col_values(1)
        row = [
            ticker,
            name or ticker,
            strategy_name,
            param_str,
            status,
        ]

        if ticker in codes[1:]:
            row_idx = codes.index(ticker) + 1
            ws.update(range_name=f"A{row_idx}:E{row_idx}", values=[row])
            print(f"🔄 已更新 Google Sheet 分頁既有列: {ticker}")
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
            print(f"📤 已新增至 Google Sheet 分頁: {ticker}")
    except Exception as e:
        print(f"⚠️ 同步分頁失敗: {e}")


def check_current_signal(stats, strategy_name, ticker=None, to_sheet=False):
    """
    依據回測結果的最後狀態，判定今日訊號
    """
    strategy_instance = stats["_strategy"]
    df = strategy_instance.data.df
    last_date = df.index[-1].strftime("%Y-%m-%d")

    print(f"\n數據截點: {last_date}")
    print(f"使用參數: {strategy_instance._params}")

    # 邏輯判斷示範 (請根據你 helper.py 實際指標名稱修改)
    try:
        # 檢查是否有未平倉部位
        active_trades = strategy_instance.trades

        if active_trades:
            # 取得最後一筆開倉的交易 (通常只有一筆，除非你的策略支援分批進場)
            current_trade = active_trades[0]
            entry_date = current_trade.entry_time.strftime("%Y-%m-%d")
            entry_price = current_trade.entry_price
            current_price = df["Close"][-1]
            pnl_pct = (current_price - entry_price) / entry_price

            print(f"📊 目前狀態：【 🟢 持股中 】")
            print(f"📅 買入日期：{entry_date}")
            print(f"💰 買入價格：{entry_price:.2f}")
            print(f"📈 目前現價：{current_price:.2f} (浮報: {pnl_pct:.2%})")

            # 這裡可以加入賣出邏輯判定
            # if 滿足賣出條件: print("🔔 建議：今日觸發賣出訊號")

            if ticker and to_sheet:
                name = get_stock_name(ticker)
                sync_backtest_position(
                    ticker,
                    name,
                    strategy_name,
                    dict(strategy_instance._params),
                    "持有中",
                )
        else:
            print(f"📊 目前狀態：【 ⚪ 空手觀望 】")
            print(f"💡 建議：等待下一次買入訊號")  # 取得最後一根 K 線的價格與指標值

            if ticker and to_sheet:
                name = get_stock_name(ticker)
                sync_backtest_position(
                    ticker,
                    name,
                    strategy_name,
                    dict(strategy_instance._params),
                    "空手中",
                )

    except Exception as e:
        print(f"判定訊號時發生錯誤: {e}")
        print("建議：請檢查 helper.py 中指標的變數名稱是否與此對接。")


def get_data(market, ticker, start_date, end_date):
    """
    根據市場別，統一使用 FinMind 下載資料
    """
    api = DataLoader()

    if market == "tw":
        df = api.taiwan_stock_daily(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )
        df = df.rename(
            columns={
                "max": "High",
                "min": "Low",
                "open": "Open",
                "close": "Close",
                "Trading_Volume": "Volume",
            }
        )
    else:  # us 市場
        df = api.us_stock_price(
            stock_id=ticker, start_date=start_date, end_date=end_date
        )

    if df.empty:
        print(f"錯誤：無法取得股票 {ticker} 在 {start_date} ~ {end_date} 的資料。")
        return

    # 清理無效價格（避免除零）
    df = df[(df["Close"] > 0) & (df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0)]
    if df.empty:
        print("錯誤：過濾後無有效價格資料。")
        return

    df.set_index("date", inplace=True)
    df.index = pd.to_datetime(df.index)

    return df


def main():
    parser = argparse.ArgumentParser(description="股票策略回測 CLI 工具")
    parser.add_argument("ticker", type=str, help="股票代號，例如：2317")
    parser.add_argument(
        "--market",
        type=str,
        choices=["tw", "us"],
        default="tw",
        help="市場：tw (台股, 預設), us (美股)",
    )
    parser.add_argument(
        "-y", "--years", type=int, default=5, help="回測年數（預設 2 年）"
    )
    parser.add_argument(
        "-m", "--months", type=int, default=0, help="回測月數（預設 0 月）"
    )
    parser.add_argument(
        "-s",
        "--strategy",
        type=str,
        nargs="?",
        const="__list__",
        default="all",
        help="指定策略（預設 all）：EMA_KD, EMA_VWAP_KD, SmaCross, SMA_KD, BOLL_KD30, BOX_RANGE, LEFT_SIDE_MA, NEURAL_SEASONALITY。不帶值則列出所有可用策略",
    )
    parser.add_argument(
        "--to-sheet",
        action="store_true",
        help="若目前有未平倉部位，將結果輸出至 Google Sheet（預設不輸出）",
    )

    args = parser.parse_args()
    ticker = args.ticker
    years = args.years
    months = args.months
    strategy = args.strategy
    to_sheet = args.to_sheet

    if strategy == "__list__":
        print("可用策略：")
        for s in [
            "EMA_KD",
            "EMA_VWAP_KD",
            "SmaCross",
            "SMA_KD",
            "BOLL_KD30",
            "BOX_RANGE",
            "LEFT_SIDE_MA",
            "NEURAL_SEASONALITY",
        ]:
            print(f"  - {s}")
        return

    # 設定日期範圍
    today = datetime.today()
    start_date = (today - relativedelta(years=years, months=months)).strftime(
        "%Y-%m-%d"
    )
    end_date = today.strftime("%Y-%m-%d")

    # 下載資料
    df = get_data(args.market, args.ticker, start_date, end_date)

    # 執行策略
    if strategy == "all":
        strategies = [
            "EMA_KD",
            "EMA_VWAP_KD",
            "SmaCross",
            "SMA_KD",
            "BOLL_KD30",
            "BOX_RANGE",
            "LEFT_SIDE_MA",
        ]
        results = {}

        for s in strategies:
            try:
                stats = run_strategy(df, s)
                equity_final = stats["Equity Final [$]"]
                results[s] = {"equity": equity_final, "stats": stats}
                print_result(stats, s)
            except Exception as e:
                print(f"\n{'='*50}\n策略 {s} 執行失敗: {e}\n{'='*50}")
                continue

        if results:
            best_strategy = max(results, key=lambda k: results[k]["equity"])
            best_stats = results[best_strategy]["stats"]
            print("\n" + "=" * 60)
            print(f"🏆 最佳策略評估結果 {ticker}")
            print("=" * 60)
            print(f"最佳策略: {best_strategy}")
            print(f"最終資產淨值: ${results[best_strategy]['equity']:,.2f}")
            # --- 新增：判定今日訊號 ---
            check_current_signal(best_stats, best_strategy, ticker, to_sheet)
            print("=" * 60)
        else:
            print("所有策略執行失敗。")

    else:
        stats = run_strategy(df, strategy)
        print_result(stats, strategy)
        check_current_signal(stats, strategy, ticker, to_sheet)


if __name__ == "__main__":
    main()
