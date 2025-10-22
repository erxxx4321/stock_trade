import sqlite3


def query_data(query: str):
    try:
        conn = sqlite3.connect("mystock.db")
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()
    except sqlite3.Error as e:
        print("message: ", e)
        return None
