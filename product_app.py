"""
Upbit 자동 매매 봇 메인 모듈 (다중 코인 실행 지원)
"""

# 기본 라이브러리 임포트
import os
import time
import logging
import sys
import argparse
from datetime import datetime
from typing import Dict, Optional, Any

# 서드파티 라이브러리
import pyupbit
import requests
from dotenv import load_dotenv

# Python 3.12 sqlite3 호환성을 위한 설정
import sqlite3
sqlite3.register_adapter(datetime, lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
sqlite3.register_converter("timestamp", lambda x: datetime.strptime(x.decode(), '%Y-%m-%d %H:%M:%S'))

# Windows 환경에서만 winsound 모듈 import (소리 알림용)
if sys.platform == 'win32':
    import winsound

# --- 설정 및 전역 변수 선언 ---

# 설정 클래스 임포트
from config.config import APIConfig, TradingConfig, PathConfig

# API 설정 (환경변수에서 로드)
load_dotenv()
ACCESS_KEY = APIConfig.ACCESS_KEY
SECRET_KEY = APIConfig.SECRET_KEY
DISCORD_WEBHOOK_URL = APIConfig.DISCORD_WEBHOOK_URL

# 거래 관련 전역 변수 (실행 시 동적으로 설정됨)
TICKER: Optional[str] = None
BASE_PRICE: Optional[float] = None
PRICE_CHANGE: Optional[float] = None
GRID_INTERVAL_PERCENT: Optional[float] = None  # 동적 그리드 간격 퍼센트
MAX_GRID_COUNT: Optional[int] = None
ORDER_AMOUNT: Optional[float] = None
CHECK_INTERVAL: Optional[int] = None
FEE_RATE: Optional[float] = None
DISCORD_LOGGING: Optional[bool] = None
PLAY_SOUND: Optional[bool] = None

# 시스템 관련 전역 변수
DB_FILE: Optional[str] = None
logger = logging.getLogger()
upbit: Optional[pyupbit.Upbit] = None
discord_logger: 'DiscordLogger'

# 상태 관련 전역 변수
current_price: float = 0
previous_price: Optional[float] = None
grid_orders: list = []
trade_history: list = []


class DiscordLogger:
    """디스코드로 로그를 전송하는 전용 로거"""
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send(self, message, level="INFO"):
        if not self.enabled:
            return
        try:
            color = {'INFO': 0x00ff00, 'WARNING': 0xffff00, 'ERROR': 0xff0000, 'CRITICAL': 0xff0000}.get(level, 0x808080)
            kst_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            payload = {"embeds": [{"title": f"[{TICKER} - {level}]", "description": f"{message}\n\n{kst_time} (KST)", "color": color}]}
            requests.post(self.webhook_url, json=payload)
        except Exception as e:
            print(f"Discord 로그 전송 중 오류 발생: {str(e)}")


def setup_logging(ticker: str) -> None:
    """티커에 따라 로깅 설정을 초기화합니다."""
    path_config = PathConfig(ticker)
    log_file = path_config.get_log_filename()

    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler()]
    )
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(file_handler)
    logger.info(f"'{ticker}'에 대한 로깅 설정 완료. 로그 파일: {log_file}")


