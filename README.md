# Bit-Moon Crypto Trading System

## 소개

-   업비트 API 기반의 자동화 암호화폐 트레이딩 봇 및 Streamlit 대시보드 프로젝트입니다.
-   Docker + docker-compose로 개발/운영 환경을 통일합니다.

## Nginx 리버스 프록시 도입

-   **배경**: BTC와 ETH 대시보드를 동시에 운영하기 위해 `8501`, `8502` 등 여러 포트를 외부에 노출했습니다. AWS의 Public IPv4 주소 정책 변경으로 인해, 여러 포트를 사용하는 것이 복수의 IP를 사용하는 것으로 간주되어 프리 티어를 초과하는 불필요한 과금이 발생했습니다.
-   **해결**: Nginx를 리버스 프록시로 도입하여 모든 외부 요청을 단일 포트(80)에서 받도록 아키텍처를 개선했습니다.
-   **주요 이점**:
    -   **비용 절감**: Public IP를 1개만 사용하게 되어 AWS 과금 문제를 해결했습니다.
    -   **URL 단순화**: 포트 번호 대신 `http://<서버IP>/btc/`, `http://<서버IP>/eth/` 와 같은 직관적인 경로로 각 대시보드에 접근합니다.
    -   **보안 강화**: 대시보드 컨테이너가 더 이상 인터넷에 직접 노출되지 않고 Nginx를 통해서만 접근 가능합니다.

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
├── nginx.conf             # Nginx 리버스 프록시 설정
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
# BTC 대시보드: http://localhost/btc/
# ETH 대시보드: http://localhost/eth/
```

## 배포 (AWS EC2 Ubuntu 예시)

1. 서버에 git clone
2. .env, data, logs, config 폴더 준비
3. Docker, docker-compose 설치
4. `docker compose up --build -d`
5. 보안그룹에서 80번 포트(HTTP)만 오픈합니다.

## 환경 변수 예시 (.env)

```
UPBIT_ACCESS_KEY=your-access-key
UPBIT_SECRET_KEY=your-secret-key
```

## 주의사항

-   `.env`, `data/`, `logs/` 등 민감정보/실시간 데이터는 git에 절대 올리지 마세요.
-   PR, 이슈, 배포 등은 반드시 코드리뷰 후 진행 바랍니다.

## Changelog

-   **2025-09-06**: Nginx 리버스 프록시 도입
    -   AWS Public IPv4 과금 문제 해결을 위해 아키텍처 변경.
    -   `docker-compose.yml`에 nginx 서비스 추가 및 대시보드 포트 외부 노출 제거.
    -   URL 경로 기반 라우팅 적용 (`/btc/`, `/eth/`).

## 라이선스

-   MIT License (필요시 명시)
