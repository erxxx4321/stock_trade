import argparse
import sys
import warnings
import os
import importlib.util
from itertools import product
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from backtesting import Backtest
from FinMind.data import DataLoader
import helper
import numpy as np
import gspread
from google.oauth2.service_account import Credentials

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
EVALUATE_SCRIPT_PATH = os.path.join(
    PROJECT_ROOT,
    ".claude",
    "skills",
    "backtest-expert",
    "scripts",
    "evaluate_backtest.py",
)
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1alMqZ1cRn8onmy16RfB0T4n_PMPpSG6RKvHaD_LDewA"
GOOGLE_CREDS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BACKTEST_SHEET = "Backtest"
BACKTEST_COLS = ["個股代號", "個股名稱", "策略名稱", "策略條件", "通知"]

STRATEGY_CONFIG = {
    "EMA_KD": {
        "class": None,  # 於 helper 載入後填入，見下方 _init_strategy_config()
        "optimize": True,
        "params": {"n1": [5, 10, 20], "n2": [20, 60, 100, 120], "kd": 75},
    },
    "EMA_VWAP_KD": {
        "class": None,
        "optimize": True,
        "params": {"n1": [5, 10, 20], "n2": [20, 50, 60, 100, 120], "kd": 75},
    },
    "SmaCross": {
        "class": None,
        "optimize": True,
        "params": {
            "n1": [5, 10, 20],
            "n2": [20, 60, 100],
            "stop_loss": [0.05, 0.1, 0.15, 0.2],
        },
    },
    "SMA_KD": {
        "class": None,
        "optimize": True,
        "params": {
            "n1": [5, 10, 20],
            "n2": [20, 50, 60, 100],
            "kd": 75,
            "stop_loss": [0.05, 0.1, 0.15, 0.2],
        },
    },
    "BOLL_KD30": {
        "class": None,
        "optimize": False,
        "params": {},
    },
    "BOX_RANGE": {
        "class": None,
        "optimize": False,
        "params": {},
    },
    "LEFT_SIDE_MA": {
        "class": None,
        "optimize": True,
        "params": {
            "ma_period": [10, 20, 60, 100, 120],
            "take_profit": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 0.7],
            "stop_loss": [0.05, 0.1, 0.15, 0.2],
        },
    },
    "MA_BIAS": {
        "class": None,
        "optimize": True,
        "params": {
            "ma_period": 25,
            "bias_threshold": -0.15,
            "take_profit": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 1],
            "stop_loss": [0.05, 0.08, 0.1, 0.15, 0.2],
        },
    },
}


def _init_strategy_config():
    STRATEGY_CONFIG["EMA_KD"]["class"] = helper.EMA_KD
    STRATEGY_CONFIG["EMA_VWAP_KD"]["class"] = helper.EMA_VWAP_KD
    STRATEGY_CONFIG["SmaCross"]["class"] = helper.SmaCross
    STRATEGY_CONFIG["SMA_KD"]["class"] = helper.SMA_KD
    STRATEGY_CONFIG["BOLL_KD30"]["class"] = helper.BOLL_KD30
    STRATEGY_CONFIG["BOX_RANGE"]["class"] = helper.BOX_RANGE
    STRATEGY_CONFIG["LEFT_SIDE_MA"]["class"] = helper.LEFT_SIDE_MA
    STRATEGY_CONFIG["MA_BIAS"]["class"] = helper.MA_BIAS


_init_strategy_config()

# python backtest.py 2344 --strategy LEFT_SIDE_MA

warnings.filterwarnings("ignore")
os.environ["BACKTESTING_DISABLE_TQDM"] = "1"

