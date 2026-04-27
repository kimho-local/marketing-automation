#!/bin/bash
# Re:NK META 광고 일일 자동화 실행 (Mac/Linux)
echo "===================================================="
echo "  Re:NK META 광고 일일 자동화 실행"
echo "===================================================="
echo ""

# 스크립트 위치로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Python 설치 확인
if ! command -v python3 &> /dev/null; then
    echo "[오류] Python3가 설치되지 않았습니다."
    echo "  brew install python  또는 https://www.python.org 에서 설치하세요."
    exit 1
fi

echo "[실행] 어제 Meta 광고 데이터 수집 및 리포트 기입 시작..."
echo ""

python3 run_daily.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[실패] 오류가 발생했습니다. 위 메시지를 확인하세요."
    exit 1
fi

echo ""
echo "[완료] 정상적으로 처리되었습니다."
