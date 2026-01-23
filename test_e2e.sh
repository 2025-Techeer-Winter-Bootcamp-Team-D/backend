#!/bin/bash

# E2E 테스트 실행 스크립트
# 사용법: ./test_e2e.sh [ADMIN_TOKEN]

# 관리자 토큰 (필수)
ADMIN_TOKEN=${1:-""}

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ 오류: 관리자 토큰이 필요합니다."
    echo "사용법: ./test_e2e.sh <ADMIN_TOKEN>"
    exit 1
fi

# API 서버 URL
API_URL="http://localhost:8000/api/companies/test/e2e/"

echo "=========================================="
echo "E2E 테스트 실행"
echo "=========================================="
echo ""

# 테스트 실행 옵션 선택
echo "테스트 실행 옵션을 선택하세요:"
echo "1. 전체 Phase 실행 (Gemini 사용)"
echo "2. 전체 Phase 실행 (Gemini 스킵)"
echo "3. Phase 1, 2, 3만 실행 (Gemini 최소 사용)"
echo "4. Phase 1만 실행 (인프라 검증)"
echo ""
read -p "선택 (1-4): " choice

case $choice in
    1)
        echo "전체 Phase 실행 (Gemini 사용)..."
        PAYLOAD='{"phases": [1, 2, 3, 4], "skip_gemini": false}'
        ;;
    2)
        echo "전체 Phase 실행 (Gemini 스킵)..."
        PAYLOAD='{"phases": [1, 2, 3, 4], "skip_gemini": true}'
        ;;
    3)
        echo "Phase 1, 2, 3만 실행 (Gemini 최소 사용)..."
        PAYLOAD='{"phases": [1, 2, 3], "skip_gemini": false}'
        ;;
    4)
        echo "Phase 1만 실행 (인프라 검증)..."
        PAYLOAD='{"phases": [1], "skip_gemini": true}'
        ;;
    *)
        echo "❌ 잘못된 선택입니다."
        exit 1
        ;;
esac

echo ""
echo "API 호출 중..."
echo ""

# API 호출
curl -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d "$PAYLOAD" \
    | python3 -m json.tool

echo ""
echo "=========================================="
echo "E2E 테스트 완료"
echo "=========================================="
