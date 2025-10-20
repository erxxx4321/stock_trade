from abc import ABC, abstractmethod
import pandas as pd
from enum import Enum


class BuyStrategy(Enum):
    BOLL_KD30 = "布林下軌KD<30"
    SMA5_SMA20 = "SMA5_20"
    SMA20_SMA60 = "SMA20_60"
    EMA20_EMA60 = "EMA20_60"
    EMA10_EMA50 = "EMA10_50"
    # BOLL_RSI30 = "布林下軌RSI<30"
    # VOL_KD30 = "成交量KD<30"


class SellStrategy(Enum):
    BOLL_UP = "布林上軌"
    # FIVE_MA_VOL = "5MA成交量"
    KD70 = "KD>70"
    KD75 = "KD>75"
    KD80 = "KD>80"


# 抽象基底類別
class BaseStrategy(ABC):
    @abstractmethod
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        pass


class BOLL_KD30(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["Close"] <= df["Lower"]) & (df["k"] < 30) & (df["d"] < 30)


class BOLL_UP(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return df["Close"] >= df["Upper"]


class KD70(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 70) & (df["d"] > 70)


class KD75(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 75) & (df["d"] > 75)


class KD80(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 80) & (df["d"] > 80)


class SMA_CROSSOVER(BaseStrategy):
    def __init__(self, n1: int = 5, n2: int = 20):
        self.n1 = n1
        self.n2 = n2

    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        sma_fast = df["Close"].rolling(window=self.n1).mean()
        sma_slow = df["Close"].rolling(window=self.n2).mean()

        # Previous period SMAs for crossover detection
        sma_fast_prev = sma_fast.shift(1)
        sma_slow_prev = sma_slow.shift(1)

        return (sma_fast > sma_slow) & (sma_fast_prev <= sma_slow_prev)


class EMA_CROSSOVER(BaseStrategy):
    def __init__(self, n1: int = 9, n2: int = 20):
        self.n1 = n1
        self.n2 = n2

    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        ema_fast = df["Close"].ewm(span=self.n1, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=self.n2, adjust=False).mean()

        ema_fast_prev = ema_fast.shift(1)
        ema_slow_prev = ema_slow.shift(1)

        return (ema_fast > ema_slow) & (ema_fast_prev <= ema_slow_prev)


buy_strategy_group = {
    BuyStrategy.BOLL_KD30.value: BOLL_KD30(),
    BuyStrategy.SMA5_SMA20.value: SMA_CROSSOVER(n1=5, n2=20),
    BuyStrategy.SMA20_SMA60.value: SMA_CROSSOVER(n1=20, n2=60),
    BuyStrategy.EMA20_EMA60.value: EMA_CROSSOVER(n1=20, n2=60),
    BuyStrategy.EMA10_EMA50.value: EMA_CROSSOVER(n1=10, n2=50),
}
sell_strategy_group = {
    SellStrategy.BOLL_UP.value: BOLL_UP(),
    SellStrategy.KD70.value: KD70(),
    SellStrategy.KD75.value: KD75(),
    SellStrategy.KD80.value: KD80(),
}


def get_trade_condition(df: pd.DataFrame, buy_strategy: str, sell_strategy: str):
    buy_condition = buy_strategy_group.get(buy_strategy).get_condition(df)
    sell_condition = sell_strategy_group.get(sell_strategy).get_condition(df)
    return buy_condition, sell_condition