# --all / --multi-year 模式預設比較的策略清單（與原 main() 內的 all 分支保持一致）
DEFAULT_STRATEGIES = [
    # "EMA_KD",
    # "EMA_VWAP_KD",
    "SmaCross",
    # "SMA_KD",
    "LEFT_SIDE_MA",
    # "MA_BIAS",
    # "BOLL_KD30",
    # "BOX_RANGE",
    # "KAHANSHIN",
]


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
    if strategy_name not in STRATEGY_CONFIG:
        raise ValueError(
            f"未知策略: {strategy_name}。可用策略: {list(STRATEGY_CONFIG.keys())}"
        )

    config = STRATEGY_CONFIG[strategy_name]
    bt = Backtest(
        df,
        config["class"],
        cash=100_000,
        commission=0.001425,
        trade_on_close=config.get("trade_on_close", True),
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


def _load_backtest_expert_evaluator():
    """動態載入 .claude/skills/backtest-expert/scripts/evaluate_backtest.py。

    該檔案不是套件模組，故用 importlib 依檔案路徑載入，避免污染 sys.path。
    """
    if not os.path.exists(EVALUATE_SCRIPT_PATH):
        raise FileNotFoundError(
            f"找不到 backtest-expert 評估腳本：{EVALUATE_SCRIPT_PATH}\n"
            "請確認 .claude/skills/backtest-expert 是否已安裝於專案內。"
        )
    spec = importlib.util.spec_from_file_location(
        "backtest_expert_evaluate", EVALUATE_SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _avg_win_loss_pct(trades: pd.DataFrame) -> tuple[float, float]:
    """由交易紀錄計算平均獲利/平均虧損百分比（皆為正值），供 evaluate_backtest 使用。"""
    if trades is None or trades.empty:
        return 0.0, 0.0
    returns = trades["ReturnPct"]
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win_pct = float(wins.mean() * 100) if not wins.empty else 0.0
    avg_loss_pct = float(abs(losses.mean()) * 100) if not losses.empty else 0.0
    return avg_win_pct, avg_loss_pct


def _strategy_vs_buy_hold(stats) -> dict:
    """比較策略報酬與同期間 Buy & Hold 報酬，判斷策略是否跑輸單純買進持有。"""
    return_pct = float(stats["Return [%]"])
    buy_hold_pct = float(stats["Buy & Hold Return [%]"])
    return {
        "return_pct": return_pct,
        "buy_hold_pct": buy_hold_pct,
        "diff_pct": return_pct - buy_hold_pct,
        "underperforms": return_pct < buy_hold_pct,
    }


def compare_top_strategies(
    results: dict, ticker: str, years_tested: float, output_dir=None
):
    """
    運用 backtest-expert skill 的 5 維度評分框架（樣本量/期望值/風控/穩健性/執行現實性），
    比較 optimize 後「最終資產淨值」最佳的兩個策略，供部署前參考。

    注意：僅供參考，正式部署前仍需人工複核（依 Makalot 組織規範）。
    """
    successful = {k: v for k, v in results.items() if v.get("stats") is not None}
    if len(successful) < 2:
        print("⚠️ 可比較的策略數量不足兩個，略過 backtest-expert 評估。")
        return None

    ranked = sorted(successful.items(), key=lambda kv: kv[1]["equity"], reverse=True)
    top_two = ranked[:2]

    try:
        evaluator = _load_backtest_expert_evaluator()
    except FileNotFoundError as e:
        print(f"⚠️ {e}")
        return None

    output_dir = Path(output_dir or os.path.join(SCRIPT_DIR, "reports"))

    evaluations = []
    for strategy_name, data in top_two:
        stats = data["stats"]
        trades = stats["_trades"]
        total_trades = int(stats["# Trades"])
        avg_win_pct, avg_loss_pct = _avg_win_loss_pct(trades)
        num_parameters = len(STRATEGY_CONFIG[strategy_name]["params"])

        result = evaluator.evaluate(
            total_trades=total_trades,
            win_rate=float(stats["Win Rate [%]"]) if total_trades else 0.0,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            max_drawdown_pct=abs(float(stats["Max. Drawdown [%]"])),
            years_tested=max(1, round(years_tested)),
            num_parameters=num_parameters,
            slippage_tested=False,  # run_strategy 目前僅計入手續費，未做滑價壓力測試
        )
        json_path, md_path = evaluator.write_outputs(
            result, output_dir / f"{ticker}_{strategy_name}"
        )
        vs_buy_hold = _strategy_vs_buy_hold(stats)

        # 附加「策略 vs Buy & Hold」檢查到報告，不動 evaluate_backtest.py 本身
        with open(md_path, "a", encoding="utf-8") as f:
            f.write("\n## 額外檢查：策略報酬 vs Buy & Hold\n\n")
            f.write(f"- 策略 Return: {vs_buy_hold['return_pct']:.2f}%\n")
            f.write(f"- Buy & Hold Return: {vs_buy_hold['buy_hold_pct']:.2f}%\n")
            f.write(f"- 差異: {vs_buy_hold['diff_pct']:.2f} 個百分點\n")
            if vs_buy_hold["underperforms"]:
                f.write(
                    "- 🟡 **策略跑輸 Buy & Hold** — 進出場邏輯可能拖累報酬，"
                    "建議檢視是否過早停利/停損或錯過大波段。\n"
                )
            else:
                f.write("- ✅ 策略跑贏 Buy & Hold。\n")

        evaluations.append((strategy_name, result, json_path, md_path, vs_buy_hold))

    print("\n" + "=" * 60)
    print(f"🧪 backtest-expert 評估：比較最佳兩個策略（{ticker}）")
    print("=" * 60)
    for strategy_name, result, json_path, md_path, vs_buy_hold in evaluations:
        equity = successful[strategy_name]["equity"]
        print(f"\n▶ {strategy_name}｜最終淨值 ${equity:,.2f}")
        print(f"  總分: {result['total_score']}/100  判定: {result['verdict']}")
        for dim in result["dimensions"]:
            print(f"    - {dim['name']}: {dim['score']}/{dim['max_score']}")
        if result["red_flags"]:
            for flag in result["red_flags"]:
                icon = "🔴" if flag["severity"] == "high" else "🟡"
                print(f"    {icon} {flag['message']}")
        if vs_buy_hold["underperforms"]:
            print(
                f"    🟡 策略跑輸 Buy & Hold（策略 {vs_buy_hold['return_pct']:.2f}% "
                f"vs Buy & Hold {vs_buy_hold['buy_hold_pct']:.2f}%，"
                f"差 {vs_buy_hold['diff_pct']:.2f} 個百分點）"
            )
        else:
            print(
                f"    ✅ 策略跑贏 Buy & Hold（策略 {vs_buy_hold['return_pct']:.2f}% "
                f"vs Buy & Hold {vs_buy_hold['buy_hold_pct']:.2f}%）"
            )
        print(f"  報告輸出: {md_path}")

    (name_a, result_a, *_), (name_b, result_b, *_) = evaluations
    print("\n" + "-" * 60)
    if result_a["total_score"] == result_b["total_score"]:
        print(
            f"⚖️ 兩策略評分相同（{result_a['total_score']} 分），建議人工複核後再決定。"
        )
    else:
        winner = name_a if result_a["total_score"] > result_b["total_score"] else name_b
        print(f"🏆 backtest-expert 建議優先考慮: {winner}（分數較高，判定較穩健）")
    if all(e[4]["underperforms"] for e in evaluations):
        print(
            "🟡 提醒：這兩個策略在此期間都跑輸 Buy & Hold，優化後表現仍不如單純持有，建議重新檢視策略邏輯或改用其他標的驗證。"
        )
    print("💡 提醒：此評分僅供參考（AI 分析），正式部署前仍需相關人員人工複核。")
    print("=" * 60)

    return evaluations


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
        _format_backtest_header(ws)
        ws.freeze(rows=1)
    else:
        header = ws.row_values(1)
        if header[: len(BACKTEST_COLS)] != BACKTEST_COLS or len(header) != len(
            BACKTEST_COLS
        ):
            _migrate_backtest_worksheet(ws, header)

    return ws


def _format_backtest_header(ws):
    last_col = chr(ord("A") + len(BACKTEST_COLS) - 1)
    ws.format(
        f"A1:{last_col}1",
        {
            "backgroundColor": {"red": 0.13, "green": 0.24, "blue": 0.45},
            "textFormat": {
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                "bold": True,
            },
            "verticalAlignment": "MIDDLE",
        },
    )
    notification_idx = BACKTEST_COLS.index("通知")
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": notification_idx,
                            "endIndex": notification_idx + 1,
                        },
                        "properties": {"pixelSize": 260},
                        "fields": "pixelSize",
                    }
                }
            ]
        }
    )


