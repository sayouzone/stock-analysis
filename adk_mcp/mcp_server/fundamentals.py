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
    description="""FnGuide에서 한국 주식 재무제표 수집.
    사용 대상:
    - 6자리 숫자 티커: 005930, 000660
    - .KS/.KQ 접미사: 005930.KS, 035720.KQ
    - 한국 기업명: 삼성전자, SK하이닉스

    반환: 재무상태표, 포괄손익계산서, 현금흐름표 (연간 데이터)
    """,
    tags={"fnguide", "fundamentals", "korea"}
)
def fetch_fnguide_data(stock: str):
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
    description="""Yahoo Finance에서 해외 주식 재무제표 수집.
    사용 대상:
    - 알파벳 티커 (1-5자): AAPL, TSLA, GOOGL
    - 해외 기업명: Apple, Tesla, Microsoft

    반환: balance_sheet, income_statement, cash_flow (연간 데이터)
    """,
    tags={"yahoo", "fundamentals", "global"}
)
def get_yahoofinance_fundamentals(query: str):
    """
    재무제표 3종(income_stmt, balance_sheet, cashflow)을 한 번에 가져오는 통합 함수

    Args:
        query: 종목 코드 또는 회사명 (예: '005930', '삼성전자', 'AAPL', 'Apple')

    Returns:
        dict: {
            "ticker": str,  # Yahoo Finance 티커 (예: '005930.KS', 'AAPL')
            "country": str,  # 상장 국가 (예: 'KR', 'US', 'Unknown')
            "balance_sheet": str | None,  # 재무상태표 (JSON 문자열)
            "income_statement": str | None,  # 손익계산서 (JSON 문자열)
            "cash_flow": str | None  # 현금흐름표 (JSON 문자열)
        }
    """
    import yfinance as yf
    from utils.companydict import companydict as find

    # companydict를 통해 올바른 티커 형식 조회
    # 한국 주식: '005930' → '005930.KS'
    # 미국 주식: 'AAPL' → 'AAPL'
    ticker_symbol = find.get_ticker(query)

    # companydict에 없는 경우 입력값 그대로 사용 (대문자 변환)
    if not ticker_symbol:
        ticker_symbol = query.upper()

    # yfinance Ticker 객체 생성
    ticker = yf.Ticker(ticker_symbol)

    # 국가 정보 추론
    country = "Unknown"
    try:
        info = ticker.info or {}
        country = info.get("country") or "Unknown"
    except Exception:
        pass

    # 한국 종목 코드 패턴 확인 (.KS 또는 .KQ 접미사)
    if ".KS" in ticker_symbol or ".KQ" in ticker_symbol:
        country = "KR"
    # 6자리 숫자만 있는 경우도 한국으로 추정 (예: 사용자가 '005930' 직접 입력)
    elif ticker_symbol.replace(".KS", "").replace(".KQ", "").isdigit() and len(ticker_symbol.replace(".KS", "").replace(".KQ", "")) == 6:
        country = "KR"

    # 재무제표 3종 수집
    result = {
        "ticker": ticker_symbol,
        "country": country,
        "balance_sheet": None,
        "income_statement": None,
        "cash_flow": None
    }

    # 1. Balance Sheet (재무상태표)
    try:
        balance_sheet = ticker.balance_sheet
        if balance_sheet is not None and not balance_sheet.empty:
            result["balance_sheet"] = balance_sheet.to_json(orient="columns", date_format="iso")
    except Exception as e:
        print(f"Warning: Failed to fetch balance_sheet for {ticker_symbol}: {e}")

    # 2. Income Statement (손익계산서)
    try:
        income_stmt = ticker.income_stmt
        if income_stmt is not None and not income_stmt.empty:
            result["income_statement"] = income_stmt.to_json(orient="columns", date_format="iso")
    except Exception as e:
        print(f"Warning: Failed to fetch income_stmt for {ticker_symbol}: {e}")

    # 3. Cash Flow (현금흐름표)
    try:
        cashflow = ticker.cashflow
        if cashflow is not None and not cashflow.empty:
            result["cash_flow"] = cashflow.to_json(orient="columns", date_format="iso")
    except Exception as e:
        print(f"Warning: Failed to fetch cashflow for {ticker_symbol}: {e}")

    return result

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
