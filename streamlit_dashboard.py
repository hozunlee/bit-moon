import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import numpy as np
import time
import streamlit.components.v1 as components
import glob
import os
from pathlib import Path

# 설정 가져오기
from config.config import DBConfig, TradingConfig

# --- 전역 설정 ---
REFRESH_INTERVAL = 10  # 자동 새로고침 간격 (초)
KST = timezone(timedelta(hours=9))

# --- 유틸리티 함수 ---
def get_coin_name(ticker):
    """TICKER에 해당하는 코인 한글 이름을 반환합니다."""
    coin_map = {
        "KRW-BTC": "비트코인",
        "KRW-ETH": "이더리움",
        "KRW-XRP": "리플",
        # 필요시 다른 코인 추가
    }
    return coin_map.get(ticker, ticker)

# --- 데이터베이스 관련 함수 ---

def get_db_connection():
    """가장 최근 DB 파일을 찾아 연결합니다."""
    data_dir = DBConfig.get_db_dir()
    if not data_dir.exists():
        st.error(f"데이터 디렉토리({data_dir})를 찾을 수 없습니다.")
        st.stop()
    
    db_files = sorted(data_dir.glob('trading_history_*.db'), reverse=True)
    if not db_files:
        st.error("trading_history_*.db 파일을 찾을 수 없습니다. 거래 프로그램을 먼저 실행해주세요.")
        st.stop()
    
    return sqlite3.connect(db_files[0], check_same_thread=False)

@st.cache_data(ttl=REFRESH_INTERVAL)
def get_current_ticker():
    """데이터베이스에서 현재 사용 중인 TICKER를 가져옵니다."""
    with get_db_connection() as conn:
        try:
            query = "SELECT DISTINCT ticker FROM grid ORDER BY timestamp DESC LIMIT 1"
            result = pd.read_sql_query(query, conn)
            if not result.empty:
                return result['ticker'].iloc[0]
            
            query = "SELECT DISTINCT ticker FROM trades ORDER BY timestamp DESC LIMIT 1"
            result = pd.read_sql_query(query, conn)
            if not result.empty:
                return result['ticker'].iloc[0]
            
            # TradingConfig에 TICKER가 정의되어 있지 않을 수 있으므로 기본값 설정
            return "KRW-BTC"
        except Exception:
            return "KRW-BTC"

@st.cache_data(ttl=REFRESH_INTERVAL)
def load_data(ticker):
    """모든 필요한 데이터를 한 번에 로드합니다."""
    with get_db_connection() as conn:
        trades_query = "SELECT * FROM trades WHERE ticker = ? ORDER BY timestamp DESC"
        trades_df = pd.read_sql_query(trades_query, conn, params=(ticker,))

        balance_query = "SELECT * FROM balance_history ORDER BY timestamp ASC"
        balance_df = pd.read_sql_query(balance_query, conn)

        grid_query = """
            WITH latest_grid AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY grid_level ORDER BY timestamp DESC) as rn
                FROM grid WHERE ticker = ?
            )
            SELECT * FROM latest_grid WHERE rn = 1 ORDER BY grid_level ASC
        """
        grid_df = pd.read_sql_query(grid_query, conn, params=(ticker,))
        
        return trades_df, balance_df, grid_df

@st.cache_data(ttl=3600) # 시작 시간은 자주 바뀌지 않으므로 캐시 기간을 길게 설정
def get_start_time():
    """봇의 시작 시간을 가져옵니다 (가장 첫 번째 잔고 기록 시간)."""
    with get_db_connection() as conn:
        try:
            query = "SELECT MIN(timestamp) as start_time FROM balance_history"
            result = pd.read_sql_query(query, conn)
            if not result.empty and result['start_time'].iloc[0]:
                return pd.to_datetime(result['start_time'].iloc[0])
        except Exception:
            return None
    return None

def get_total_investment(grid_df):
    """현재 그리드 설정 기준 총 투자 원금을 계산합니다."""
    if not grid_df.empty and 'order_krw_amount' in grid_df.columns:
        order_amount = grid_df['order_krw_amount'].iloc[0]
        num_grids = len(grid_df)
        if pd.notna(order_amount) and order_amount > 0 and num_grids > 0:
            return num_grids * order_amount
    return 0

