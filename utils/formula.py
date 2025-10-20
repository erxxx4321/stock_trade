import pandas as pd


# --- KDJ 計算函式 ---
def calculate_kdj(df, n=9):
    df["Ln"] = df["Low"].rolling(window=n).min()
    df["Hn"] = df["High"].rolling(window=n).max()
    df["rsv"] = ((df["Close"] - df["Ln"]) / (df["Hn"] - df["Ln"])) * 100
    df["k"] = df["rsv"].ewm(com=2, adjust=False).mean()
    df["d"] = df["k"].ewm(com=2, adjust=False).mean()
    return df[["k", "d"]]


# --- 布林通道計算函式 ---
def calculate_bollinger_bands(df, n=20):
    df["Middle"] = df["Close"].rolling(window=n).mean()
    df["Std"] = df["Close"].rolling(window=n).std()
    df["Upper"] = df["Middle"] + (df["Std"] * 2)
    df["Lower"] = df["Middle"] - (df["Std"] * 2)
    return df[["Middle", "Upper", "Lower"]]


# --- 新增的 RSI 計算函式 ---
def calculate_rsi(df, period=14):
    """
    參數:
    df (DataFrame): 包含 'Close' 欄位的股價資料。
    period (int): RSI 的計算週期，預設為 14 天。

    回傳:
    DataFrame: 包含 'rsi' 欄位。
    """
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return pd.DataFrame({"rsi": rsi})
