FROM python:3.12-slim AS builder

# 빌드 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 복사 및 의존성 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-slim AS production

# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


# 빌더 스테이지에서 설치된 패키지 복사
COPY --from=builder /root/.local /root/.local

# 작업 디렉토리 설정
WORKDIR /app

# 데이터 및 로그 디렉토리 생성
RUN mkdir -p /app/data /app/logs

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:$PATH

# 애플리케이션 코드 복사
COPY product_app.py .
COPY streamlit_dashboard.py .
# COPY test.py .
# COPY dash.py .
COPY start.sh .
COPY ./config/ /app/config/

# 포트 노출
EXPOSE 8080
EXPOSE 8501

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/_stcore/health || exit 1

# 애플리케이션 실행
# CMD ["python", "product_app.py"]
# CMD ["python", "test.py"]
CMD ["/app/start.sh"]