# --- UI 컴포넌트 및 포맷팅 함수 ---

def format_korean_won(num):
    """숫자를 한글 단위(천, 만, 억)로 변환합니다."""
    if not isinstance(num, (int, float)) or pd.isna(num):
        return ""
    num_abs = abs(int(num))
    if num_abs < 1000:
        return ""
    units = {100000000: "억", 10000: "만", 1000: "천"}
    for unit_val, unit_name in units.items():
        if num_abs >= unit_val:
            val = num_abs / unit_val
            formatted_val = f"{val:.1f}".rstrip('0').rstrip('.')
            return f" ({formatted_val}{unit_name})"
    return ""

def display_bot_status(start_time):
    """봇 운영 상태 (시작 시간, 운영 시간)를 표시합니다."""
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if start_time:
            st.markdown(f"**⏳ 봇 시작 시간:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.markdown("**⏳ 봇 시작 시간:** 정보 없음")
    with col2:
        if start_time:
            uptime = datetime.now(KST) - start_time.replace(tzinfo=KST)
            days, remainder = divmod(uptime.total_seconds(), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            st.markdown(f"**⏱️ 총 운영 시간:** {int(days)}일 {int(hours)}시간 {int(minutes)}분")
        else:
            st.markdown("**⏱️ 총 운영 시간:** 정보 없음")
    st.markdown("---")

def display_kpi_metrics(trades_df, balance_df, grid_df):
    """핵심 성과 지표(KPI)를 5개 컬럼으로 표시합니다."""
    st.subheader("📊 핵심 성과 지표 (KPI)")

    # KPI 계산
    total_profit = trades_df['profit'].sum()
    total_fees = trades_df['fee'].sum()
    total_investment = get_total_investment(grid_df)
    profit_rate = (total_profit / total_investment) * 100 if total_investment > 0 else 0
    
    total_volume = trades_df['amount'].sum()
    fee_rate = (total_fees / total_volume) * 100 if total_volume > 0 else 0

    total_trades = len(trades_df)
    buy_count = len(trades_df[trades_df['buy_sell'] == 'buy'])
    sell_count = len(trades_df[trades_df['buy_sell'] == 'sell'])

    latest_balance = balance_df.iloc[-1] if not balance_df.empty else None

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        profit_color = "normal" if total_profit >= 0 else "inverse"
        st.metric(
            label="💰 총 수익",
            value=f"{total_profit:,.0f} 원",
            delta=f"투자 대비 {profit_rate:+.2f}%",
            delta_color=profit_color
        )

    with col2:
        st.metric(
            label="🧾 총 수수료",
            value=f"{total_fees:,.0f} 원",
            delta=f"거래량 대비 {fee_rate:.4f}%",
            delta_color="off"
        )

    with col3:
        st.metric(
            label="📊 총 거래",
            value=f"{total_trades} 회",
            delta=f"매수 {buy_count} / 매도 {sell_count}"
        )

    with col4:
        if latest_balance is not None:
            st.metric(
                label="🏦 현재 총 자산",
                value=f"{latest_balance['total_assets']:,.0f} 원" + format_korean_won(latest_balance['total_assets']),
            )
        else:
            st.metric("🏦 현재 총 자산", "정보 없음")

    with col5:
        if latest_balance is not None:
            coin_value = latest_balance['coin_balance'] * latest_balance['current_price']
            st.metric(
                label="💎 보유 코인 가치",
                value=f"{coin_value:,.0f} 원" + format_korean_won(coin_value),
            )
        else:
            st.metric("💎 보유 코인 가치", "정보 없음")

def display_grid_status(grid_df, current_price):
    """그리드 현황을 Expander 안에 표시합니다."""
    with st.expander("🔲 그리드 현황 보기", expanded=False):
        if grid_df.empty:
            st.info("현재 활성화된 그리드가 없습니다.")
            return

        grid_display = grid_df.copy()
        grid_display.rename(columns={
            'grid_level': '구간', 'buy_price_target': '매수 목표가', 'sell_price_target': '매도 목표가',
            'order_krw_amount': '주문 금액', 'is_bought': '매수 상태', 'actual_bought_volume': '실제 매수량',
            'actual_buy_fill_price': '평균 매수가', 'timestamp': '최종 업데이트'
        }, inplace=True)

        # 포맷팅
        for col in ['매수 목표가', '매도 목표가', '평균 매수가']:
            grid_display[col] = grid_display[col].apply(lambda x: f"{x:,.2f}" if x > 0 else "-")
        grid_display['주문 금액'] = grid_display['주문 금액'].apply(lambda x: f"{x:,.0f}")
        grid_display['실제 매수량'] = grid_display['실제 매수량'].apply(lambda x: f"{x:.8f}" if x > 0 else "-")
        grid_display['매수 상태'] = grid_display['매수 상태'].apply(lambda x: "✅ 매수완료" if x else "⏳ 대기중")
        grid_display['최종 업데이트'] = pd.to_datetime(grid_display['최종 업데이트']).dt.strftime('%y-%m-%d %H:%M')

        # 현재 가격 강조
        def highlight_current_grid(row):
            style = [''] * len(row)
            try:
                buy_target = float(row['매수 목표가'])
                sell_target = float(row['매도 목표가'])
                if current_price and buy_target < current_price <= sell_target:
                    style = ['background-color: #444444'] * len(row)
            except (ValueError, TypeError):
                pass
            return style
        
        st.dataframe(
            grid_display.style.apply(highlight_current_grid, axis=1),
            use_container_width=True, hide_index=True
        )

def display_trade_history(trades_df):
    """거래 내역을 Expander 안에 표시합니다."""
    with st.expander("🧾 거래 내역 보기", expanded=False):
        if trades_df.empty:
            st.info("거래 내역이 없습니다.")
            return
        
        trades_display = trades_df[['timestamp', 'buy_sell', 'grid_level', 'price', 'amount', 'volume', 'fee', 'profit', 'profit_percentage']].copy()
        trades_display.rename(columns={
            'timestamp': '시간', 'buy_sell': '유형', 'grid_level': '레벨', 'price': '가격',
            'amount': '거래액', 'volume': '수량', 'fee': '수수료', 'profit': '수익', 'profit_percentage': '수익률(%)'
        }, inplace=True)

        trades_display['시간'] = pd.to_datetime(trades_display['시간']).dt.strftime('%y-%m-%d %H:%M')
        trades_display['유형'] = trades_display['유형'].map({'buy': '매수', 'sell': '매도'})
        
        for col in ['가격', '거래액', '수수료', '수익']:
            trades_display[col] = trades_display[col].apply(lambda x: f"{x:,.0f}")
        trades_display['수익률(%)'] = trades_display['수익률(%)'].apply(lambda x: f"{x:+.2f}" if pd.notnull(x) else "-")
        trades_display['수량'] = trades_display['수량'].apply(lambda x: f"{x:.6f}")

        st.dataframe(trades_display, use_container_width=True, hide_index=True, height=300)

# --- 메인 대시보드 ---

def main():
    st.set_page_config(page_title="그리드 트레이딩 대시보드", page_icon="📈", layout="wide")
    st.title("📈 업비트 그리드 트레이딩 대시보드")

    placeholder = st.empty()

    while True:
        with placeholder.container():
            TICKER = get_current_ticker()
            trades_df, balance_df, grid_df = load_data(TICKER)
            
            start_time = get_start_time()
            current_price = balance_df.iloc[-1]['current_price'] if not balance_df.empty else None
            coin_name = get_coin_name(TICKER)

            # 헤더
            price_str = f"{current_price:,.2f} 원" if current_price else "정보 없음"
            st.markdown(f"### **{TICKER}** ({coin_name}) | 현재가: **{price_str}**")
            
            # 봇 상태
            display_bot_status(start_time)

            # KPI
            display_kpi_metrics(trades_df, balance_df, grid_df)
            
            st.markdown("---")

            # 상세 정보
            display_grid_status(grid_df, current_price)
            display_trade_history(trades_df)

        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    main()