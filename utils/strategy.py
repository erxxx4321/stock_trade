from abc import ABC, abstractmethod
import pandas as pd
from enum import Enum
from backtesting.lib import crossover


class BuyStrategy(Enum):
    BOLL_KD30 = "BOLL_KD30"
    SMA_5_20 = "SMA_5_20"
    SMA_10_20 = "SMA_10_20"
    SMA_10_50 = "SMA_10_50"
    SMA_10_60 = "SMA_10_60"
    EMA_5_20 = "EMA_5_20"
    EMA_5_60 = "EMA_5_60"
    EMA_20_50 = "EMA_20_50"
    EMA_20_60 = "EMA_20_60"
    EMA_10_50 = "EMA_10_50"
    EMA_10_100 = "EMA_10_100"
    EMA_10_120 = "EMA_10_120"
    KD20 = "KD<20"
    # BOLL_RSI30 = "布林下軌RSI<30"
    # VOL_KD30 = "成交量KD<30"


class SellStrategy(Enum):
    BOLL_UP = "BOLL_UP"
    # FIVE_MA_VOL = "5MA成交量
    KD70 = "KD>70"
    KD75 = "KD>75"
    KD80 = "KD>80"
    KD85 = "KD>85"


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

class KD20(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] < 20) & (df["d"] < 20)

class KD70(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 70) & (df["d"] > 70)


class KD75(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 75) & (df["d"] > 75)


class KD80(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 80) & (df["d"] > 80)
    
class KD85(BaseStrategy):
    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        return (df["k"] > 85) & (df["d"] > 85)


class SMA_CROSSOVER(BaseStrategy):
    def __init__(self, n1: int = 5, n2: int = 20):
        self.n1 = n1
        self.n2 = n2

    def get_condition(self, df: pd.DataFrame) -> pd.Series:
        sma_n1 = df["Close"].rolling(window=self.n1).mean()
        sma_n2 = df["Close"].rolling(window=self.n2).mean()

        sma_n1_prev = sma_n1.shift(1)
        sma_n2_prev = sma_n2.shift(1)

        if self.n1 < self.n2:
            return (sma_n1 > sma_n2) & (sma_n1_prev <= sma_n2_prev)
        elif self.n1 > self.n2:
            return (sma_n1 < sma_n2) & (sma_n1_prev >= sma_n2_prev)


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


def create_strategy(buy_strategy_enum: BuyStrategy):
    name = buy_strategy_enum.name
    parts = name.split("_")

    if name == BuyStrategy.BOLL_KD30.name:
        return BOLL_KD30()
    if name == BuyStrategy.KD20.name:
        return KD20()

    elif len(parts) == 3:
        indicator_type = parts[0]
        try:
            n1 = int(parts[1])
            n2 = int(parts[2])
        except ValueError:
            raise ValueError(f"Could not parse n1/n2 from strategy name: {name}")

        if indicator_type == "SMA":
            return SMA_CROSSOVER(n1=n1, n2=n2)
        elif indicator_type == "EMA":
            return EMA_CROSSOVER(n1=n1, n2=n2)
        else:
            raise NotImplementedError(f"Unknown crossover type: {indicator_type}")
    else:
        raise NotImplementedError(f"Strategy {name} does not follow naming convention.")


buy_strategy_group = {
    strategy.value: create_strategy(strategy) for strategy in BuyStrategy
}
sell_strategy_group = {
    SellStrategy.BOLL_UP.value: BOLL_UP(),
    SellStrategy.KD70.value: KD70(),
    SellStrategy.KD75.value: KD75(),
    SellStrategy.KD80.value: KD80(),
    SellStrategy.KD85.value: KD85(),
}


def get_trade_condition(df: pd.DataFrame, buy_strategy: str, sell_strategy: str):
    if buy_strategy == "":
        buy_condition = pd.Series([False] * len(df), index=df.index)
    else:
        buy_condition =  buy_strategy_group.get(buy_strategy).get_condition(df)

    if sell_strategy == "":
        sell_condition = pd.Series([False] * len(df), index=df.index)
    else:
        sell_condition = sell_strategy_group.get(sell_strategy).get_condition(df)
    return buy_condition, sell_condition
