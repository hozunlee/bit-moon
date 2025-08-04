"""
Upbit 자동 매매 봇 메인 모듈 (리팩토링 버전)
- DB 로직 분리 (db_handler)
- 코인별 ON/OFF 및 예산 관리 기능 추가
"""
import os
import time
import logging
import sys
import threading
import random
from datetime import datetime
from typing import Dict, List, Any

import pyupbit
import requests
from dotenv import load_dotenv

# --- 모듈 임포트 ---
load_dotenv()
from config.config import APIConfig, DBConfig, TradingConfig, PathConfig
import db_handler as db

# --- 전역 설정 ---
if sys.platform == 'win32':
    import winsound

upbit = pyupbit.Upbit(APIConfig.ACCESS_KEY, APIConfig.SECRET_KEY)
discord_logger = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(threadName)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

# --- Discord 로거 클래스 ---
class DiscordLogger:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send(self, message, level="INFO"):
        if not self.enabled: return
        try:
            color = {'INFO': 0x00ff00, 'WARNING': 0xffff00, 'ERROR': 0xff0000}.get(level, 0x808080)
            kst_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            payload = {"embeds": [{"title": f"[{level}]", "description": f"{message}\n\n{kst_time} (KST)", "color": color}]}
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Discord 로그 전송 중 오류: {e}")

# --- 데이터 저장 함수 (db_handler 호출) ---
def save_trade(trade_data: Dict[str, Any]):
    sql = "INSERT INTO trades (ticker, buy_sell, grid_level, price, amount, volume, fee, profit, profit_percentage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    params = (
        trade_data['ticker'], trade_data['type'], trade_data['grid_level'],
        trade_data['price'], trade_data['amount'], trade_data['volume'],
        trade_data.get('fee', 0), trade_data.get('profit', 0), trade_data.get('profit_percentage', 0)
    )
    db.execute(sql, params)

def save_balance(balance_data: Dict[str, Any]):
    sql = "INSERT INTO balance_history (ticker, krw_balance, coin_balance, coin_avg_price, total_assets, current_price) VALUES (%s, %s, %s, %s, %s, %s)"
    params = (
        balance_data['ticker'], balance_data['krw'], balance_data['coin'],
        balance_data['coin_avg_price'], balance_data['total_assets'], balance_data['current_price']
    )
    db.execute(sql, params)

def save_grid(grid_data: Dict[str, Any]):
    sql = """
    INSERT INTO grid (ticker, grid_level, buy_price_target, sell_price_target, order_krw_amount, is_bought, actual_bought_volume, actual_buy_fill_price)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (ticker, grid_level) DO UPDATE SET
        buy_price_target = EXCLUDED.buy_price_target, sell_price_target = EXCLUDED.sell_price_target,
        order_krw_amount = EXCLUDED.order_krw_amount, is_bought = EXCLUDED.is_bought,
        actual_bought_volume = EXCLUDED.actual_bought_volume, actual_buy_fill_price = EXCLUDED.actual_buy_fill_price,
        timestamp = CURRENT_TIMESTAMP;
    """
    params = (
        grid_data['ticker'], grid_data['level'], grid_data['buy_price_target'],
        grid_data['sell_price_target'], grid_data['order_krw_amount'], grid_data['is_bought'],
        grid_data['actual_bought_volume'], grid_data['actual_buy_fill_price']
    )
    db.execute(sql, params)

def init_coin_config(coin_config: Dict[str, Any]):
    sql = """
    INSERT INTO coin_config (ticker, budget_krw, is_active) VALUES (%s, %s, %s)
    ON CONFLICT (ticker) DO UPDATE SET
        budget_krw = EXCLUDED.budget_krw;
    """
    params = (coin_config['TICKER'], coin_config.get('BUDGET_KRW', 0), True)
    db.execute(sql, params)