def setup_application(ticker: str) -> bool:
    """커맨드 라인 인자를 기반으로 애플리케이션 설정을 초기화합니다."""
    global TICKER, BASE_PRICE, PRICE_CHANGE, GRID_INTERVAL_PERCENT, MAX_GRID_COUNT, ORDER_AMOUNT
    global CHECK_INTERVAL, FEE_RATE, DISCORD_LOGGING, PLAY_SOUND
    global DB_FILE, upbit, discord_logger

    # 1. 티커에 맞는 설정 로드
    coin_config = TradingConfig.get_coin_config(ticker)
    if not coin_config:
        logger.error(f"'{ticker}'에 대한 설정을 config.py에서 찾을 수 없습니다.")
        return False

    # 2. 전역 변수 설정
    TICKER = coin_config["TICKER"]
    BASE_PRICE = coin_config["BASE_PRICE"]
    PRICE_CHANGE = coin_config.get("PRICE_CHANGE", 0)
    GRID_INTERVAL_PERCENT = coin_config.get("GRID_INTERVAL_PERCENT", 0)
    MAX_GRID_COUNT = coin_config["MAX_GRID_COUNT"]
    ORDER_AMOUNT = coin_config["ORDER_AMOUNT"]

    CHECK_INTERVAL = TradingConfig.CHECK_INTERVAL
    FEE_RATE = TradingConfig.FEE_RATE
    DISCORD_LOGGING = TradingConfig.DISCORD_LOGGING
    PLAY_SOUND = TradingConfig.PLAY_SOUND

    # 3. 티커 기반 경로 및 클라이언트 초기화
    path_config = PathConfig(ticker)
    DB_FILE = path_config.get_db_filename()
    
    # 4. 로깅 재설정
    setup_logging(ticker)

    # 5. Upbit 및 Discord 클라이언트 초기화
    if not all([ACCESS_KEY, SECRET_KEY]):
        logger.error("API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        return False
    upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
    discord_logger = DiscordLogger(DISCORD_WEBHOOK_URL)

    logger.info(f"'{TICKER}' 애플리케이션 설정 완료.")
    return True


def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            logger.info(f"데이터베이스 연결: {DB_FILE}")
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS grid (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, grid_level INTEGER,
                buy_price_target REAL, sell_price_target REAL, order_krw_amount REAL,
                is_bought BOOLEAN, actual_bought_volume REAL, actual_buy_fill_price REAL,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, buy_sell TEXT, grid_level INTEGER,
                price REAL, amount REAL, volume REAL, fee REAL, profit REAL, profit_percentage REAL,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, krw_balance REAL, coin_balance REAL,
                coin_avg_price REAL, total_assets REAL, current_price REAL,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )''')
            conn.commit()
            logger.info("데이터베이스 초기화 완료")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 중 오류 발생: {e}")

# ... (save_trade, save_balance, save_grid 함수들은 DB_FILE과 TICKER 전역 변수를 사용하므로 수정 불필요) ...
def save_trade(trade_data):
    """거래 내역을 데이터베이스에 저장"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO trades (
                ticker, buy_sell, grid_level, price, amount, 
                volume, fee, profit, profit_percentage, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                TICKER, trade_data['type'], trade_data['grid_level'], trade_data['price'],
                trade_data['amount'], trade_data['volume'], trade_data.get('fee', 0),
                trade_data.get('profit', 0), trade_data.get('profit_percentage', 0),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"거래 내역 저장 중 오류 발생: {e}")

def save_balance(balance_data):
    """잔고 현황을 데이터베이스에 저장"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO balance_history (
                timestamp, krw_balance, coin_balance, 
                coin_avg_price, total_assets, current_price
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), balance_data['krw'],
                balance_data['coin'], balance_data['coin_avg_price'],
                balance_data['total_assets'], current_price
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"잔고 현황 저장 중 오류 발생: {e}")

def save_grid(grid_data):
    """그리드 상태를 데이터베이스에 업데이트"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM grid WHERE grid_level = ? AND ticker = ? ORDER BY timestamp DESC LIMIT 1', (grid_data['level'], TICKER))
            result = cursor.fetchone()
            
            if result:
                cursor.execute('''
                UPDATE grid SET
                    buy_price_target = ?, sell_price_target = ?, order_krw_amount = ?, is_bought = ?,
                    actual_bought_volume = ?, actual_buy_fill_price = ?, timestamp = ?
                WHERE id = ?
                ''', (
                    grid_data['buy_price_target'], grid_data['sell_price_target'], grid_data['order_krw_amount'],
                    grid_data['is_bought'], grid_data['actual_bought_volume'], grid_data['actual_buy_fill_price'],
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), result[0]
                ))
            else:
                cursor.execute('''
                INSERT INTO grid (
                    ticker, grid_level, buy_price_target, sell_price_target, order_krw_amount,
                    is_bought, actual_bought_volume, actual_buy_fill_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    TICKER, grid_data['level'], grid_data['buy_price_target'], grid_data['sell_price_target'],
                    grid_data['order_krw_amount'], grid_data['is_bought'],
                    grid_data['actual_bought_volume'], grid_data['actual_buy_fill_price']
                ))
            conn.commit()
    except Exception as e:
        logger.error(f"그리드 상태 저장 중 오류 발생: {e}")


