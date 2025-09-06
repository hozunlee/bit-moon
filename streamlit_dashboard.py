"""
Streamlit 대시보드 (다중 코인 통합 관리 버전)
"""
import streamlit as st
import pandas as pd
import sqlite3
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# 설정 및 유틸리티 임포트
from config.config import TradingConfig, PathConfig

# --- 전역 설정 ---
REFRESH_INTERVAL = 10  # 자동 새로고침 간격 (초)
KST = timezone(timedelta(hours=9))

# --- 유틸리티 함수 ---
def get_coin_name(ticker: str) -> str:
    """TICKER에 해당하는 코인 한글 이름을 반환합니다."""
    name_map = {"BTC": "비트코인", "ETH": "이더리움", "XRP": "리플"}
    coin_symbol = ticker.replace("KRW-", "")
    return name_map.get(coin_symbol, coin_symbol)

# --- 데이터 로드 함수 ---
@st.cache_data(ttl=60)
def load_data(ticker: str):
    """지정된 티커의 DB에서 모든 데이터를 로드합니다."""
    db_path = PathConfig(ticker).get_db_filename()
    if not db_path.exists():
        return None, None, None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            trades_df = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp DESC", conn)
            balance_df = pd.read_sql_query("SELECT * FROM balance_history ORDER BY timestamp ASC", conn)
            grid_df = pd.read_sql_query("SELECT * FROM grid ORDER BY timestamp DESC", conn) # 최신순으로 정렬
        return trades_df, balance_df, grid_df
    except sqlite3.OperationalError:
        # DB가 잠겨있을 경우 잠시 후 재시도
        time.sleep(0.5)
        return load_data(ticker)


@st.cache_data(ttl=3600)
def get_first_start_time(ticker: str) -> Optional[datetime]:
    """봇의 최초 시작 시간을 DB에서 가져옵니다."""
    _, balance_df, _ = load_data(ticker)
    if balance_df is None or balance_df.empty:
        return None
    try:
        first_time_str = balance_df['timestamp'].iloc[0]
        return pd.to_datetime(first_time_str).tz_localize(KST)
    except Exception:
        return None

@st.cache_data(ttl=60)
def get_session_start_time(ticker: str) -> Optional[datetime]:
    """현재 세션의 시작 시간을 파일에서 읽어옵니다."""
    session_file = PathConfig(ticker).get_session_filename()
    if not session_file.exists(): return None
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            iso_timestamp = f.read().strip()
            # fromisoformat은 시간대 정보가 포함된 문자열을 올바르게 파싱합니다.
            return datetime.fromisoformat(iso_timestamp)
    except Exception:
        return None

# --- UI 컴포넌트 ---
def display_kpi_metrics(trades_df: pd.DataFrame, balance_df: pd.DataFrame, grid_df: pd.DataFrame, ticker: str):
    st.subheader("📊 핵심 성과 지표 (KPI)")
    
    total_profit = trades_df['profit'].sum()
    total_fees = trades_df['fee'].sum()
    invested_capital = grid_df[grid_df['is_bought'] == True]['order_krw_amount'].sum()
    profit_rate = (total_profit / invested_capital) * 100 if invested_capital > 0 else 0
    
    latest_balance = balance_df.iloc[-1] if not balance_df.empty else None

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 총 수익", f"{total_profit:,.0f} 원", f"투자 대비 {profit_rate:+.2f}%", delta_color="normal" if total_profit >= 0 else "inverse")
    with col2:
        st.metric("🧾 총 수수료", f"{total_fees:,.0f} 원")
    with col3:
        st.metric("📊 총 거래", f"{len(trades_df)} 회", f"매수 {len(trades_df[trades_df['buy_sell'] == 'buy'])} / 매도 {len(trades_df[trades_df['buy_sell'] == 'sell'])}")
    with col4:
        if latest_balance is not None:
            total_assets_val = latest_balance['total_assets']
            krw_balance_val = latest_balance['krw_balance']
            coin_balance_val = latest_balance['coin_balance']
            coin_symbol = ticker.replace("KRW-", "")
            
            st.metric(
                label="🏦 현재 총 자산",
                value=f"{total_assets_val:,.0f} 원",
                help=f"현금: {krw_balance_val:,.0f} 원\n코인: {coin_balance_val:.8f} {coin_symbol}"
            )
        else:
            st.metric("🏦 현재 총 자산", "정보 없음")

