"""
거래 봇 설정 파일 (다중 코인 통합 관리 버전)
"""
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# --- API 키 설정 ---
class APIConfig:
    """API 관련 설정. 실제 키 값은 .env 파일에서 로드됩니다."""
    ACCESS_KEY: str = os.environ.get("UPBIT_ACCESS_KEY", "")
    SECRET_KEY: str = os.environ.get("UPBIT_SECRET_KEY", "")
    DISCORD_WEBHOOK_URL: Optional[str] = os.environ.get("DISCORD_WEBHOOK_URL")

# --- 거래 설정 ---
class TradingConfig:
    """
    거래 관련 공통 설정 및 코인별 개별 설정을 관리합니다.
    새로운 코인을 추가하려면 COIN_LIST에 설정을 추가하기만 하면 됩니다.
    """
    # 거래할 모든 코인의 설정을 중앙에서 관리
    COIN_LIST: List[Dict[str, Any]] = [
        {
            "TICKER": "KRW-BTC",
            "BASE_PRICE": 170000000,      # 그리드 기준 가격
            "PRICE_CHANGE": 550000.0,     # 그리드 간 가격 간격
            "MAX_GRID_COUNT": 20,         # 그리드 수
            "ORDER_AMOUNT": 450000,        # 주문당 금액
        },
        {
            "TICKER": "KRW-ETH",
            "BASE_PRICE": 6300000,
            # "PRICE_CHANGE": 118220.0,
            "GRID_INTERVAL_PERCENT": 1.2,   # 기준가 대비 0.5% 간격으로 동적 설정
            "MAX_GRID_COUNT": 20,
            "ORDER_AMOUNT": 300000,
        }
        # 예시: 리플(XRP)을 추가하고 싶다면 아래 주석을 해제하고 값을 설정하세요.
        # {
        #     "TICKER": "KRW-XRP",
        #     "BASE_PRICE": 700,
        #     "PRICE_CHANGE": 5.0,
        #     "MAX_GRID_COUNT": 30,
        #     "ORDER_AMOUNT": 10000,
        # }
    ]
    
    # 모든 코인 봇에 공통으로 적용될 설정
    CHECK_INTERVAL: int = 10      # 가격 체크 간격 (초)
    FEE_RATE: float = 0.0005      # 거래 수수료 (0.05%)
    DISCORD_LOGGING: bool = True  # 디스코드 로깅 사용 여부
    PLAY_SOUND: bool = False       # 거래 알림음 재생 여부 (Windows에서만 지원)

    @staticmethod
    def get_coin_config(ticker: str) -> Optional[Dict[str, Any]]:
        """
        주어진 티커에 해당하는 코인 설정을 COIN_LIST에서 찾아 반환합니다.
        
        Args:
            ticker (str): 찾고자 하는 코인의 티커 (예: "KRW-BTC")
        
        Returns:
            Optional[Dict[str, Any]]: 해당 티커의 설정 사전 또는 찾지 못한 경우 None
        """
        for coin_config in TradingConfig.COIN_LIST:
            if coin_config.get("TICKER") == ticker:
                return coin_config
        return None

# --- 경로 설정 ---
class PathConfig:
    """
    티커별로 로그 및 데이터베이스 파일 경로를 관리합니다.
    이를 통해 각 코인의 데이터가 독립적으로 저장됩니다.
    """
    def __init__(self, ticker: str):
        self.ticker_id = ticker.replace('KRW-', '').lower()
        self.base_dir = Path(__file__).parent.parent
        
        # 데이터 디렉토리 설정 (예: /data/btc/)
        self.data_dir = self.base_dir / 'data' / self.ticker_id
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 로그 디렉토리 설정 (예: /logs/btc/)
        self.logs_dir = self.base_dir / 'logs' / self.ticker_id
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_db_filename(self) -> Path:
        """코인별 데이터베이스 파일 경로를 반환합니다. (예: .../data/btc/trading.db)"""
        return self.data_dir / "trading.db"

    def get_log_filename(self) -> Path:
        """코인별 로그 파일 경로를 반환합니다. (예: .../logs/btc/trade.log)"""
        return self.logs_dir / "trade.log"

    def get_session_filename(self) -> Path:
        """코인별 세션 시작 시간 파일 경로를 반환합니다. (예: .../data/btc/session.log)"""
        return self.data_dir / "session.log"
    
    
    # 데이터베이스 설정
class DBConfig:
    """데이터베이스 관련 설정"""
    # 디렉토리 및 파일 설정
    DB_DIR: Path = Path(__file__).parent.parent / 'data'
    DB_PREFIX: str = "trading_history"
    DB_EXTENSION: str = "db"

    @classmethod
    def get_db_dir(cls) -> Path:
        """
        Returns the data directory as a Path object, creating it if necessary.
        """
        cls.DB_DIR.mkdir(parents=True, exist_ok=True)
        return cls.DB_DIR

    @classmethod
    def get_db_filename(cls) -> Path:
        """
        Returns a Path object for a new DB file, based on the current date and time.
        """
        db_dir = cls.get_db_dir()
        timestamp = datetime.now().strftime('%Y%m%d%H%M')
        filename = f"{cls.DB_PREFIX}_{timestamp}.{cls.DB_EXTENSION}"
        return db_dir / filename