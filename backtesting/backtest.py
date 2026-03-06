import argparse
import warnings
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from backtesting import Backtest
from FinMind.data import DataLoader
import helper
import numpy as np

# === 隱藏警告與進度條 ===
warnings.filterwarnings("ignore")
os.environ["BACKTESTING_DISABLE_TQDM"] = "1"


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
            "params": {"n1": [5, 10, 20], "n2": [10, 20, 50, 60, 100, 120]},
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
    }

    if strategy_name not in strategy_config:
        raise ValueError(
            f"未知策略: {strategy_name}。可用策略: {list(strategy_config.keys())}"
        )

    config = strategy_config[strategy_name]
    bt = Backtest(df, config["class"], cash=100_000, commission=0.001425)

    if config["optimize"]:
        stats = bt.optimize(
            maximize="Equity Final [$]",
            **config["params"],
            constraint=lambda p: p.n1 < p.n2 if "n2" in p else True,
        )
    else:
        helper.BOLL_KD30.buy_strategy = helper.BuyStrategy.BOLL_KD30
        stats = bt.run()

    return stats


def check_current_signal(stats, strategy_name):
    """
    依據回測結果的最後狀態，判定今日訊號
    """
    strategy_instance = stats["_strategy"]
    df = strategy_instance.data.df
    last_date = df.index[-1].strftime("%Y-%m-%d")

    print(f"\n數據截點: {last_date}")
    print(f"使用參數: {strategy_instance._params}")

    # 這裡的邏輯需要對應你在 helper.py 裡的定義
    # 範例：假設你的策略有 self.k, self.d 或 self.ma1, self.ma2

    signal = "💡 觀望 (HOLD / WAIT)"

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
        else:
            print(f"📊 目前狀態：【 ⚪ 空手觀望 】")
            print(f"💡 建議：等待下一次買入訊號")  # 取得最後一根 K 線的價格與指標值

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
        "-m",
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
        "-s",
        "--strategy",
        type=str,
        default="all",
        help="指定策略（預設 all）：EMA_KD, EMA_VWAP_KD, SmaCross, SMA_KD, BOLL_KD30",
    )

    args = parser.parse_args()
    ticker = args.ticker
    years = args.years
    strategy = args.strategy

    # 設定日期範圍
    today = datetime.today()
    start_date = (today - relativedelta(years=years)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    # 下載資料
    df = get_data(args.market, args.ticker, start_date, end_date)

    # 執行策略
    if strategy == "all":
        strategies = ["EMA_KD", "EMA_VWAP_KD", "SmaCross", "SMA_KD", "BOLL_KD30"]
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
            check_current_signal(best_stats, best_strategy)
            print("=" * 60)
        else:
            print("所有策略執行失敗。")

    else:
        stats = run_strategy(df, strategy)
        print_result(stats, strategy)


if __name__ == "__main__":
    main()