def display_processed_tables(grid_df: pd.DataFrame, trades_df: pd.DataFrame):
    st.markdown("---")
    
    # --- 그리드 현황 ---
    st.subheader("🔲 그리드 상세 현황")
    if grid_df is None or grid_df.empty:
        st.info("그리드 정보가 없습니다.")
    else:
        # grid_level별로 가장 최신 상태를 정확히 반영하도록 로직 수정
        # 1. 시간순으로 정렬
        grid_df_sorted = grid_df.sort_values('timestamp')
        # 2. grid_level별로 마지막(최신) 데이터만 남김
        latest_grid_df = grid_df_sorted.drop_duplicates(subset='grid_level', keep='last')
        
        grid_display_df = pd.DataFrame({
            "구간": latest_grid_df['grid_level'],
            "상태": latest_grid_df['is_bought'].apply(lambda x: "🟢 매수완료" if x else "⚪ 대기"),
            "매수 목표가": latest_grid_df['buy_price_target'].apply(lambda x: f"{x:,.0f}"),
            "매도 목표가": latest_grid_df['sell_price_target'].apply(lambda x: f"{x:,.0f}"),
            "실제 매수가": latest_grid_df['actual_buy_fill_price'].apply(lambda x: f"{x:,.0f}" if x > 0 else "-"),
            "보유량": latest_grid_df['actual_bought_volume'].apply(lambda x: f"{x:.8f}" if x > 0 else "-"),
            "주문액": latest_grid_df['order_krw_amount'].apply(lambda x: f"{x:,.0f}"),
        }).sort_values(by="구간").set_index("구간")
        st.dataframe(grid_display_df, use_container_width=True)

    # --- 거래 내역 ---
    st.subheader("🧾 최근 거래 내역")
    if trades_df is None or trades_df.empty:
        st.info("거래 내역이 없습니다.")
    else:
        trades_display_df = pd.DataFrame({
            "시간": pd.to_datetime(trades_df['timestamp']).dt.strftime('%m-%d %H:%M:%S'),
            "종류": trades_df['buy_sell'].apply(lambda x: "매수" if x == 'buy' else "매도"),
            "구간": trades_df['grid_level'],
            "체결가": trades_df['price'].apply(lambda x: f"{x:,.0f}"),
            "체결량": trades_df['volume'].apply(lambda x: f"{x:.8f}"),
            "체결액(원)": trades_df['amount'].apply(lambda x: f"{x:,.0f}"),
            "수수료(원)": trades_df['fee'].apply(lambda x: f"{x:,.0f}"),
            "수익(원)": trades_df.apply(lambda row: f"{row['profit']:+,}" if row['buy_sell'] == 'sell' else "-", axis=1),
        }).set_index("시간")
        st.dataframe(trades_display_df.head(15), use_container_width=True)

