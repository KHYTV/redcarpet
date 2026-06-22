#!/usr/bin/env bash
# RedCarpet 실행 스크립트 (cron용)
set -euo pipefail

# 스크립트 위치 기준으로 프로젝트 루트 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 활성화 (없으면 생성)
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

# 의존성 설치
pip install -q -r requirements.txt

# 로그 디렉토리 보장
mkdir -p logs

# 실행 (표준 출력/에러를 날짜별 로그로도 보존)
TS="$(date +%Y%m%d)"
python main.py >> "logs/run_${TS}.log" 2>&1

deactivate
