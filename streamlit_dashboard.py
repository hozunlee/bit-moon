"""
Streamlit 대시보드 (기능 업그레이드 버전)
- 코인별 ON/OFF, 예산 설정 기능 추가
- DB 직접 제어 UI 구현
- 사용자 입력 유효성 검사 및 확인 절차 추가
"""
import streamlit as st
import pandas as pd
import time
import os
import sqlite3
from datetime import datetime, timezone, timedelta

# --- 모듈 임포트 ---
from config.config import TradingConfig, DBConfig, TestConfig
import db_handler as db # handle_config_update에서 pg 용으로 사용

# --- 전역 설정 ---
REFRESH_INTERVAL = 10
APP_MODE = os.environ.get("APP_MODE", "PRODUCTION")

st.set_page_config(page_title="Bit-Moon 트레이딩 대시보드", layout="wide")

# --- 세션 상태 초기화 ---
if 'confirming_action' not in st.session_state:
    st.session_state.confirming_action = None
if 'action_params' not in st.session_state:
    st.session_state.action_params = {}

# --- DB 연결 헬퍼 ---
def get_dashboard_db_connection():
    """대시보드 모드에 맞는 DB 커넥션을 반환"""
    if APP_MODE == "TEST":
        db_path = TestConfig.get_test_db_dir() / "test_mode.db"
        return sqlite3.connect(db_path)
    else:
        # 운영 모드에서는 db_handler의 연결 풀 사용
        return db.get_connection()

def put_dashboard_db_connection(conn):
    if APP_MODE != "TEST":
        db.put_connection(conn)
    else:
        conn.close()

# --- 데이터 로드 함수 ---
@st.cache_data(ttl=REFRESH_INTERVAL)
def load_data(ticker: str):
    """지정된 티커에 대한 모든 데이터를 DB에서 로드합니다."""
    conn = get_dashboard_db_connection()
    try:
        trades_df = pd.read_sql_query(f"SELECT * FROM trades WHERE ticker = '{ticker}' ORDER BY timestamp DESC", conn)
        balance_df = pd.read_sql_query(f"SELECT * FROM balance_history WHERE ticker = '{ticker}' ORDER BY timestamp ASC", conn)
        grid_df = pd.read_sql_query(f"SELECT * FROM grid WHERE ticker = '{ticker}' ORDER BY grid_level ASC", conn)
        config_df = pd.read_sql_query(f"SELECT * FROM coin_config WHERE ticker = '{ticker}'", conn)
        
        return trades_df, balance_df, grid_df, config_df.iloc[0] if not config_df.empty else None
    finally:
        put_dashboard_db_connection(conn)

@st.cache_data(ttl=REFRESH_INTERVAL)
def get_invested_capital(ticker: str):
    """현재 투자된 자본(매수된 그리드의 총합)을 계산합니다."""
    conn = get_dashboard_db_connection()
    try:
        sql = "SELECT COALESCE(SUM(order_krw_amount), 0) AS total FROM grid WHERE ticker = ? AND is_bought = ?"
        is_bought_param = 1 if APP_MODE == "TEST" else True
        
        cursor = conn.cursor()
        cursor.execute(sql, (ticker, is_bought_param))
        result = cursor.fetchone()
        return result[0] if result else 0
    finally:
        put_dashboard_db_connection(conn)

# --- UI 핸들러 ---
def handle_config_update(ticker, key, value):
    """DB의 코인 설정을 업데이트합니다."""
    if key not in ['is_active', 'budget_krw']:
        st.error("잘못된 설정 키입니다.")
        return
    
    if APP_MODE == "TEST":
        conn = get_dashboard_db_connection()
        try:
            val = 1 if value is True else (0 if value is False else value)
            sql = f"UPDATE coin_config SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE ticker = ?"
            conn.execute(sql, (val, ticker))
            conn.commit()
        finally:
            put_dashboard_db_connection(conn)
    else:
        sql = f"UPDATE coin_config SET {key} = %s, updated_at = CURRENT_TIMESTAMP WHERE ticker = %s"
        db.execute(sql, (value, ticker))

    st.cache_data.clear()
    st.success(f"{ticker}의 {key} 설정이 업데이트되었습니다. 잠시 후 반영됩니다.")
    # 확인 상태 초기화
    st.session_state.confirming_action = None
    st.session_state.action_params = {}
    time.sleep(1) # UI가 다시 그려질 시간을 줌
    st.rerun()