def _migrate_backtest_worksheet(ws, old_header):
    """欄位結構變動時（例如移除「狀態」欄），依欄位名稱重新對應既有資料並清理多餘欄位。"""
    print("🛠️ 偵測到 Backtest 分頁欄位結構有變動，正在遷移既有資料...")
    all_values = ws.get_all_values()
    data_rows = all_values[1:] if len(all_values) > 1 else []

    col_index = {}
    for idx, col_name in enumerate(old_header):
        col_index.setdefault(col_name, idx)

    def get_cell(row, col_name):
        idx = col_index.get(col_name)
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    new_rows = [
        [get_cell(row, col_name) for col_name in BACKTEST_COLS]
        for row in data_rows
        if any(row)
    ]

    ws.clear()
    ws.update(range_name="A1", values=[BACKTEST_COLS] + new_rows)
    _format_backtest_header(ws)
    ws.freeze(rows=1)


def sync_backtest_position(
    ticker: str,
    name: str,
    strategy_name: str,
    params: dict,
    notification: str = "",
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
            notification,
        ]

        if ticker in codes[1:]:
            row_idx = codes.index(ticker) + 1
            last_col = chr(ord("A") + len(BACKTEST_COLS) - 1)
            ws.update(range_name=f"A{row_idx}:{last_col}{row_idx}", values=[row])
            print(f"🔄 已更新 Google Sheet 分頁既有列: {ticker}")
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
            print(f"📤 已新增至 Google Sheet 分頁: {ticker}")
    except Exception as e:
        print(f"⚠️ 同步分頁失敗: {e}")