# --- 신규 분석 섹션 ---
def display_summary_and_analysis(grid_df: pd.DataFrame, trades_df: pd.DataFrame, balance_df: pd.DataFrame):
    st.markdown("---")
    st.subheader("💡 요약 및 기술적 분석")

    if grid_df.empty and trades_df.empty and balance_df.empty:
        st.info("분석할 데이터가 부족합니다.")
        return

    col1, col2 = st.columns(2)

    with col1:
        # --- A. 그리드 요약 ---
        st.markdown("##### A. 그리드 요약")
        if not grid_df.empty:
            latest_grid_df = grid_df.loc[grid_df.groupby('grid_level')['timestamp'].idxmax()]
            total_grids = len(latest_grid_df)
            bought_grids = latest_grid_df['is_bought'].sum()
            waiting_grids = total_grids - bought_grids
            bought_ratio = bought_grids / total_grids if total_grids > 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("총 그리드", f"{total_grids} 개")
            c2.metric("🟢 보유", f"{bought_grids} 개")
            c3.metric("⚪ 대기", f"{waiting_grids} 개")
            st.progress(bought_ratio, text=f"자본 투입률: {bought_ratio:.1%}")
        else:
            st.info("그리드 데이터가 없습니다.")

        # --- C. 시장 동향 기술적 분석 ---
        st.markdown("##### C. 시장 동향 기술적 분석")
        if not balance_df.empty and len(balance_df) > 10: # 최소 데이터 포인트 확보
            balance_df['timestamp'] = pd.to_datetime(balance_df['timestamp'])
            now = pd.Timestamp.now(tz=KST)
            
            # 최근 1시간, 6시간 데이터 필터링
            recent_1h = balance_df[balance_df['timestamp'] >= now - timedelta(hours=1)]
            recent_6h = balance_df[balance_df['timestamp'] >= now - timedelta(hours=6)]

            if not recent_1h.empty and not recent_6h.empty:
                short_sma = recent_1h['current_price'].mean()
                long_sma = recent_6h['current_price'].mean()
                volatility = recent_1h['current_price'].std()

                trend = "횡보 (낮은 변동성)"
                if short_sma > long_sma * 1.01:
                    trend = "📈 상승 추세"
                elif short_sma < long_sma * 0.99:
                    trend = "📉 하락 추세"
                elif volatility > short_sma * 0.01: # 변동성이 평균 가격의 1% 이상이면
                    trend = "횡보 (높은 변동성)"
                
                st.metric("현재 시장 동향", trend, help="단기(1h) 및 장기(6h) 이동평균선과 변동성을 기반으로 분석됩니다.")
            else:
                st.info("추세 분석을 위한 데이터가 부족합니다.")
        else:
            st.info("가격 기록이 부족하여 추세를 분석할 수 없습니다.")

    with col2:
        # --- B. 최근 거래 동향 ---
        st.markdown("##### B. 최근 거래 동향 (지난 24시간)")
        if not trades_df.empty:
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            now = pd.Timestamp.now(tz=KST).tz_localize(None)
            recent_trades = trades_df[trades_df['timestamp'] >= now - timedelta(hours=24)]

            if not recent_trades.empty:
                buy_trades = recent_trades[recent_trades['buy_sell'] == 'buy']['amount'].sum()
                sell_trades = recent_trades[recent_trades['buy_sell'] == 'sell']['amount'].sum()

                st.text(f"총 매수액: {buy_trades:,.0f} 원")
                st.text(f"총 매도액: {sell_trades:,.0f} 원")

                # 시각화를 위한 데이터프레임 생성
                flow_data = pd.DataFrame({
                    "거래 종류": ["매수", "매도"],
                    "체결액 (원)": [buy_trades, sell_trades]
                }).set_index("거래 종류")
                
                st.bar_chart(flow_data, color=["#3388ff", "#ff3344"]) # 파란색, 빨간색
            else:
                st.info("지난 24시간 동안 거래가 없습니다.")
        else:
            st.info("거래 데이터가 없습니다.")

def display_footer_status(first_start_time: Optional[datetime], session_start_time: Optional[datetime]):
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    
    def format_uptime(start_dt: Optional[datetime]) -> str:
        if not start_dt: return "정보 없음"
        uptime = datetime.now(KST) - start_dt
        days, rem = divmod(uptime.total_seconds(), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        return f"{int(days)}일 {int(hours)}시간 {int(minutes)}분"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"**🌱 최초 시작**")
        st.code(f"{first_start_time.strftime('%Y-%m-%d %H:%M') if first_start_time else 'N/A'}")
    with col2:
        st.markdown(f"**📈 총 누적 운영**")
        st.code(f"{format_uptime(first_start_time)}")
    with col3:
        st.markdown(f"**🔄 현 세션 시작**")
        st.code(f"{session_start_time.strftime('%Y-%m-%d %H:%M') if session_start_time else 'N/A'}")
    with col4:
        st.markdown(f"**⏳ 현 세션 운영**")
        st.code(f"{format_uptime(session_start_time)}")

# --- 메인 대시보드 실행 ---
def main(ticker: str):
    st.set_page_config(page_title=f"{ticker} 트레이딩 대시보드", page_icon="📈", layout="wide")
    coin_name = get_coin_name(ticker)
    st.title(f"📈 {ticker} ({coin_name}) 트레이딩 대시보드")

    placeholder = st.empty()

    while True:
        with placeholder.container():
            trades_df, balance_df, grid_df = load_data(ticker)
            
            if balance_df is None or balance_df.empty:
                st.warning(f"{ticker}에 대한 데이터가 없습니다. 봇이 실행 중인지 확인하세요.")
                time.sleep(REFRESH_INTERVAL)
                continue

            current_price = balance_df.iloc[-1]['current_price']
            price_str = f"{current_price:,.2f} 원" if current_price else "정보 없음"
            st.markdown(f"#### 현재가: **{price_str}** (업데이트: {datetime.now(KST).strftime('%H:%M:%S')})")
            
            display_kpi_metrics(trades_df, balance_df, grid_df, ticker)
            display_processed_tables(grid_df, trades_df)
            display_summary_and_analysis(grid_df, trades_df, balance_df)

            first_start_time = get_first_start_time(ticker)
            session_start_time = get_session_start_time(ticker)
            display_footer_status(first_start_time, session_start_time)

        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upbit 그리드 트레이딩 대시보드")
    parser.add_argument("--ticker", type=str, help="표시할 코인 티커 (예: KRW-BTC)", required=True)
    args = parser.parse_args()
    main(args.ticker)