def get_current_price():
    """현재 가격 조회"""
    global current_price, previous_price
    try:
        ticker_price = pyupbit.get_current_price(TICKER)
        if ticker_price is None:
            logger.warning("현재가를 가져오지 못했습니다.")
            return None
        
        if previous_price is None: previous_price = ticker_price
        
        price_change_val = ticker_price - previous_price
        change_percentage = (price_change_val / previous_price) * 100 if previous_price > 0 else 0
        sign = "+" if price_change_val >= 0 else ""
        
        logger.info(f"현재 {TICKER} 가격: {ticker_price:,.2f}원 ({sign}{change_percentage:.2f}%)")
        
        previous_price = ticker_price
        current_price = ticker_price
        return ticker_price
    except Exception as e:
        logger.error(f"가격 조회 중 오류 발생: {e}")
        return None

def get_balance():
    """계좌 잔고 조회"""
    try:
        krw_balance = upbit.get_balance("KRW")
        coin_balance = upbit.get_balance(TICKER)
        coin_avg_price = upbit.get_avg_buy_price(TICKER) if coin_balance > 0 else 0
        
        current_coin_value = coin_balance * current_price if coin_balance > 0 and current_price > 0 else 0
        total_assets = krw_balance + current_coin_value

        logger.info(f"잔고: {krw_balance:,.0f}원, {TICKER} {coin_balance:.8f}개, 총 자산 {total_assets:,.0f}원")

        balance_data = {"krw": krw_balance, "coin": coin_balance, "coin_avg_price": coin_avg_price, "total_assets": total_assets}
        save_balance(balance_data)
        return balance_data
    except Exception as e:
        logger.error(f"잔고 조회 중 오류 발생: {e}")
        return None

def create_grid_orders(input_base_price=None):
    """분할 매수/매도 그리드 주문 생성 (동적/고정 간격 지원)"""
    global grid_orders, BASE_PRICE
    current_market_price = get_current_price()
    if current_market_price is None:
        logger.error("현재 가격을 가져올 수 없어 그리드 생성을 중단합니다.")
        return False

    BASE_PRICE = input_base_price if input_base_price is not None else current_market_price
    logger.info(f"그리드 기준 가격: {BASE_PRICE:,.2f}원")

    # --- 동적 간격 계산 로직 ---
    if GRID_INTERVAL_PERCENT and GRID_INTERVAL_PERCENT > 0:
        # 퍼센트 기반 동적 간격 사용
        price_change_amount = BASE_PRICE * (GRID_INTERVAL_PERCENT / 100.0)
        logger.info(f"동적 간격 모드 활성화 ({GRID_INTERVAL_PERCENT}%) -> 계산된 간격: {price_change_amount:,.2f}원")
    else:
        # 기존 고정 간격 사용
        price_change_amount = PRICE_CHANGE
        logger.info(f"고정 간격 모드 활성화 -> 설정된 간격: {price_change_amount:,.0f}원")

    if price_change_amount <= 0:
        logger.error("그리드 간격이 0 또는 음수입니다. 설정을 확인해주세요.")
        return False
    # --- 로직 종료 ---

    grid_orders = []
    for i in range(MAX_GRID_COUNT):
        buy_target_price = BASE_PRICE - (i * price_change_amount)
        grid = {
            'level': i + 1,
            'buy_price_target': buy_target_price,
            'sell_price_target': buy_target_price + price_change_amount,
            'buy_price_min': buy_target_price - price_change_amount,
            'order_krw_amount': ORDER_AMOUNT,
            'is_bought': False, 'actual_bought_volume': 0.0, 'actual_buy_fill_price': 0.0
        }
        grid_orders.append(grid)
        save_grid(grid)

    logger.info(f"총 {len(grid_orders)}개의 그리드 생성 완료. (주문액: {ORDER_AMOUNT:,.0f}원)")
    return True