def parse_params(param_str: str) -> dict:
    """將 Google Sheet「策略條件」欄位的字串 (例如 'n1=5,n2=20') 還原為 dict。"""
    params = {}
    for pair in (param_str or "").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        params[k] = v
    return params


def run_with_params(df, strategy_name: str, params: dict):
    """使用既定（非優化）參數執行單一策略回測，供每日訊號掃描使用。"""
    if strategy_name not in STRATEGY_CONFIG:
        raise ValueError(
            f"未知策略: {strategy_name}。可用策略: {list(STRATEGY_CONFIG.keys())}"
        )

    config = STRATEGY_CONFIG[strategy_name]
    if strategy_name == "BOLL_KD30":
        helper.BOLL_KD30.buy_strategy = helper.BuyStrategy.BOLL_KD30

    bt = Backtest(
        df,
        config["class"],
        cash=100_000,
        commission=0.001425,
        trade_on_close=config.get("trade_on_close", True),
    )
    return bt.run(**params)


def determine_notification(stats):
    """
    找出回測至今「最近一次」觸發的進場或出場訊號（不限定必須發生在最新一根K棒），
    並判斷出場屬於停損、停利或訊號出場，回傳可讀的通知字串。
    """
    strategy_instance = stats["_strategy"]
    tol = 0.005  # 價格容許誤差(浮點/滑價)

    # 若目前有未平倉部位，最近一次觸發的訊號即為該筆進場（尚未出場，持有中）
    if strategy_instance.trades:
        trade = strategy_instance.trades[-1]
        entry_date = trade.entry_time.strftime("%Y-%m-%d")
        take_profit = getattr(strategy_instance, "take_profit", None)
        if take_profit is not None:
            expected_exit = trade.entry_price * (1 + take_profit)
            return (
                f"🟡 進場 @ {trade.entry_price:.2f}（{entry_date}，持有中，"
                f"預計停利出場 @ {expected_exit:.2f}）"
            )
        return f"🟡 進場 @ {trade.entry_price:.2f}（{entry_date}，持有中）"

    # 否則取最近一筆已平倉交易，判斷出場原因
    if strategy_instance.closed_trades:
        trade = strategy_instance.closed_trades[-1]
        exit_price = trade.exit_price
        exit_date = trade.exit_time.strftime("%Y-%m-%d")
        if trade.sl is not None and abs(exit_price - trade.sl) / trade.sl <= tol:
            return f"🔴 停損出場 @ {exit_price:.2f}（{exit_date}）"
        elif trade.tp is not None and abs(exit_price - trade.tp) / trade.tp <= tol:
            return f"🟢 停利出場 @ {exit_price:.2f}（{exit_date}）"
        else:
            return f"🔵 訊號出場 @ {exit_price:.2f}（{exit_date}）"

    return "⚪ 尚無交易訊號"


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
        notification = determine_notification(stats)

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
        else:
            print(f"📊 目前狀態：【 ⚪ 空手觀望 】")
            print(f"💡 建議：等待下一次買入訊號")

        print(f"🔔 最近一次觸發訊號：{notification}")

        if ticker and to_sheet:
            name = get_stock_name(ticker)
            sync_backtest_position(
                ticker,
                name,
                strategy_name,
                dict(strategy_instance._params),
                notification,
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


def run_multi_window_comparison(
    ticker: str,
    market: str,
    windows: list[float],
    strategies: list[str] = None,
):
    """
    在多個回測年數視窗下分別跑完整最佳化，比較各策略排名是否穩定。

    目的：單一年數（例如只跑 -y 3 或只跑 -y 5）挑出的「最佳策略」，
    本質上是該區間的樣本內（in-sample）最優解，換一段區間結果可能整個翻盤
    （詳見 backtest-expert skill 的 Curve-Fitting / Regime-Specific Performance 說明）。
    此函式讓你一次看到同一檔股票在不同年數視窗下，各策略的名次與淨值變化，
    藉此判斷哪個策略是「跨區間穩健」，而不是「只在特定切點贏」。

    注意：此比較僅為 AI 分析輔助判斷，正式部署前仍需人工複核（依 Makalot 組織規範）。
    """
    strategies = strategies or DEFAULT_STRATEGIES
    today = datetime.today()

    # window_results[strategy][years] = {"equity": ..., "rank": ...} 或 None（執行失敗）
    window_results: dict[str, dict[float, dict]] = {s: {} for s in strategies}
    window_best: dict[float, str] = {}

    for years in windows:
        start_date = (today - relativedelta(years=years)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        print(f"\n{'#'*60}")
        print(f"📆 回測視窗: 近 {years} 年（{start_date} ~ {end_date}）")
        print(f"{'#'*60}")

        df = get_data(market, ticker, start_date, end_date)
        if df is None or df.empty:
            print(f"⚠️ 視窗 {years} 年無有效資料，略過。")
            continue

        equities = {}
        for s in strategies:
            try:
                stats = run_strategy(df, s)
                equities[s] = float(stats["Equity Final [$]"])
                print_result(stats, s)
            except Exception as e:
                print(f"\n{'='*50}\n策略 {s} 於 {years} 年視窗執行失敗: {e}\n{'='*50}")
                window_results[s][years] = None
                continue

        if not equities:
            continue

        ranked = sorted(equities.items(), key=lambda kv: kv[1], reverse=True)
        window_best[years] = ranked[0][0]
        for rank, (s, equity) in enumerate(ranked, start=1):
            window_results[s][years] = {"equity": equity, "rank": rank}

    # --- 彙整輸出比較表 ---
    valid_windows = [y for y in windows if y in window_best]
    print("\n" + "=" * 70)
    print(f"🧭 多年數視窗策略排名比較 {ticker}")
    print("=" * 70)

    if not valid_windows:
        print("⚠️ 所有視窗皆無有效結果，無法比較。")
        return None

    header = f"{'策略':<16}" + "".join(
        f"{f'{y}年 淨值(排名)':>26}" for y in valid_windows
    )
    print(header)
    for s in strategies:
        row = f"{s:<16}"
        for y in valid_windows:
            r = window_results[s].get(y)
            if r is None:
                row += f"{'失敗':>26}"
            else:
                cell = f"${r['equity']:,.0f}(#{r['rank']})"
                row += f"{cell:>26}"
        print(row)

    # 穩健性判定：計算每個策略在各視窗的平均排名、是否每次都進前二
    print("\n" + "-" * 70)
    print("📊 穩健性摘要（排名越接近 1 且越一致，代表跨區間越穩健）")
    print("-" * 70)
    stability = {}
    for s in strategies:
        ranks = [
            window_results[s][y]["rank"]
            for y in valid_windows
            if window_results[s].get(y) is not None
        ]
        if not ranks:
            continue
        avg_rank = sum(ranks) / len(ranks)
        always_top2 = all(r <= 2 for r in ranks)
        stability[s] = {
            "avg_rank": avg_rank,
            "ranks": ranks,
            "always_top2": always_top2,
        }
        print(
            f"  - {s}: 平均排名 {avg_rank:.2f}（各視窗排名 {ranks}），"
            f"{'✅ 每次皆進前二' if always_top2 else '⚠️ 曾跌出前二'}"
        )

    distinct_winners = set(window_best.values())
    if len(distinct_winners) > 1:
        print(
            f"\n🔴 警訊：不同年數視窗的冠軍策略不一致（{window_best}），"
            "顯示至少有策略是樣本內最優解，而非跨區間穩健策略。"
            "建議依平均排名/穩健性摘要判斷，而非只看單一視窗的冠軍（詳見 backtest-expert skill）。"
        )
        if stability:
            most_stable = min(stability, key=lambda k: stability[k]["avg_rank"])
            print(
                f"💡 若需選一個策略，平均排名最佳者為: {most_stable}（僅供參考，仍需人工複核）"
            )
    else:
        winner = distinct_winners.pop()
        print(f"\n✅ 所有視窗冠軍一致: {winner}，穩健性較高。")

    print("💡 提醒：此比較僅供參考（AI 分析），正式部署前仍需相關人員人工複核。")
    print("=" * 70)

    return {
        "window_results": window_results,
        "window_best": window_best,
        "stability": stability,
    }


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
        "-y", "--years", type=int, default=3, help="回測年數（預設 10 年）"
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
        help="指定策略（預設 all）：EMA_KD, EMA_VWAP_KD, SmaCross, SMA_KD, SHORT_SMA_CROSS, BOLL_KD30, BOX_RANGE, LEFT_SIDE_MA, MA_BIAS, KAHANSHIN, NEURAL_SEASONALITY。不帶值則列出所有可用策略",
    )
    parser.add_argument(
        "--to-sheet",
        action="store_true",
        help="若目前有未平倉部位，將結果輸出至 Google Sheet（預設不輸出）",
    )
    parser.add_argument(
        "--cs",
        action="store_true",
        help="以 all 模式跑完所有策略後，呼叫 backtest-expert skill 比較最佳兩個策略（預設不執行）",
    )
    parser.add_argument(
        "--multi-year",
        action="store_true",
        help="在多個回測年數視窗（見 --windows）下分別跑完整最佳化，比較各策略排名是否穩定，"
        "用於檢查「換個 -y 年數，最佳策略就變」的樣本內過擬合問題（預設不執行）",
    )
    parser.add_argument(
        "--windows",
        type=str,
        default="3,5,10",
        help="搭配 --multi-year 使用，逗號分隔的回測年數清單（預設 3,5,10）",
    )

    args = parser.parse_args()
    ticker = args.ticker
    years = args.years
    months = args.months
    strategy = args.strategy
    to_sheet = args.to_sheet
    compare_strategies = args.cs
    multi_year = args.multi_year

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
            "MA_BIAS",
            "KAHANSHIN",
        ]:
            print(f"  - {s}")
        return

    if multi_year:
        try:
            windows = [float(w.strip()) for w in args.windows.split(",") if w.strip()]
        except ValueError:
            print(
                f"錯誤：--windows 格式不正確: {args.windows!r}，應為逗號分隔的數字，例如 3,5,10"
            )
            return
        run_multi_window_comparison(ticker, args.market, windows)
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
        strategies = DEFAULT_STRATEGIES
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

            # --- 新增：用 backtest-expert 比較最佳兩個策略（需帶 --compare-strategies）---
            if compare_strategies:
                compare_top_strategies(results, ticker, years + months / 12)
        else:
            print("所有策略執行失敗。")

    else:
        stats = run_strategy(df, strategy)
        print_result(stats, strategy)
        check_current_signal(stats, strategy, ticker, to_sheet)


if __name__ == "__main__":
    main()
