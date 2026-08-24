import pandas as pd
import numpy as np
from enum import Enum
from backtesting import Strategy
from backtesting.lib import crossover
from backtesting.test import SMA


def calculate_bollinger_bands(close, n=20):
    close_series = pd.Series(close)
    middle = close_series.rolling(window=n).mean()
    std = close_series.rolling(window=n).std()
    upper = middle + (std * 2)
    lower = middle - (std * 2)
    return upper, lower


def bollinger_bands(close, n=20, dev=2.0):
    """回傳布林通道 (上軌, 中軌, 下軌)。

    中軌 = n 日簡單移動平均 (SMA)
    上/下軌 = 中軌 ± dev * n 日標準差 (STD)
    """
    s = pd.Series(close)
    middle = s.rolling(window=n).mean()
    std = s.rolling(window=n).std()
    upper = middle + dev * std
    lower = middle - dev * std
    return upper.to_numpy(), middle.to_numpy(), lower.to_numpy()


def calculate_rsi(close, n=14):
    """Wilder's RSI（相對強弱指標）。"""
    s = pd.Series(close)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder 平滑：等同 alpha = 1/n 的指數移動平均
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.to_numpy()


def calculate_kdj(high_data, low_data, close_data, n=9):
    high_series = pd.Series(high_data)
    low_series = pd.Series(low_data)
    close_series = pd.Series(close_data)

    ln = low_series.rolling(window=n).min()
    hn = high_series.rolling(window=n).max()
    rsv = ((close_series - ln) / (hn - ln).replace(0, np.nan)) * 100
    rsv = rsv.fillna(0)  # 處理空值

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()

    return k.to_numpy(), d.to_numpy()


def EMA(values, n):
    close = pd.Series(values)
    return close.ewm(span=n, adjust=False).mean()


def VWAP(high, low, close, volume):
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / volume.cumsum()


def ma_bias(close, n=25):
    """乖離率 (BIAS) = (收盤價 - n日均線) / n日均線，以小數表示（-0.2 即 -20%）。"""
    s = pd.Series(close)
    ma = s.rolling(window=n).mean()
    return ((s - ma) / ma.replace(0, np.nan)).to_numpy()


def yearly_seasonality(close, dates):
    from neuralprophet import NeuralProphet, set_log_level

    set_log_level("ERROR")
    df = pd.DataFrame(
        {"ds": pd.to_datetime(dates), "y": np.asarray(close, dtype=float)}
    )

    m = NeuralProphet(
        n_changepoints=0,
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
    )
    m.fit(df, epochs=30, batch_size=32, early_stopping=True, progress=None)
    forecast = m.predict(df, decompose=True)
    return forecast["season_yearly"].to_numpy()


class BuyStrategy(Enum):
    BOLL_KD30 = "布林下軌KD<30"
    BOLL_RSI30 = "布林下軌RSI<30"
    VOL_KD30 = "成交量KD<30"


class SmaCross(Strategy):
    n1 = 20
    n2 = 60
    stop_loss = 0.08

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)

    def next(self):
        price = self.data.Close[-1]

        if crossover(self.sma1, self.sma2):
            self.buy(sl=price * (1 - self.stop_loss))

        elif crossover(self.sma2, self.sma1):
            if self.position and self.position.pl > 0.0:
                self.position.close()
            # self.sell()


class SHORT_SMA_CROSS(Strategy):
    """均線交叉的反向操作（放空策略）

    - 死亡交叉（短均線跌破長均線）→ 放空 (self.sell)
    - 黃金交叉（短均線突破長均線）→ 平倉 (position.close)
    """

    n1 = 20
    n2 = 60
    stop_loss = 0.08

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)

    def next(self):
        price = self.data.Close[-1]

        # 死亡交叉：短均線跌破長均線 → 放空
        if crossover(self.sma2, self.sma1):
            self.sell(sl=price * (1 + self.stop_loss))

        # 黃金交叉：短均線突破長均線 → 平倉
        elif crossover(self.sma1, self.sma2):
            if self.position:
                self.position.close()


class BOLL_KD30(Strategy):
    k_period = 14
    d_period = 3
    buy_strategy = BuyStrategy.BOLL_KD30

    def init(self):
        # Calculate Bollinger Bands using your function
        self.upper, self.lower = self.I(calculate_bollinger_bands, self.data.Close)

        # Calculate KDJ using your function
        self.k, self.d = self.I(
            calculate_kdj, self.data.High, self.data.Low, self.data.Close
        )

        # Calculate 5-day average volume
        self.avg_5_vol = self.I(
            lambda data: pd.Series(data).rolling(5).mean(), self.data.Volume
        )

    def next(self):
        if self.buy_strategy == BuyStrategy.BOLL_KD30:
            buy_condition = (
                (self.data.Close[-1] <= self.lower[-1])
                & (self.k[-1] < 30)
                & (self.d[-1] < 30)
            )
        elif self.buy_strategy == BuyStrategy.VOL_KD30:
            buy_condition = (
                (self.data.Volume[-1] > self.avg_5_vol)
                & (self.k[-1] < 30)
                & (self.d[-1] < 30)
            )

        if buy_condition:
            self.buy()
        elif self.data.Close[-1] >= self.upper[-1]:
            if self.position:
                self.position.close()


