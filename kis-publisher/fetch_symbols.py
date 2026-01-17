"""
상장 기업 종목 코드 목록을 가져오는 모듈

KRX 정보데이터시스템에서 상장 종목 목록을 다운로드하거나,
DART API를 통해 상장 기업 목록을 가져올 수 있습니다.
또는 PostgreSQL DB에서 Company 테이블의 stock_code를 가져올 수 있습니다.
"""

import os
import csv
import aiohttp
import asyncio
import asyncpg
from typing import List, Optional
from urllib.parse import urlparse


def load_symbols_from_csv(
    csv_path: str, market_filter: Optional[str] = None, limit: Optional[int] = None
) -> List[str]:
    """
    CSV 파일에서 종목 코드 목록을 읽어옵니다.

    Args:
        csv_path: CSV 파일 경로
        market_filter: 시장 필터 ('KOSPI', 'KOSDAQ' 등) - None이면 전체
        limit: 최대 종목 수 제한 - None이면 전체

    Returns:
        List[str]: 종목 코드 목록
    """
    symbols = []

    # 여러 인코딩 시도
    encodings = ["utf-8-sig", "euc-kr", "cp949", "utf-8"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding) as f:
                reader = csv.reader(f)
                header = next(reader)  # 헤더 건너뛰기

                # 헤더에서 컬럼 인덱스 찾기
                # CSV 구조: [0]ISIN코드, [1]종목코드, [2]한글 종목명, [3]한글 종목약명, [4]영문 종목명, [5]상장일, [6]시장구분, ...
                code_idx = 1  # 종목코드는 2번째 컬럼 (인덱스 1)
                market_idx = 6  # 시장구분은 7번째 컬럼 (인덱스 6)

                for row in reader:
                    if len(row) <= code_idx:
                        continue

                    code = row[code_idx].strip().strip('"')  # 따옴표 제거

                    # 시장 필터 적용
                    if market_filter and len(row) > market_idx:
                        market = row[market_idx].strip().strip('"')
                        if market_filter not in market:
                            continue

                    # 종목 코드가 6자리인지 확인
                    if code and len(code) == 6 and code.isdigit():
                        symbols.append(code)

                        # 제한 적용
                        if limit and len(symbols) >= limit:
                            break

                # 성공적으로 읽었으면 루프 종료
                break

        except UnicodeDecodeError:
            # 다음 인코딩 시도
            continue
        except Exception as e:
            print(f"[ERROR] Failed to load symbols from CSV with {encoding}: {e}")
            import traceback

            traceback.print_exc()
            continue

    return symbols


async def get_stock_codes_from_db() -> List[str]:
    """
    PostgreSQL DB에서 Company 테이블의 모든 stock_code를 가져옵니다.

    DATABASE_URL 환경변수 또는 개별 DB 환경변수를 사용하여 연결합니다.

    Returns:
        List[str]: stock_code 목록 (is_deleted=False인 기업만)
    """
    # DATABASE_URL 파싱
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        db_url = urlparse(database_url)
        db_config = {
            "host": db_url.hostname,
            "port": db_url.port or 5432,
            "user": db_url.username,
            "password": db_url.password,
            "database": db_url.path[1:],  # Remove leading '/'
        }
    else:
        # 개별 환경변수 사용
        db_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "database": os.getenv("POSTGRES_DB", "postgres"),
        }

    try:
        conn = await asyncpg.connect(**db_config)
        try:
            # is_deleted=False인 모든 기업의 stock_code 조회
            rows = await conn.fetch(
                "SELECT stock_code FROM company WHERE is_deleted = false ORDER BY stock_code"
            )
            stock_codes = [row["stock_code"] for row in rows]
            print(f"[INFO] Loaded {len(stock_codes)} stock codes from database")
            return stock_codes
        finally:
            await conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to load stock codes from database: {e}")
        import traceback

        traceback.print_exc()
        return []


def get_all_listed_symbols() -> List[str]:
    """
    모든 상장 종목 코드를 가져옵니다.

    우선순위:
    1. DB에서 stock_code 조회 (DATABASE_URL 또는 POSTGRES_* 환경변수)
    2. CSV 파일 (KRX_SYMBOLS_CSV_PATH)
    3. 환경변수 (KIS_SUBSCRIBE_SYMBOLS)
    4. 기본값 (삼성전자만)

    환경변수:
    - DATABASE_URL: PostgreSQL 연결 URL (우선 사용)
    - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB: DB 연결 정보
    - KRX_SYMBOLS_CSV_PATH: CSV 파일 경로
    - KIS_MARKET_FILTER: 시장 필터 ('KOSPI', 'KOSDAQ' 등)
    - KIS_SYMBOL_LIMIT: 최대 종목 수 제한 (기본값: 500)

    Returns:
        List[str]: 종목 코드 목록
    """
    # 1. DB에서 조회 시도 (동기적으로 호출하려면 이벤트 루프 필요)
    try:
        # 이벤트 루프가 실행 중인지 확인
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 실행 중이면 새 태스크로 실행 불가
            # 대신 None 반환하고 다음 우선순위 시도
            print(
                "[INFO] Event loop is running, skipping DB query (will be called async later)"
            )
        else:
            stock_codes = loop.run_until_complete(get_stock_codes_from_db())
            if stock_codes:
                return stock_codes
    except RuntimeError:
        # 이벤트 루프가 없으면 새로 생성
        try:
            stock_codes = asyncio.run(get_stock_codes_from_db())
            if stock_codes:
                return stock_codes
        except Exception as e:
            print(f"[WARNING] Failed to load from DB: {e}, falling back to CSV")

    # CSV 파일에서 읽기 시도
    csv_path = os.getenv("KRX_SYMBOLS_CSV_PATH")

    # 환경변수 경로가 있지만 파일이 존재하지 않으면 무시
    if csv_path and not os.path.exists(csv_path):
        csv_path = None

    if not csv_path:
        # 기본 경로 시도 (현재 디렉토리의 companies_data.csv)
        default_path = os.path.join(os.path.dirname(__file__), "companies_data.csv")
        if os.path.exists(default_path):
            csv_path = default_path

    if csv_path and os.path.exists(csv_path):
        market_filter = os.getenv("KIS_MARKET_FILTER")  # 'KOSPI', 'KOSDAQ' 등
        limit_str = os.getenv("KIS_SYMBOL_LIMIT", "500")  # 기본값 500개

        try:
            limit = int(limit_str) if limit_str else None
        except ValueError:
            limit = 500  # 기본값

        symbols = load_symbols_from_csv(
            csv_path, market_filter=market_filter, limit=limit
        )
        if symbols:
            print(f"[INFO] Loaded {len(symbols)} symbols from CSV: {csv_path}")
            if market_filter:
                print(f"[INFO] Market filter: {market_filter}")
            if limit:
                print(f"[INFO] Limited to {limit} symbols")
            return symbols
    else:
        # 환경변수에서 읽기
        env_symbols = os.getenv("KIS_SUBSCRIBE_SYMBOLS")
        if env_symbols:
            symbols = [s.strip() for s in env_symbols.split(",") if s.strip()]
            print(f"[INFO] Loaded {len(symbols)} symbols from environment variable")
            return symbols

    # 기본값
    print("[INFO] Using default symbol: 005930 (Samsung Electronics)")
    return ["005930"]


if __name__ == "__main__":
    # 테스트
    symbols = get_all_listed_symbols()
    print(f"Total symbols: {len(symbols)}")
    print(f"First 10 symbols: {symbols[:10]}")
