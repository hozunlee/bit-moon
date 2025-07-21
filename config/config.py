"""
거래 봇 설정 파일
환경변수와 거래 관련 설정값을 관리합니다.
"""
import os
from typing import Optional
from datetime import datetime
from pathlib import Path
# from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
# load_dotenv()

# API 키 설정
class APIConfig:
    """API 관련 설정"""
    ACCESS_KEY: str = os.environ.get("UPBIT_ACCESS_KEY", "")
    SECRET_KEY: str = os.environ.get("UPBIT_SECRET_KEY", "")
    DISCORD_WEBHOOK_URL: Optional[str] = os.environ.get("DISCORD_WEBHOOK_URL")

# 기존 리플 설정 
# # 거래 설정
# class TradingConfig:
#     """거래 관련 설정"""
#     # 기본 코인 설정
#     TICKER: str = "KRW-XRP"  # 거래할 코인 (티커 형식)
    
#     # 그리드 거래 설정
#     BASE_PRICE: Optional[float] = 3200.0  # 기준 가격 (None이면 현재가로 자동 설정)
#     PRICE_CHANGE: float = 20.0  # 그리드 간 가격 차이 (원)
#     MAX_GRID_COUNT: int = 50  # 최대 그리드 수 (1~100)
#     ORDER_AMOUNT: float = 30000.0  # 주문당 금액 (원, 최소 5,000원)
    
#     # 실행 설정
#     CHECK_INTERVAL: int = 10  # 가격 체크 간격 (초)
#     FEE_RATE: float = 0.0005  # 거래 수수료 (0.05%)
    


# 거래 설정
class TradingConfig:
    """거래 관련 설정"""
    # 기본 코인 설정
    TICKER: str = "KRW-BTC"   # 거래할 코인 (티커 형식)
    
    # 그리드 거래 설정
    BASE_PRICE: Optional[float] = 166800000 # 기준 가격 (None이면 현재가로 자동 설정)
    PRICE_CHANGE: float = 20.0  # 그리드 간 가격 차이 (원)
    MAX_GRID_COUNT: int = 50  # 최대 그리드 수 (1~100)
    ORDER_AMOUNT: float = 5000 # 주문당 금액 (원, 최소 5,000원)
    
    # 실행 설정
    CHECK_INTERVAL: int = 10  # 가격 체크 간격 (초)
    FEE_RATE: float = 0.0005  # 거래 수수료 (0.05%)
        
    # 기능 설정
    DISCORD_LOGGING: bool = False  # 디스코드 로깅 사용 여부
    PLAY_SOUND: bool = True  # 소리 알림 사용 여부

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


# 테스트 설정
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