class SMA_KD(Strategy):
    n1 = 5
    n2 = 20
    kd = 75
    stop_loss = 0.1  # 動態停損(移動停損)：停損價隨最高價同步上移，只漲不跌，鎖利兼限損

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)
        self.k, self.d = self.I(
            calculate_kdj, self.data.High, self.data.Low, self.data.Close
        )

    def next(self):
        price = self.data.Close[-1]

        if crossover(self.sma1, self.sma2):
            self.buy(sl=price * (1 - self.stop_loss))

        # 動態停損：停損價只會隨股價創高往上調整，不會因股價拉回而下修
        for trade in self.trades:
            new_sl = price * (1 - self.stop_loss)
            if trade.sl is None or new_sl > trade.sl:
                trade.sl = new_sl

        if (self.k[-1] > self.kd) and (self.d[-1] > self.kd):
            if self.position and self.position.pl > 0.0:
                self.position.close()


class SMA_BULL(Strategy):
    n1 = 5
    n2 = 20

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)
        self.upper, self.lower = self.I(calculate_bollinger_bands, self.data.Close)

    def next(self):
        if crossover(self.sma1, self.sma2):
            self.buy()
        elif self.position and self.position.pl > 0.0:
            if self.data.Close[-1] >= self.upper[-1]:
                self.position.close()


class EMA_KD(Strategy):
    n1 = 9
    n2 = 20
    kd = 75

    def init(self):
        self.ema1 = self.I(EMA, self.data.Close, self.n1)
        self.ema2 = self.I(EMA, self.data.Close, self.n2)
        self.k, self.d = self.I(
            calculate_kdj, self.data.High, self.data.Low, self.data.Close
        )

    def next(self):
        if crossover(self.ema1, self.ema2):
            self.buy()

        elif (self.k[-1] > self.kd) and (self.d[-1] > self.kd):
            if self.position and self.position.pl > 0.0:
                self.position.close()


class EMA_VWAP_KD(Strategy):
    n1 = 9
    n2 = 20
    kd = 75

    def init(self):
        self.ema1 = self.I(EMA, self.data.Close, self.n1)
        self.ema2 = self.I(EMA, self.data.Close, self.n2)
        self.k, self.d = self.I(
            calculate_kdj, self.data.High, self.data.Low, self.data.Close
        )
        self.vwap = self.I(
            VWAP, self.data.High, self.data.Low, self.data.Close, self.data.Volume
        )

    def next(self):
        # if self.position:
        #     print(
        #         f"日期: {self.data.index[-1]} | K: {self.k[-1]:.2f} | D: {self.d[-1]:.2f} | 獲利: {self.position.pl:.2f}"
        #     )
        if crossover(self.ema1, self.ema2) and self.data.Close[-1] > self.vwap[-1]:
            self.buy()

        elif (self.k[-1] > self.kd) and (self.d[-1] > self.kd):
            if self.position and self.position.pl > 0.0:
                self.position.close()


class BOX_RANGE(Strategy):
    n_box = 10  # 縮短觀察期，對短期波動更敏感
    buffer = 0.01  # 增加緩衝區到
    rsi_window = 14

    def init(self):
        # 縮短箱型週期
        self.box_top = self.I(
            lambda x: pd.Series(x).rolling(self.n_box).max().shift(1), self.data.High
        )
        self.box_bottom = self.I(
            lambda x: pd.Series(x).rolling(self.n_box).min().shift(1), self.data.Low
        )

    def next(self):
        price = self.data.Close[-1]

        # --- 買進邏輯：觸及箱底 OR RSI 低位回升 ---
        if not self.position:
            # 只要價格靠近箱底，或是 RSI < 40 (超賣區)，就進場
            if price <= self.box_bottom[-1] * (1 + self.buffer):
                self.buy()

        # --- 賣出邏輯：分批獲利 OR 觸及箱頂 ---
        elif self.position:
            if price >= self.box_top[-1] * (1 - self.buffer):
                self.position.close()


class NEURAL_SEASONALITY(Strategy):
    threshold = 0.0
    take_profit = 0.2

    def init(self):
        self.seasonality = self.I(yearly_seasonality, self.data.Close, self.data.index)

    def next(self):
        prev, curr = self.seasonality[-2], self.seasonality[-1]
        if np.isnan(prev) or np.isnan(curr):
            return

        if not self.position and prev <= self.threshold < curr:
            self.buy()
        elif self.position and self.position.pl_pct > self.take_profit * 100:
            self.position.close()


