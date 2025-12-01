import sqlite3
from statsmodels.tsa.stattools import pacf
import numpy as np


def query_data(query: str):
    try:
        conn = sqlite3.connect("mystock.db")
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()
    except sqlite3.Error as e:
        print("message: ", e)
        return None


def best_pacf_lag(data, max_lags=30):
    pacf_values = pacf(data, nlags=max_lags, method="ywadjusted")
    conf_int = 1.96 / np.sqrt(len(data))  # 95% confidence threshold

    # Find first lag where PACF falls within confidence bounds
    for lag in range(1, len(pacf_values)):
        if abs(pacf_values[lag]) < conf_int:
            return lag - 1

    return max_lags
