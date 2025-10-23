from pathlib import Path
import sys

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.crawler.fnguide import FnGuideCrawler
from utils.yahoofinance import Fundamentals as YahooFundamentals
import pandas as pd
import json
from utils.gcpmanager import GCSManager

mcp = FastMCP(name="StockFundamentalsServer")

@mcp.tool(
    name="find_fnguide_data",
    description="""FnGuide에서 한국 주식 재무제표 수집 (yfinance와 동일한 스키마).
    사용 대상:
    - 6자리 숫자 티커: 005930, 000660
    - .KS/.KQ 접미사: 005930.KS, 035720.KQ
    - 한국 기업명: 삼성전자, SK하이닉스

    반환: {
        "ticker": str,
        "country": "KR",
        "balance_sheet": str | None,      # JSON 문자열
        "income_statement": str | None,   # JSON 문자열
        "cash_flow": str | None           # JSON 문자열
    }
    """,
    tags={"fnguide", "fundamentals", "korea", "standardized"}
)
def fetch_fnguide_data(stock: str):
    """
    FnGuide에서 한국 주식 재무제표 3종을 수집합니다.

    yfinance와 동일한 스키마를 반환하여 LLM 에이전트가
    한국 주식과 해외 주식을 동일한 방식으로 처리할 수 있습니다.

    Args:
        stock: 종목 코드 (예: "005930", "삼성전자")

    Returns:
        dict: 재무제표 3종 (yfinance와 동일한 스키마)
    """
    crawler = FnGuideCrawler(stock=stock)
    return crawler.fundamentals()


@mcp.tool(
    name="find_yahoofinance_data",
    description=(
        "Fetch fundamentals data for a given company from Yahoo Finance."
        "The attribute parameter should match yfinance.Ticker attribute names "
        "such as 'income_stmt', 'balance_sheet', or 'cashflow'."
    ),
    tags={"finance", "stocks", "fundamentals", "global"}
)
def fetch_yahoofinance_data(query: str, attribute: str):
    """
    단일 attribute를 가져오는 함수 (후방 호환성 유지)
    """
    data = YahooFundamentals().fundamentals(query=query, attribute_name_str=attribute)

    if isinstance(data, pd.DataFrame):
        return json.loads(data.to_json(orient="records", date_format="iso"))
    if isinstance(data, pd.Series):
        return data.to_dict()
    if isinstance(data, dict):
        return data
    return data


@mcp.tool(
    name="get_yahoofinance_fundamentals",
    description="""Yahoo Finance에서 해외 주식 재무제표 수집 (GCS 캐싱 지원).
    사용 대상:
    - 알파벳 티커 (1-5자): AAPL, TSLA, GOOGL
    - 해외 기업명: Apple, Tesla, Microsoft

    반환: balance_sheet, income_statement, cash_flow (연간 데이터)
    """,
    tags={"yahoo", "fundamentals", "global", "cached"}
)
def get_yahoofinance_fundamentals(query: str, use_cache: bool = True):
    """
    재무제표 3종(income_stmt, balance_sheet, cashflow)을 한 번에 가져오는 통합 함수

    리팩토링된 utils.yahoofinance.Fundamentals 클래스를 사용하여:
    - GCS 캐싱으로 반복 API 호출 방지
    - 간결한 코드 구조
    - logging 모듈을 통한 체계적인 로깅

    Args:
        query: 종목 코드 또는 회사명 (예: '005930', '삼성전자', 'AAPL', 'Apple')
        use_cache: GCS 캐시 사용 여부 (기본값: True)

    Returns:
        dict: {
            "ticker": str,  # Yahoo Finance 티커 (예: '005930.KS', 'AAPL')
            "country": str,  # 상장 국가 (예: 'KR', 'US', 'Unknown')
            "balance_sheet": str | None,  # 재무상태표 (JSON 문자열)
            "income_statement": str | None,  # 손익계산서 (JSON 문자열)
            "cash_flow": str | None  # 현금흐름표 (JSON 문자열)
        }
    """
    # 리팩토링된 Fundamentals 클래스 사용 (캐싱 포함)
    return YahooFundamentals().fundamentals(query=query, use_cache=use_cache)

@mcp.tool(
    name="save_fundamentals_data_to_gcs",
    description="Saves fundamentals data to a CSV file in Google Cloud Storage.",
    tags={"gcs", "fundamentals", "storage"}
)
def save_fundamentals_data_to_gcs(fundamentals_data: dict | list, gcs_path: str, file_name: str):
    """
    fundamentals_data: The JSON-like object returned from fetch_fnguide_data or fetch_yahoofinance_data.
    gcs_path: The destination folder path in the GCS bucket.
    file_name: The name of the CSV file.
    """
    if not fundamentals_data:
        raise ValueError("fundamentals_data cannot be empty.")

    if isinstance(fundamentals_data, list):
        df = pd.DataFrame(fundamentals_data)
    elif isinstance(fundamentals_data, dict):
        df = pd.DataFrame([fundamentals_data])
    else:
        raise TypeError("fundamentals_data must be a dict or a list of dicts.")

    csv_data = df.to_csv(index=False)

    gcs_manager = GCSManager()
    destination_blob_name = f"{gcs_path}/{file_name}"
    
    success = gcs_manager.upload_file(
        source_file=csv_data,
        destination_blob_name=destination_blob_name,
        content_type="text/csv"
    )

    if success:
        return f"Successfully saved fundamentals data to gs://{gcs_manager.bucket_name}/{destination_blob_name}"
    else:
        raise Exception("Failed to upload file to GCS.")
