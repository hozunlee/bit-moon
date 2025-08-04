"""
거래 봇 설정 파일
환경변수와 거래 관련 설정값을 관리합니다.
"""
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

# 애플리케이션 모드 설정
APP_MODE = os.environ.get("APP_MODE", "PRODUCTION")

# API 키 설정
class APIConfig:
    """API 관련 설정"""
    ACCESS_KEY: str = os.environ.get("UPBIT_ACCESS_KEY", "")
    SECRET_KEY: str = os.environ.get("UPBIT_SECRET_KEY", "")
    DISCORD_WEBHOOK_URL: Optional[str] = os.environ.get("DISCORD_WEBHOOK_URL")

# 데이터베이스 설정
class DBConfig:
    """데이터베이스 연결 설정"""
    DB_USER: str = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: str = os.environ.get("DB_PORT", "5432")
    DB_NAME: str = os.environ.get("DB_NAME", "trading_db")

    @classmethod
    def get_db_url(cls) -> str:
        """PostgreSQL 연결 URL 생성"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

# 거래 설정
class TradingConfig:
    """거래 관련 설정"""
    # 거래할 코인 목록
    COIN_LIST: List[Dict[str, Any]] = [
        {
            "TICKER": "KRW-BTC",
            "BASE_PRICE": 166800000,
            "PRICE_CHANGE": 513350.0,
            "MAX_GRID_COUNT": 20,
            "ORDER_AMOUNT": 250000,
        },
        {
            "TICKER": "KRW-ETH",
            "BASE_PRICE": 4500000,
            "PRICE_CHANGE": 22500.0, # 0.5%
            "MAX_GRID_COUNT": 20,
            "ORDER_AMOUNT": 50000,
        }
    ]
    
    # 공통 실행 설정
    CHECK_INTERVAL: int = 10  # 가격 체크 간격 (초)
    FEE_RATE: float = 0.0005  # 거래 수수료 (0.05%)
    DISCORD_LOGGING: bool = False  # 디스코드 로깅 사용 여부
    PLAY_SOUND: bool = True  # 소리 알림 사용 여부

# 데이터베이스 및 로그 경로 설정
class PathConfig:
    """데이터 및 로그 경로 설정"""
    def __init__(self, ticker: str):
        # 티커에서 'KRW-'를 제거하고 소문자로 만들어 폴더 이름으로 사용 (예: btc, eth)
        self.ticker_id = ticker.replace('KRW-', '').lower()
        
        # 기본 로그 디렉토리 경로 설정
        base_dir = Path(__file__).parent.parent
        self.base_logs_dir = base_dir / 'logs'
        
        # 코인별 로그 디렉토리 경로 정의
        self.coin_logs_dir: Path = self.base_logs_dir / self.ticker_id
        
        # 디렉토리가 존재하지 않으면 생성
        self.coin_logs_dir.mkdir(parents=True, exist_ok=True)

    def get_log_filename(self) -> Path:
        """코인별 로그 파일 경로를 생성"""
        filename = f"{self.ticker_id}_grid_trade.log"
        return self.coin_logs_dir / filename

# 테스트 설정 (변경 없음)
class TestConfig:
    """테스트 관련 설정"""
    # 테스트 데이터 디렉토리 설정
    TEST_DIR: Path = Path(__file__).parent.parent / 'data'
    TEST_DB_PREFIX: str = "test_trading_history"
    TEST_DB_EXTENSION: str = "db"

    @classmethod
    def get_test_db_dir(cls) -> Path:
        cls.TEST_DIR.mkdir(parents=True, exist_ok=True)
        return cls.TEST_DIR

    @classmethod
    def get_test_db_filename(cls) -> Path:
        """테스트용 DB 파일 경로 생성"""
        test_dir = cls.get_test_db_dir()
        timestamp = datetime.now().strftime('%Y%m%d%H%M')
        filename = f"{cls.TEST_DB_PREFIX}_{timestamp}.{cls.TEST_DB_EXTENSION}"
        return test_dir / filename
        # 테스트 데이터 디렉토리가 없으면 생성
        os.makedirs(cls.TEST_DIR, exist_ok=True)
        
        # 파일명 생성
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{cls.TEST_DB_PREFIX}_{timestamp}.{cls.TEST_DB_EXTENSION}"
        
        # 전체 경로 반환
        return os.path.join(cls.TEST_DIR, filename)