class KAHANSHIN(Strategy):
    """下半身策略

    進場：非盤整趨勢 + 昨日收盤在5MA之下 + 今日紅K且實體中點站上5MA + 今日成交量>20日均量
    停損/停利：比照 LEFT_SIDE_MA，進場當下依固定比例設定停損/停利價位。
    """

    ma_short = 5
    ma_mid = 20
    ma_long = 60
    take_profit = 0.2
    stop_loss = 0.08

    def init(self):
        self.ma5 = self.I(SMA, self.data.Close, self.ma_short)
        self.ma20 = self.I(SMA, self.data.Close, self.ma_mid)
        self.ma60 = self.I(SMA, self.data.Close, self.ma_long)
        self.vol_ma20 = self.I(
            lambda v: pd.Series(v).rolling(20).mean(), self.data.Volume
        )

    def next(self):
        ma5, ma20, ma60 = self.ma5[-1], self.ma20[-1], self.ma60[-1]
        if np.isnan(ma5) or np.isnan(ma20) or np.isnan(ma60):
            return
        if len(self.data) < 2:
            return

        is_bull = ma5 > ma20 > ma60
        is_bear = ma60 > ma20 > ma5
        is_range = not (is_bull or is_bear)

        c, o = self.data.Close[-1], self.data.Open[-1]
        prev_c, prev_ma5 = self.data.Close[-2], self.ma5[-2]
        body_center = (o + c) / 2
        vol, vol_ma20 = self.data.Volume[-1], self.vol_ma20[-1]

        yesterday_kahanshin = prev_c <= prev_ma5
        is_kahanshin = (
            not is_range
            and yesterday_kahanshin
            and c > o
            and body_center > ma5
            and vol > vol_ma20
        )

        if not self.position and is_kahanshin:
            self.buy(
                sl=c * (1 - self.stop_loss),
                tp=c * (1 + self.take_profit),
            )


class LEFT_SIDE_MA(Strategy):
    ma_period = 60
    take_profit = 0.2
    stop_loss = 0.08
    cooldown_bars = 5  # 停損出場後,幾根K棒內不再進場
    max_hold_bars = 60  # 持倉超過此交易日數仍未觸及停損/停利,無條件出場(時間停損)

    def init(self):
        self.ma20 = self.I(SMA, self.data.Close, self.ma_period)
        self.last_stop_bar = -self.cooldown_bars

    def next(self):
        price = self.data.Close[-1]
        ma20 = self.ma20[-1]
        bar = len(self.data) - 1

        # 時間停損：進場超過 max_hold_bars 個交易日,若停損/停利都還沒觸發,直接出場。
        # 放在最前面,不受下方 ma20 是否為 nan 或冷卻期限制影響。
        if self.position:
            for trade in self.trades:
                if bar - trade.entry_bar >= self.max_hold_bars:
                    trade.close()

        if np.isnan(ma20):
            return

        # 若上一筆交易剛於本根K棒平倉且為虧損(觸及停損),記錄冷卻起點
        if self.closed_trades and self.closed_trades[-1].exit_bar == bar:
            if self.closed_trades[-1].pl < 0:
                self.last_stop_bar = bar

        if bar - self.last_stop_bar < self.cooldown_bars:
            return

        # 進場條件改為「隔日確認」：前一根K棒發生向下穿越均線,且今天收盤仍在均線下方,才進場。
        # 目的：過濾單日假跌破後立即翻多的雜訊,避免破線當天就進場被巴。
        if bar < 2:
            return

        crossed_below_yesterday = crossover(self.ma20[:-1], self.data.Close[:-1])
        still_below_today = price < ma20

        if not self.position and crossed_below_yesterday and still_below_today:
            self.buy(
                sl=price * (1 - self.stop_loss),
                tp=price * (1 + self.take_profit),
            )


class MA_BIAS(Strategy):
    """負乖離策略

    進場：收盤價對 25MA 的乖離率向下跌破 -20%
    停利/停損：比照 LEFT_SIDE_MA,進場當下依固定比例設定停利/停損價位,
    並沿用停損後的冷卻期。
    """

    ma_period = 25
    bias_threshold = -0.2  # 乖離率門檻,-0.2 = -20%
    take_profit = 0.2
    stop_loss = 0.08
    cooldown_bars = 5  # 停損出場後,幾根K棒內不再進場

    def init(self):
        self.ma25 = self.I(SMA, self.data.Close, self.ma_period)
        self.bias = self.I(ma_bias, self.data.Close, self.ma_period)
        self.last_stop_bar = -self.cooldown_bars

    def next(self):
        price = self.data.Close[-1]
        bias = self.bias[-1]
        bar = len(self.data) - 1

        if np.isnan(bias):
            return

        # 若上一筆交易剛於本根K棒平倉且為虧損(觸及停損),記錄冷卻起點
        if self.closed_trades and self.closed_trades[-1].exit_bar == bar:
            if self.closed_trades[-1].pl < 0:
                self.last_stop_bar = bar

        if bar - self.last_stop_bar < self.cooldown_bars:
            return

        # 以「向下跌破門檻」取代單純「低於門檻」,避免乖離長期偏低時反覆進場
        if not self.position and crossover(self.bias_threshold, self.bias):
            self.buy(
                sl=price * (1 - self.stop_loss),
                tp=price * (1 + self.take_profit),
            )
