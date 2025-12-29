#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google News FactSet 新聞爬蟲 + SQLite 資料庫整合
"""
import requests
from bs4 import BeautifulSoup
import time
import argparse
from datetime import datetime as dt
import sqlite3
import re

class FactSetNewsDB:
    """FactSet 新聞資料庫管理類"""
    
    def __init__(self, db_name='mystock.db'):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        
    def connect(self):
        """連接資料庫"""
        self.conn = sqlite3.connect(self.db_name)
        self.cursor = self.conn.cursor()
        print(f"✓ 已連接到資料庫: {self.db_name}")
        
    def create_table(self):
        """創建 factset_news 資料表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS factset_news (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT NOT NULL,
            eps REAL,
            est_price REAL,
            date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.cursor.execute(create_table_sql)
        self.conn.commit()
        print("✓ 資料表 factset_news 已創建/確認")
        
    def parse_factset_title(self, title, date_str):
        """解析 FactSet 新聞標題"""
        result = {
            'stock_code': None,
            'stock_name': None,
            'eps': None,
            'est_price': None,
            'date': date_str
        }
        
        # 提取股票名稱和代碼
        stock_pattern = r'：([^(]+)\((\d+)-TW\)'
        stock_match = re.search(stock_pattern, title)
        if stock_match:
            result['stock_name'] = stock_match.group(1).strip()
            result['stock_code'] = stock_match.group(2)
        
        # 提取 EPS
        eps_pattern = r'EPS預估(?:下修|上修)至([\d.]+)元'
        eps_match = re.search(eps_pattern, title)
        if eps_match:
            result['eps'] = float(eps_match.group(1))
        
        # 提取目標價
        price_pattern = r'預估目標價為([\d.]+)元'
        price_match = re.search(price_pattern, title)
        if price_match:
            result['est_price'] = float(price_match.group(1))
        
        return result
        
    def insert_or_update(self, stock_code, stock_name, eps, est_price, date):
        """插入或更新資料"""
        self.cursor.execute(
            "SELECT stock_code FROM factset_news WHERE stock_code = ?",
            (stock_code,)
        )
        exists = self.cursor.fetchone()
        
        if exists:
            update_sql = """
            UPDATE factset_news 
            SET stock_name = ?, eps = ?, est_price = ?, date = ?, updated_at = ?
            WHERE stock_code = ?
            """
            self.cursor.execute(
                update_sql,
                (stock_name, eps, est_price, date, dt.now().isoformat(), stock_code)
            )
            action = "更新"
        else:
            insert_sql = """
            INSERT INTO factset_news (stock_code, stock_name, eps, est_price, date)
            VALUES (?, ?, ?, ?, ?)
            """
            self.cursor.execute(
                insert_sql,
                (stock_code, stock_name, eps, est_price, date)
            )
            action = "新增"
        
        self.conn.commit()
        return action
        
    def insert_from_news_title(self, title, date_str):
        """從新聞標題直接解析並插入資料庫"""
        data = self.parse_factset_title(title, date_str)
        
        if not data['stock_code']:
            return False, "無法解析股票代碼"
            
        action = self.insert_or_update(
            data['stock_code'],
            data['stock_name'],
            data['eps'],
            data['est_price'],
            data['date']
        )
        
        return True, f"{action} - {data['stock_code']} {data['stock_name']}: EPS={data['eps']}, 目標價={data['est_price']}"
        
    def display_all(self):
        """顯示所有資料"""
        self.cursor.execute("SELECT * FROM factset_news ORDER BY date DESC")
        rows = self.cursor.fetchall()
        
        if not rows:
            print("資料庫中沒有資料")
            return
            
        print("\n" + "="*120)
        print(f"{'股票代碼':<10} {'股票名稱':<15} {'EPS':<10} {'目標價':<10} {'日期':<20}")
        print("="*120)
        
        for row in rows:
            stock_code, stock_name, eps, est_price, date, _, _ = row
            print(f"{stock_code:<10} {stock_name:<15} {eps:<10.2f} {est_price:<10.2f} {date:<20}")
        
        print("="*120)
        print(f"總計: {len(rows)} 筆資料\n")
        
    def close(self):
        """關閉資料庫連線"""
        if self.conn:
            self.conn.close()


def scrape_factset_news(keyword='factset 最新調查', save_to_db=True, db_name='mystock.db'):
    """
    爬取 Google News 上的 FactSet 新聞並儲存到資料庫
    """
    url = f"https://news.google.com/search?q={keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    print(f"正在爬取 Google News...")
    print(f"關鍵字: {keyword}")
    print(f"網址: {url}\n")
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 找到所有新聞容器
        news_containers = soup.find_all('div', class_='IFHyqb')
        
        print(f"找到 {len(news_containers)} 個新聞容器\n")
        
        # 初始化資料庫
        db = None
        if save_to_db:
            db = FactSetNewsDB(db_name)
            db.connect()
            db.create_table()
            print()
        
        news_items = []
        saved_count = 0
        
        for container in news_containers:
            # 提取標題
            title_link = container.find('a', class_='JtKRv')
            if not title_link:
                continue
            title = title_link.get_text(strip=True)
            
            # 只處理包含 "Factset" 和股票代碼的新聞
            if 'factset' not in title.lower() or '-TW)' not in title:
                continue
            
            # 提取時間
            date = None
            datetime_value = None
            display_time = None
            
            time_container = container.find('div', class_='UOVeFe')
            if time_container:
                time_tag = time_container.find('time')
                if time_tag:
                    datetime_value = time_tag.get('datetime')
                    display_time = time_tag.get_text(strip=True)
                    
                    if datetime_value:
                        try:
                            dt_obj = dt.fromisoformat(datetime_value.replace('Z', '+00:00'))
                            date = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            date = datetime_value
            
            if not date:
                date = '日期未知'
            
            # 顯示找到的新聞
            print(f"找到 FactSet 新聞:")
            print(f"  標題: {title}")
            print(f"  時間: {date} ({display_time})")
            
            # 儲存到資料庫
            if save_to_db and db and date != '日期未知':
                success, message = db.insert_from_news_title(title, date)
                if success:
                    print(f"  ✓ {message}")
                    saved_count += 1
                else:
                    print(f"  ✗ {message}")
            
            print()
            
            news_items.append({
                'title': title,
                'date': date,
                'display_time': display_time
            })
        
        # 顯示資料庫內容
        if save_to_db and db:
            print("\n" + "="*120)
            print("資料庫中的所有 FactSet 新聞:")
            print("="*120)
            db.display_all()
            db.close()
        
        print(f"\n總結: 找到 {len(news_items)} 則 FactSet 新聞")
        if save_to_db:
            print(f"成功儲存 {saved_count} 則到資料庫")
        
        return news_items
        
    except Exception as e:
        print(f"發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    parser = argparse.ArgumentParser(
        description='爬取 Google News 的 FactSet 新聞並儲存到 SQLite 資料庫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用範例:
  python scrape_and_save.py
  python scrape_and_save.py --keyword "factset 台積電"
  python scrape_and_save.py --db custom.db
  python scrape_and_save.py --no-save  (只爬取不存資料庫)
        '''
    )
    
    parser.add_argument(
        '--keyword',
        type=str,
        default='factset 最新調查',
        help='搜尋關鍵字（預設: factset 最新調查）'
    )
    
    parser.add_argument(
        '--db',
        type=str,
        default='mystock.db',
        help='資料庫檔案名稱（預設: mystock.db）'
    )
    
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='不儲存到資料庫，只顯示結果'
    )
    
    args = parser.parse_args()
    
    print("="*120)
    print("Google News FactSet 新聞爬蟲 + 資料庫儲存")
    print("="*120)
    print()
    
    scrape_factset_news(
        keyword=args.keyword,
        save_to_db=not args.no_save,
        db_name=args.db
    )


if __name__ == "__main__":
    main()