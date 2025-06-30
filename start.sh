#!/bin/sh

# 1. 거래 봇(app.py)을 백그라운드에서 실행합니다.
# '&' 기호는 프로세스를 백그라운드로 보내고 바로 다음 명령어를 실행하라는 의미입니다.
echo "Starting Trading Bot..."
python /app/product_app.py & 

# 2. Streamlit 대시보드를 포그라운드에서 실행합니다.
# 컨테이너의 메인 프로세스가 되며, 이 프로세스가 살아있는 동안 컨테이너가 유지됩니다.
echo "Starting Streamlit Dashboard..."
streamlit run /app/streamlit_dashboard.py --server.port 8501 --server.address 0.0.0.0