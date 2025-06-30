# Bit-Moon Crypto Trading System

## 소개

-   업비트 API 기반의 자동화 암호화폐 트레이딩 봇 및 Streamlit 대시보드 프로젝트입니다.
-   Docker + docker-compose로 개발/운영 환경을 통일합니다.

## 폴더 구조

```
bit-moon/
├── config/                # 설정 파일
├── data/                  # 거래 기록 DB (git 미포함)
├── logs/                  # 로그 파일 (git 미포함)
├── product_app.py         # 거래 봇 메인 코드
├── streamlit_dashboard.py # 대시보드
├── start.sh               # 컨테이너 진입점
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                   # 환경변수 (git 미포함)
└── .gitignore
```

## 빠른 시작 (로컬)

```bash
# 1. 환경 변수 파일 작성
cp .env.example .env  # 또는 직접 .env 작성

# 2. 필수 폴더 생성
mkdir -p data logs config

# 3. Docker 빌드 및 실행
docker compose up --build -d

# 4. 대시보드 접속
# http://localhost:8080 또는 http://localhost:8501
```

## 배포 (AWS EC2 Ubuntu 예시)

1. 서버에 git clone
2. .env, data, logs, config 폴더 준비
3. Docker, docker-compose 설치
4. `docker compose up --build -d`
5. 보안그룹 및 방화벽 오픈(8080, 8501 등)

## 환경 변수 예시 (.env)

```
UPBIT_ACCESS_KEY=your-access-key
UPBIT_SECRET_KEY=your-secret-key
```

## 주의사항

-   `.env`, `data/`, `logs/` 등 민감정보/실시간 데이터는 git에 절대 올리지 마세요.
-   PR, 이슈, 배포 등은 반드시 코드리뷰 후 진행 바랍니다.

## 라이선스

-   MIT License (필요시 명시)