def render_confirmation_dialog():
    """확인 다이얼로그를 렌더링합니다."""
    action = st.session_state.confirming_action
    params = st.session_state.action_params

    if action == 'toggle_active':
        ticker = params['ticker']
        new_value = params['value']
        status_text = "활성화" if new_value else "비활성화"
        st.warning(f"정말로 {ticker}의 거래를 **{status_text}** 하시겠습니까?")
        
        col1, col2 = st.columns(2)
        if col1.button("예, 변경합니다.", key="confirm_yes"):
            handle_config_update(ticker, 'is_active', new_value)
        if col2.button("아니오, 취소합니다.", key="confirm_no"):
            st.session_state.confirming_action = None
            st.session_state.action_params = {}
            st.rerun()

    elif action == 'update_budget':
        ticker = params['ticker']
        new_value = params['value']
        st.warning(f"{ticker}의 할당 예산을 **{new_value:,.0f}원**으로 변경하시겠습니까?")

        col1, col2 = st.columns(2)
        if col1.button("예, 변경합니다.", key="confirm_yes"):
            handle_config_update(ticker, 'budget_krw', new_value)
        if col2.button("아니오, 취소합니다.", key="confirm_no"):
            st.session_state.confirming_action = None
            st.session_state.action_params = {}
            st.rerun()

# --- 메인 대시보드 ---
def main():
    with st.sidebar:
        st.title("📈 Bit-Moon")
        
        available_tickers = [coin['TICKER'] for coin in TradingConfig.COIN_LIST]
        selected_ticker = st.selectbox("코인 선택", options=available_tickers)
        
        st.markdown("---")

        trades_df, balance_df, grid_df, coin_config = load_data(selected_ticker)

        st.subheader(f"{selected_ticker} 제어판")
        if coin_config is not None:
            # 확인 다이얼로그가 활성화된 경우, 다른 컨트롤 비활성화
            is_confirming = st.session_state.confirming_action is not None

            # 거래 활성화 토글
            is_active_now = bool(coin_config['is_active'])
            new_is_active = st.toggle(
                "거래 활성화", 
                value=is_active_now, 
                key=f"active_{selected_ticker}",
                disabled=is_confirming
            )
            if new_is_active != is_active_now and not is_confirming:
                st.session_state.confirming_action = 'toggle_active'
                st.session_state.action_params = {'ticker': selected_ticker, 'value': new_is_active}
                st.rerun()

            # 예산 설정
            budget_now = float(coin_config['budget_krw'])
            new_budget = st.number_input(
                "할당 예산 (원)", 
                value=budget_now, 
                min_value=0.0, 
                step=50000.0, 
                key=f"budget_{selected_ticker}",
                format="%.0f",
                disabled=is_confirming
            )
            if new_budget != budget_now and not is_confirming:
                if new_budget <= 0:
                    st.error("할당 예산은 0보다 커야 합니다.")
                else:
                    st.session_state.confirming_action = 'update_budget'
                    st.session_state.action_params = {'ticker': selected_ticker, 'value': new_budget}
                    st.rerun()
            
            # 확인 다이얼로그 렌더링
            if is_confirming:
                render_confirmation_dialog()

        else:
            st.warning("설정 정보를 불러올 수 없습니다.")

        st.markdown("---")
        auto_refresh = st.toggle("자동 새로고침 (10초)", value=True)
        if 'last_update' not in st.session_state:
            st.session_state.last_update = "N/A"
        st.info(f"마지막 업데이트: {st.session_state.last_update}")

    # --- 메인 콘텐츠 ---
    st.header(f"{selected_ticker} 대시보드")

    if balance_df.empty:
        st.warning("선택한 코인에 대한 데이터가 없습니다. 거래 봇이 실행 중인지 확인하세요.")
        st.stop()

    latest_balance = balance_df.iloc[-1]
    total_profit = trades_df['profit'].sum()
    invested_capital = get_invested_capital(selected_ticker)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("현재 총 자산", f"{latest_balance['total_assets']:,.0f}원")
    col2.metric("총 실현 수익", f"{total_profit:,.0f}원")
    col3.metric("현재 투입된 자본", f"{invested_capital:,.0f}원")
    
    if coin_config is not None and coin_config['budget_krw'] > 0:
        budget = coin_config['budget_krw']
        usage_percent = min(int((invested_capital / budget) * 100), 100)
        col4.metric("예산 사용률", f"{usage_percent}%")
        st.progress(usage_percent / 100, text=f"{invested_capital:,.0f} / {budget:,.0f} 원")
    else:
        col4.metric("예산 사용률", "N/A")

    st.markdown("---")
    
    col_grid, col_trades = st.columns(2)
    with col_grid:
        st.subheader("그리드 현황")
        st.dataframe(grid_df, use_container_width=True, hide_index=True)

    with col_trades:
        st.subheader("최근 거래 내역")
        st.dataframe(trades_df.head(15), use_container_width=True, hide_index=True)

    if auto_refresh and not st.session_state.confirming_action:
        time.sleep(REFRESH_INTERVAL)
        st.session_state.last_update = datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S')
        st.rerun()

if __name__ == "__main__":
    if APP_MODE == "PRODUCTION":
        db.init_db(DBConfig)
    main()