def play_sound(sound_type):
    """거래 알림음 재생"""
    if not PLAY_SOUND or sys.platform != 'win32': return
    try:
        sound_file = f'res/{sound_type}.wav'
        if os.path.exists(sound_file):
            winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            logger.warning(f"사운드 파일 없음: {sound_file}")
    except Exception as e:
        logger.error(f"알림음 재생 중 오류: {e}")

def buy_coin(grid_level):
    """지정된 그리드 레벨에서 코인 시장가 매수"""
    grid = grid_orders[grid_level - 1]
    if grid['is_bought']: return False

    try:
        if upbit.get_balance("KRW") < grid['order_krw_amount']:
            logger.warning(f"잔액 부족으로 매수 불가 (L{grid_level})")
            return False

        order_response = upbit.buy_market_order(TICKER, grid['order_krw_amount'])
        if not order_response or 'uuid' not in order_response:
            logger.error(f"매수 주문 실패 (L{grid_level}): {order_response}")
            return False
        
        time.sleep(2) # 체결 대기
        order_detail = upbit.get_order(order_response['uuid'])

        actual_volume = float(order_detail.get('executed_volume', 0))
        actual_price = float(order_detail.get('avg_price', current_price))
        fee = float(order_detail.get('paid_fee', grid['order_krw_amount'] * FEE_RATE))

        if actual_volume <= 0:
            logger.error(f"매수 체결 수량 0 (L{grid_level})")
            return False

        grid.update({'is_bought': True, 'actual_bought_volume': actual_volume, 'actual_buy_fill_price': actual_price})
        save_grid(grid)

        trade = {'type': 'buy', 'grid_level': grid_level, 'price': actual_price, 'amount': grid['order_krw_amount'], 'volume': actual_volume, 'fee': fee}
        save_trade(trade)

        logger.info(f"매수 성공 (L{grid_level}): {actual_volume:.8f} {TICKER} @ {actual_price:,.2f}원")
        discord_logger.send(f"매수 성공 (L{grid_level}): {actual_volume:.8f} {TICKER} @ {actual_price:,.2f}원", "INFO")
        play_sound('buy')
        get_balance()
        return True
    except Exception as e:
        logger.error(f"매수 중 오류 (L{grid_level}): {e}")
        return False

def sell_coin(grid_level):
    """지정된 그리드 레벨에서 코인 시장가 매도"""
    grid = grid_orders[grid_level - 1]
    if not grid['is_bought']: return False
    
    volume_to_sell = grid['actual_bought_volume']
    if upbit.get_balance(TICKER) < volume_to_sell:
        logger.warning(f"보유량 부족으로 매도 불가 (L{grid_level})")
        return False

    try:
        order_response = upbit.sell_market_order(TICKER, volume_to_sell)
        if not order_response or 'uuid' not in order_response:
            logger.error(f"매도 주문 실패 (L{grid_level}): {order_response}")
            return False

        time.sleep(2) # 체결 대기
        order_detail = upbit.get_order(order_response['uuid'])

        actual_price = float(order_detail.get('avg_price', current_price))
        fee = float(order_detail.get('paid_fee', (volume_to_sell * actual_price) * FEE_RATE))
        net_sell_krw = (volume_to_sell * actual_price) - fee
        profit = net_sell_krw - grid['order_krw_amount']
        profit_percentage = (profit / grid['order_krw_amount']) * 100 if grid['order_krw_amount'] > 0 else 0

        grid.update({'is_bought': False, 'actual_bought_volume': 0.0, 'actual_buy_fill_price': 0.0})
        save_grid(grid)

        trade = {'type': 'sell', 'grid_level': grid_level, 'price': actual_price, 'amount': net_sell_krw, 'volume': volume_to_sell, 'fee': fee, 'profit': profit, 'profit_percentage': profit_percentage}
        save_trade(trade)

        logger.info(f"매도 성공 (L{grid_level}): {volume_to_sell:.8f} {TICKER} @ {actual_price:,.2f}원 | 수익: {profit:+,.0f}원 ({profit_percentage:+.2f}%)")
        discord_logger.send(f"매도 성공 (L{grid_level}): {volume_to_sell:.8f} {TICKER} @ {actual_price:,.2f}원\n수익: {profit:+,.0f}원 ({profit_percentage:+.2f}%)", "INFO")
        play_sound('sell')
        get_balance()
        return True
    except Exception as e:
        logger.error(f"매도 중 오류 (L{grid_level}): {e}")
        return False