# --- 거래 로직 클래스 ---
class TradingBot:
    def __init__(self, coin_config: Dict[str, Any]):
        self.ticker = coin_config["TICKER"]
        self.logger = logging.getLogger(self.ticker)

        # 예산 초기 검증: 0 이하일 경우 경고 로그를 남기고 0으로 처리 (is_within_budget에서 막힘)
        initial_budget = coin_config.get("BUDGET_KRW", 0)
        if initial_budget <= 0:
            self.logger.warning(f"초기 할당 예산이 0 또는 음수({initial_budget})입니다. 예산을 설정하기 전까지 신규 매수가 제한됩니다.")
            self.budget_krw = 0
        else:
            self.budget_krw = initial_budget
        self.base_price = coin_config["BASE_PRICE"]
        self.price_change = coin_config["PRICE_CHANGE"]
        self.max_grid_count = coin_config["MAX_GRID_COUNT"]
        self.order_amount = coin_config["ORDER_AMOUNT"]
        
        self.check_interval = TradingConfig.CHECK_INTERVAL
        self.fee_rate = TradingConfig.FEE_RATE
        self.play_sound_enabled = TradingConfig.PLAY_SOUND

        self.grid_orders: List[Dict[str, Any]] = []
        self.current_price: float = 0
        
        self.is_test_mode = os.environ.get("APP_MODE") == "TEST"
        if self.is_test_mode:
            self.logger.warning("!!! 테스트 모드로 실행 중입니다. 실제 거래가 발생하지 않습니다. !!!")

    def get_current_price(self):
        """현재가를 조회합니다. 테스트 모드에서는 가상 가격을 생성합니다."""
        if self.is_test_mode:
            if self.current_price == 0:
                self.current_price = self.base_price
            else:
                change_percent = random.uniform(-0.01, 0.01)
                self.current_price *= (1 + change_percent)
            self.logger.info(f"[테스트] 가상 현재가: {self.current_price:,.2f}원")
            return self.current_price

        try:
            price = pyupbit.get_current_price(self.ticker)
            if price is None: return None
            self.current_price = price
            return self.current_price
        except Exception as e:
            self.logger.error(f"가격 조회 오류: {e}")
            return None

    def get_balance(self):
        """현재 KRW 및 코인 잔고를 조회하고 DB에 기록합니다. 테스트 모드에서는 가상 잔고를 사용합니다."""
        try:
            if self.is_test_mode:
                krw_balance = 10000000
                coin_balance = 10
                coin_avg_price = self.base_price * 0.98
            else:
                krw_balance = upbit.get_balance("KRW")
                coin_balance_info = upbit.get_balance(self.ticker, verbose=True)
                coin_balance = coin_balance_info['balance']
                coin_avg_price = coin_balance_info['avg_buy_price']

            if self.current_price == 0:
                self.get_current_price()

            total_assets = krw_balance + (coin_balance * self.current_price)

            balance_data = {
                'ticker': self.ticker, 'krw': krw_balance, 'coin': coin_balance,
                'coin_avg_price': coin_avg_price, 'total_assets': total_assets,
                'current_price': self.current_price
            }
            save_balance(balance_data)
            self.logger.info(f"잔고 업데이트: 총 자산 {total_assets:,.0f}원 (현금: {krw_balance:,.0f}, {self.ticker}: {coin_balance})")
        except Exception as e:
            self.logger.error(f"잔고 조회/저장 중 오류 발생: {e}")

    def create_grid_orders(self):
        """분할 매수/매도 그리드 주문 생성"""
        self.logger.info("그리드 주문 생성 시작...")
        
        if self.base_price is None:
            self.base_price = self.get_current_price()
            if self.base_price is None:
                self.logger.error("기준 가격을 설정할 수 없어 그리드 생성을 중단합니다.")
                return False
            self.logger.info(f"현재가 기준으로 기준 가격 설정: {self.base_price:,.2f}원")

        self.grid_orders = []
        for i in range(self.max_grid_count):
            buy_target_price = self.base_price - (i * self.price_change)
            sell_target_price = buy_target_price + self.price_change
            grid = {
                'ticker': self.ticker, 'level': i + 1, 'buy_price_target': buy_target_price,
                'sell_price_target': sell_target_price, 'order_krw_amount': self.order_amount,
                'is_bought': False, 'actual_bought_volume': 0.0, 'actual_buy_fill_price': 0.0
            }
            self.grid_orders.append(grid)
            save_grid(grid)

        self.logger.info(f"총 {len(self.grid_orders)}개의 그리드 설정 완료.")
        return True

    def is_trade_active(self) -> bool:
        """DB에서 현재 코인의 거래 활성화 상태를 확인"""
        row = db.fetchone("SELECT is_active FROM coin_config WHERE ticker = %s", (self.ticker,))
        if row and row['is_active'] == 0:
            self.logger.info("거래 중지 상태입니다. 모든 거래 로직을 건너뜁니다.")
            return False
        return True

    def is_within_budget(self) -> bool:
        """새로운 매수가 예산 한도 내에 있는지 확인"""
        if self.budget_krw <= 0:
            return True
        sql = "SELECT COALESCE(SUM(order_krw_amount), 0) AS total FROM grid WHERE ticker = %s AND is_bought = TRUE"
        result = db.fetchone(sql, (self.ticker,))
        invested_capital = result['total'] if result else 0
        if (invested_capital + self.order_amount) > self.budget_krw:
            self.logger.warning(f"예산 한도 초과. 현재 투입액: {invested_capital:,.0f}, 다음 주문액: {self.order_amount:,.0f}, 예산: {self.budget_krw:,.0f}")
            return False
        return True

    def buy_coin(self, grid: Dict[str, Any]):
        if not self.is_within_budget():
            return False

        if self.is_test_mode:
            self.logger.info(f"[테스트] 가상 매수 실행: Level {grid['level']} at {self.current_price:,.2f}원")
            grid['is_bought'] = True
            grid['actual_bought_volume'] = grid['order_krw_amount'] / self.current_price
            grid['actual_buy_fill_price'] = self.current_price
            save_grid(grid)
            trade_data = {
                'ticker': self.ticker, 'type': 'buy', 'grid_level': grid['level'],
                'price': self.current_price, 'amount': grid['order_krw_amount'],
                'volume': grid['actual_bought_volume']
            }
            save_trade(trade_data)
            if self.play_sound_enabled and sys.platform == 'win32': winsound.Beep(800, 200)
            return True
        
        self.logger.warning("운영 모드의 매수 로직이 구현되지 않았습니다.")
        return False

    def sell_coin(self, grid: Dict[str, Any]):
        if self.is_test_mode:
            self.logger.info(f"[테스트] 가상 매도 실행: Level {grid['level']} at {self.current_price:,.2f}원")
            profit = (self.current_price - grid['actual_buy_fill_price']) * grid['actual_bought_volume']
            profit_percentage = (profit / grid['order_krw_amount']) * 100
            trade_data = {
                'ticker': self.ticker, 'type': 'sell', 'grid_level': grid['level'],
                'price': self.current_price, 'amount': grid['order_krw_amount'],
                'volume': grid['actual_bought_volume'], 'profit': profit,
                'profit_percentage': profit_percentage
            }
            save_trade(trade_data)
            grid['is_bought'] = False
            grid['actual_bought_volume'] = 0.0
            grid['actual_buy_fill_price'] = 0.0
            save_grid(grid)
            if self.play_sound_enabled and sys.platform == 'win32': winsound.Beep(400, 200)
            return True

        self.logger.warning("운영 모드의 매도 로직이 구현되지 않았습니다.")
        return False

    def check_price_and_trade(self):
        if not self.is_trade_active():
            return
        if self.get_current_price() is None:
            return
        for grid in self.grid_orders:
            if not grid['is_bought'] and self.current_price <= grid['buy_price_target']:
                self.buy_coin(grid)
                time.sleep(1)
            elif grid['is_bought'] and self.current_price >= grid['sell_price_target']:
                self.sell_coin(grid)
                time.sleep(1)

    def run(self):
        threading.current_thread().name = self.ticker
        self.logger.info(f"===== {self.ticker} 자동 매매 시작 ====")
        if not self.create_grid_orders():
            self.logger.error("그리드 생성 실패. 거래를 시작할 수 없습니다.")
            return
        self.get_balance()
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                self.logger.info(f"--- 사이클 #{cycle_count} ---")
                self.check_price_and_trade()
                if cycle_count % 6 == 0:
                    self.get_balance()
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                self.logger.info("거래 중단 신호 수신.")
                break
            except Exception as e:
                self.logger.error(f"거래 루프 중 예외 발생: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                time.sleep(self.check_interval * 2)

def main():
    global discord_logger
    discord_logger = DiscordLogger(APIConfig.DISCORD_WEBHOOK_URL)
    logger.info("거래 봇 시스템을 시작합니다.")
    db.init_db(DBConfig)
    db.create_all_tables()
    for coin_config in TradingConfig.COIN_LIST:
        init_coin_config(coin_config)
    threads = []
    for coin_config in TradingConfig.COIN_LIST:
        bot = TradingBot(coin_config)
        thread = threading.Thread(target=bot.run, name=bot.ticker, daemon=True)
        threads.append(thread)
        thread.start()
        time.sleep(2)
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info("\n프로그램을 종료합니다.")
    finally:
        logger.info("시스템 종료.")

if __name__ == "__main__":
    main()