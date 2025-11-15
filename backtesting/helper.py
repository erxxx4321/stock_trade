import pandas as pd
from enum import Enum
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA


def calculate_bollinger_bands(close, n=20):
    close_series = pd.Series(close)
    middle = close_series.rolling(window=n).mean()
    std = close_series.rolling(window=n).std()
    upper = middle + (std * 2)
    lower = middle - (std * 2)
    return upper, lower


def calculate_kdj(high_data, low_data, close_data, n=9):
    high_series = pd.Series(high_data)
    low_series = pd.Series(low_data)
    close_series = pd.Series(close_data)

    ln = low_series.rolling(window=n).min()
    hn = high_series.rolling(window=n).max()
    rsv = ((close_series - ln) / (hn - ln)) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()

    return k, d


def EMA(values, n):
    close = pd.Series(values)
    return close.ewm(span=n, adjust=False).mean()


def VWAP(high, low, close, volume):
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / volume.cumsum()


class BuyStrategy(Enum):
    BOLL_KD30 = "布林下軌KD<30"
    BOLL_RSI30 = "布林下軌RSI<30"
    VOL_KD30 = "成交量KD<30"


class SmaCross(Strategy):
    n1 = 20
    n2 = 60

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)

    def next(self):
        if crossover(self.sma1, self.sma2):
            self.buy()

        elif crossover(self.sma2, self.sma1):
            if self.position and self.position.pl > 0.0:
                self.position.close()
            # self.sell()


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

    def init(self):
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)
        self.k, self.d = self.I(
            calculate_kdj, self.data.High, self.data.Low, self.data.Close
        )

    def next(self):
        if crossover(self.sma1, self.sma2):
            self.buy()
        elif (self.k[-1] > self.kd) and (self.d[-1] > self.kd):
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
        if crossover(self.ema1, self.ema2) and self.data.Close[-1] > self.vwap[-1]:
            self.buy()

        elif (self.k[-1] > 75) and (self.d[-1] > 75):
            if self.position and self.position.pl > 0.0:
                self.position.close()