def check_price_and_trade():
    """현재 가격을 확인하고 거래를 실행합니다. 거래가 발생하면 True를 반환합니다."""
    if current_price is None or current_price <= 0:
        logger.warning("유효하지 않은 현재 가격으로 거래 로직 건너뜀.")
        return False

    traded = False
    for grid in grid_orders:
        level = grid['level']
        if not grid['is_bought'] and grid['buy_price_min'] < current_price <= grid['buy_price_target']:
            logger.info(f"매수 조건 충족 (L{level}): 현재가({current_price:,.2f})가 구간({grid['buy_price_min']:,.2f}~{grid['buy_price_target']:,.2f}) 내 위치")
            if buy_coin(level):
                traded = True
                time.sleep(1)
        elif grid['is_bought'] and current_price >= grid['sell_price_target']:
            logger.info(f"매도 조건 충족 (L{level}): 현재가({current_price:,.2f}) >= 매도 목표가({grid['sell_price_target']:,.2f})")
            if sell_coin(level):
                traded = True
                time.sleep(1)
    return traded

def run_trading():
    """메인 거래 루프"""
    init_db()
    logger.info(f"===== {TICKER} 자동 매매 시작 =====")
    discord_logger.send(f"===== {TICKER} 자동 매매 시작 =====")

    if not create_grid_orders(BASE_PRICE):
        logger.error("그리드 주문 생성 실패. 프로그램을 종료합니다.")
        return

    logger.info("===== 매매 루프 시작 =====")
    last_balance_save_time = 0
    BALANCE_SAVE_INTERVAL = 120  # 120초(2분)마다 잔고 저장

    while True:
        if get_current_price() is not None:
            traded = check_price_and_trade()
            
            # 거래가 발생했거나, 일정 시간이 지났으면 잔고 저장
            if traded or (time.time() - last_balance_save_time > BALANCE_SAVE_INTERVAL):
                get_balance()
                last_balance_save_time = time.time()
        
        logger.info(f"{CHECK_INTERVAL}초 대기...")
        time.sleep(CHECK_INTERVAL)

def main() -> None:
    """인자 파싱 및 봇 실행"""
    parser = argparse.ArgumentParser(description="Upbit Grid Trading Bot")
    parser.add_argument("--ticker", type=str, required=True, help="거래할 티커 (예: KRW-BTC)")
    args = parser.parse_args()

    if not setup_application(args.ticker):
        sys.exit(1)

    # 현 세션 시작 시간 기록 (KST 시간대 포함)
    try:
        from datetime import timezone, timedelta
        KST = timezone(timedelta(hours=9))
        
        path_config = PathConfig(args.ticker)
        session_file = path_config.get_session_filename()
        with open(session_file, 'w', encoding='utf-8') as f:
            f.write(datetime.now(KST).isoformat())
        logger.info(f"세션 시작 시간 기록 완료: {session_file}")
    except Exception as e:
        logger.error(f"세션 시작 시간 기록 실패: {e}")

    try:
        run_trading()
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
        discord_logger.send(f"{TICKER} 거래가 사용자에 의해 중단되었습니다.", "WARNING")
    except Exception as e:
        logger.critical(f"치명적인 오류 발생: {e}", exc_info=True)
        discord_logger.send(f"{TICKER} 거래 중 치명적인 오류 발생: {e}", "CRITICAL")
    finally:
        logger.info("===== 거래 로직 종료 =====")
        get_balance()

if __name__ == "__main__":
    main()
