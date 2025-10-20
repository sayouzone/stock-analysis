import json
import os
import math
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Literal, Tuple
import asyncio

from fastapi import APIRouter, HTTPException
from utils import yahoofinance, opendart
from utils.crawler import fnguide
from utils.companydict import companydict as find
from utils.gcpmanager import GCSManager

from stock_agent.fundamentals_agent import agent as fundamentals_agent

# --- Pydantic Data Validation Model ---
# RESTful 방식으로 변경함에 따라 Request Body를 사용하지 않으므로 Pydantic 모델은 제거합니다.

# --- 서비스 매핑 ---
SERVICE_MAP = {
    "fnguide": fnguide.FnGuideCrawler,
    "yahoofinance": yahoofinance.Fundamentals(), # Changed from YahooCrawler to Fundamentals
    "opendart": opendart.OpenDartCrawler(), 
}

_GCS_BUCKET = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
_RESPONSE_CACHE_PREFIX = "Fundamentals/cache/response"
_AGENT_STATE_CACHE_PREFIX = "Fundamentals/cache/agent_state"
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"


def _current_year_and_quarter(now: datetime | None = None) -> tuple[int, int]:
    instant = now or datetime.now(timezone.utc)
    quarter = (instant.month - 1) // 3 + 1
    return instant.year, quarter


def _sanitize_for_json(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, set):
        return [_sanitize_for_json(item) for item in value]
    return value

def _get_gcs_manager() -> GCSManager:
    return GCSManager(bucket_name=_GCS_BUCKET) if _GCS_BUCKET else GCSManager()


# --- 입력값 기반 자동 데이터 소스 감지 함수 ---
DataSource = Literal["fnguide", "yahoofinance", "unknown"]

def _detect_stock_info(user_input: str) -> Tuple[DataSource, str, str]:
    """
    사용자 입력으로부터 데이터 소스, 티커, 국가를 자동 추론

    Args:
        user_input: 사용자가 입력한 종목명/코드/티커

    Returns:
        (data_source, identifier, country)
        - data_source: "fnguide" | "yahoofinance" | "unknown"
        - identifier: 정규화된 종목 코드/티커
        - country: "KR" | "US" | "Unknown"

    Examples:
        >>> _detect_stock_info("삼성전자")
        ("fnguide", "005930", "KR")

        >>> _detect_stock_info("005930")
        ("fnguide", "005930", "KR")

        >>> _detect_stock_info("AAPL")
        ("yahoofinance", "AAPL", "US")

        >>> _detect_stock_info("005930.KS")
        ("yahoofinance", "005930.KS", "KR")
    """
    user_input = user_input.strip()

    # 1. companydict 조회 (우선순위 높음)
    ticker = find.get_ticker(user_input)
    code = find.get_code(user_input)

    # ticker가 있는 경우 먼저 확인
    if ticker:
        # .KS 또는 .KQ로 끝나는 경우 → Yahoo Finance 한국 종목
        if ticker.endswith((".KS", ".KQ")):
            return ("yahoofinance", ticker, "KR")
        # 그 외 ticker → Yahoo Finance 해외 종목
        else:
            return ("yahoofinance", ticker, "US")

    # ticker가 없고 code만 있는 경우 → FnGuide 한국 종목
    if code:
        return ("fnguide", code, "KR")

    # 2. 패턴 기반 추론 (companydict에 없는 경우)

    # 6자리 숫자 → 한국 종목 코드
    if user_input.isdigit() and len(user_input) == 6:
        return ("fnguide", user_input, "KR")

    # .KS 또는 .KQ로 끝남 → Yahoo Finance 한국 종목
    if user_input.endswith((".KS", ".KQ")):
        return ("yahoofinance", user_input, "KR")

    # 한글 포함 → 한국 종목 (companydict에 없으면 실패)
    if any('\uac00' <= c <= '\ud7a3' for c in user_input):
        # companydict에 없는 한글 종목명은 처리 불가
        return ("unknown", user_input, "Unknown")

    # 영문 티커 (대문자 알파벳, 1-5글자) → Yahoo Finance 해외 종목
    if user_input.isalpha() and user_input.isupper() and 1 <= len(user_input) <= 5:
        return ("yahoofinance", user_input, "US")

    # 영문이지만 소문자인 경우 대문자로 변환
    if user_input.isalpha() and 1 <= len(user_input) <= 5:
        return ("yahoofinance", user_input.upper(), "US")

    # 알 수 없는 형식
    return ("unknown", user_input, "Unknown")


# --- API 라우터 정의 ---
router = APIRouter(prefix="/fundamentals")
# --- 헬퍼 함수 ---

# AI 에이전트를 호출하고, 결과를 파싱하여 최종 응답 payload를 생성하는 헬퍼 함수
async def _create_agent_response_payload(identifier: str, result_data: dict) -> dict:
    """AI 에이전트를 호출하고, 결과를 파싱하여 최종 응답 payload를 생성합니다."""
    
    final_response, final_state_json, rating = await fundamentals_agent.call_agent_async(
        user_input_ticker=identifier
    )

    final_state = {}
    try:
        # final_state_json이 유효한 문자열인 경우에만 파싱 시도
        if isinstance(final_state_json, str):
            final_state = json.loads(final_state_json)
    except json.JSONDecodeError:
        # 파싱 실패 시 final_state는 그대로 빈 딕셔너리로 유지하고 경고를 출력합니다.
        print(f"Warning: Failed to decode agent's final_state_json for {identifier}")

    analysis_payload = final_state.get("analysis_result", final_state)
    rating_payload = rating or final_state.get("rating")
    agent_final_response = (
        final_response if final_response and final_response != "No final response captured." else None
    )

    response_payload = {
        "result": result_data,
        "analysis": analysis_payload,
        "rating": rating_payload,
        "session_state": final_state,
        "agent_final_response": agent_final_response,
    }
    
    return _sanitize_for_json(response_payload)


# --- 엔드포인트 구현 ---

@router.get("/{site}/{stock}", summary="기업 펀더멘탈(Fundamentals) 데이터 분석")
async def get_fundamentals_data(site: str, stock: str, nocache: bool = False):
    """
    요청된 site와 stock의 펀더멘탈 데이터를 크롤링하고 AI 분석을 추가합니다.
    """
    print(f"Fundamentals router received request: site='{site}', stock='{stock}'")

    current_site = site.lower()

    # 1. 서비스 모듈 찾기
    service_module = SERVICE_MAP.get(current_site)
    if not service_module:
        raise HTTPException(status_code=404, detail=f"Site '{site}' not found.")

    # 2. 사이트별로 필요한 코드를 똑똑하게 조회하기
    identifier = None
    if current_site == 'yahoofinance':
        identifier = find.get_ticker(stock) # 야후는 티커
        if not identifier:
            identifier = stock.upper()
    elif current_site == 'fnguide':
        identifier = find.get_code(stock) # fnguide는 종목코드
        if not identifier and stock.isdigit():
            identifier = stock
    elif current_site == 'opendart':
        identifier = find.get_code(stock)
    if not identifier:
        raise HTTPException(status_code=404, detail=f"Stock '{stock}' not found for {site}.")

    # --- 로직 실행 ---
    try:
        # "fnguide"는 복잡한 다단계 캐시 로직을 사용합니다.
        if current_site == "fnguide" and not nocache:
            gcs_manager = _get_gcs_manager()
            year, quarter = _current_year_and_quarter()
            
            # [1단계 캐시] 최종 응답(response) 캐시 확인
            cache_prefix = f"{_RESPONSE_CACHE_PREFIX}/year={year}/quarter={quarter}"
            cache_blob = f"{cache_prefix}/{identifier}.json"
            cached_payload = gcs_manager.read_file(cache_blob) or gcs_manager.read_file(f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json")
            if cached_payload:
                try:
                    return json.loads(cached_payload)
                except json.JSONDecodeError:
                    print("Warning: Response cache is corrupted. Refreshing...")

            # [2단계 캐시] 에이전트 상태(agent_state) 캐시 확인
            agent_state_prefix = f"{_AGENT_STATE_CACHE_PREFIX}/year={year}/quarter={quarter}"
            agent_state_blob = f"{agent_state_prefix}/{identifier}.json"
            agent_state_raw = gcs_manager.read_file(agent_state_blob) or gcs_manager.read_file(f"{_AGENT_STATE_CACHE_PREFIX}/{identifier}.json")
            if agent_state_raw:
                try:
                    # 에이전트 상태 캐시가 있으면, AI를 다시 호출하지 않고 응답을 재구성합니다.
                    final_state = json.loads(agent_state_raw)
                    result = service_module.fundamentals(stock=identifier, use_cache=True, overwrite=False)
                    
                    response_payload = {
                        "result": result,
                        "analysis": final_state.get("analysis_result", final_state),
                        "rating": final_state.get("rating"),
                        "session_state": final_state,
                        "agent_final_response": final_state.get("agent_final_response"),
                    }
                    sanitized_payload = _sanitize_for_json(response_payload)
                    
                    # 재구성한 응답을 [1단계 캐시]에 저장하여 다음 요청 시 더 빠르게 처리
                    payload_json = json.dumps(sanitized_payload, ensure_ascii=False, default=str, allow_nan=False)
                    gcs_manager.upload_file(source_file=payload_json, destination_blob_name=cache_blob, encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
                    gcs_manager.upload_file(source_file=payload_json, destination_blob_name=f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json", encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
                    
                    return sanitized_payload
                # ▼▼▼ [수정된 부분] 중복된 Exception을 제거합니다. ▼▼▼
                except Exception:
                    print("Warning: Agent state cache is corrupted. Refreshing...")

        # --- 캐시가 없거나, nocache=True 이거나, fnguide가 아닌 경우의 기본 로직 ---
        
        # 1. 기본 펀더멘탈 데이터 가져오기
        result = service_module.fundamentals(
            stock=identifier,
            use_cache=not nocache,
            overwrite=nocache,
        )
        
        # 2. AI 에이전트 호출 및 최종 응답 생성 (헬퍼 함수 사용)
        sanitized_payload = await _create_agent_response_payload(identifier, result)

        # 3. (fnguide의 경우) 생성된 최종 결과를 캐시에 저장
        if current_site == "fnguide":
            gcs_manager = _get_gcs_manager()
            year, quarter = _current_year_and_quarter()
            cache_prefix = f"{_RESPONSE_CACHE_PREFIX}/year={year}/quarter={quarter}"
            cache_blob = f"{cache_prefix}/{identifier}.json"
            
            try:
                payload_json = json.dumps(sanitized_payload, ensure_ascii=False, default=str, allow_nan=False)
                gcs_manager.upload_file(source_file=payload_json, destination_blob_name=cache_blob, encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
                gcs_manager.upload_file(source_file=payload_json, destination_blob_name=f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json", encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
            except Exception as e:
                print(f"Error during cache write: {e}")

        return sanitized_payload

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/analyze", summary="입력값 기반 자동 데이터 소스 선택 분석")
async def analyze_fundamentals(stock: str, nocache: bool = False):
    """
    사용자 입력만으로 자동으로 데이터 소스를 선택하여 분석합니다.

    프론트엔드에서 site를 지정할 필요 없이 종목명, 코드, 티커만 입력하면
    자동으로 적절한 데이터 소스(FnGuide, Yahoo Finance)를 선택합니다.

    Args:
        stock: 종목명/코드/티커 (예: "삼성전자", "005930", "AAPL", "TSLA")
        nocache: 캐시 무시 여부 (기본값: False)

    Returns:
        dict: {
            "result": 재무제표 데이터,
            "analysis": AI 분석 결과,
            "rating": 평가 점수,
            "session_state": 세션 상태,
            "agent_final_response": Agent 최종 응답,
            "metadata": {
                "detected_source": 감지된 데이터 소스,
                "identifier": 정규화된 식별자,
                "country": 국가 코드
            }
        }

    Examples:
        - /fundamentals/analyze?stock=삼성전자
        - /fundamentals/analyze?stock=005930
        - /fundamentals/analyze?stock=AAPL
        - /fundamentals/analyze?stock=TSLA&nocache=true
    """
    print(f"[Auto-detect] Analyzing stock: '{stock}'")

    # 입력값 기반 자동 감지
    data_source, identifier, country = _detect_stock_info(stock)

    print(f"[Auto-detect] Detected: source={data_source}, identifier={identifier}, country={country}")

    # 알 수 없는 데이터 소스인 경우 에러
    if data_source == "unknown":
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{stock}'의 데이터 소스를 확인할 수 없습니다. "
                f"올바른 종목명, 6자리 종목 코드, 또는 영문 티커를 입력하세요. "
                f"(예: 삼성전자, 005930, AAPL)"
            )
        )

    # 데이터 소스별 처리
    try:
        if data_source == "fnguide":
            # FnGuide 크롤러 사용 (한국 종목)

            # 캐시 확인 (fnguide만 다단계 캐싱 지원)
            if not nocache:
                gcs_manager = _get_gcs_manager()
                year, quarter = _current_year_and_quarter()

                # [1단계 캐시] 최종 응답 캐시
                cache_prefix = f"{_RESPONSE_CACHE_PREFIX}/year={year}/quarter={quarter}"
                cache_blob = f"{cache_prefix}/{identifier}.json"
                cached_payload = gcs_manager.read_file(cache_blob) or gcs_manager.read_file(f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json")

                if cached_payload:
                    try:
                        cached_data = json.loads(cached_payload)
                        # 메타데이터 추가
                        cached_data["metadata"] = {
                            "detected_source": data_source,
                            "identifier": identifier,
                            "country": country,
                            "cached": True
                        }
                        print(f"[Auto-detect] Returning cached data for {identifier}")
                        return cached_data
                    except json.JSONDecodeError:
                        print(f"[Auto-detect] Cache corrupted for {identifier}, refreshing...")

                # [2단계 캐시] 에이전트 상태 캐시
                agent_state_prefix = f"{_AGENT_STATE_CACHE_PREFIX}/year={year}/quarter={quarter}"
                agent_state_blob = f"{agent_state_prefix}/{identifier}.json"
                agent_state_raw = gcs_manager.read_file(agent_state_blob) or gcs_manager.read_file(f"{_AGENT_STATE_CACHE_PREFIX}/{identifier}.json")

                if agent_state_raw:
                    try:
                        final_state = json.loads(agent_state_raw)
                        crawler = fnguide.FnGuideCrawler(stock=identifier)
                        result = await asyncio.to_thread(crawler.fundamentals, use_cache=True, overwrite=False)

                        response_payload = {
                            "result": result,
                            "analysis": final_state.get("analysis_result", final_state),
                            "rating": final_state.get("rating"),
                            "session_state": final_state,
                            "agent_final_response": final_state.get("agent_final_response"),
                            "metadata": {
                                "detected_source": data_source,
                                "identifier": identifier,
                                "country": country,
                                "cached": True
                            }
                        }
                        sanitized_payload = _sanitize_for_json(response_payload)

                        # 재구성한 응답을 1단계 캐시에 저장
                        payload_json = json.dumps(sanitized_payload, ensure_ascii=False, default=str, allow_nan=False)
                        gcs_manager.upload_file(source_file=payload_json, destination_blob_name=cache_blob, encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
                        gcs_manager.upload_file(source_file=payload_json, destination_blob_name=f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json", encoding="utf-8", content_type=_JSON_CONTENT_TYPE)

                        return sanitized_payload
                    except Exception as e:
                        print(f"[Auto-detect] Agent state cache error: {e}")

            # 캐시가 없거나 nocache=True인 경우
            crawler = fnguide.FnGuideCrawler(stock=identifier)
            result = await asyncio.to_thread(crawler.fundamentals, use_cache=not nocache, overwrite=nocache)

        elif data_source == "yahoofinance":
            # Yahoo Finance 사용 (해외 종목 또는 .KS/.KQ)
            fundamentals_client = yahoofinance.Fundamentals()
            result = fundamentals_client.fundamentals(
                query=identifier,
                use_cache=not nocache,
                overwrite=nocache
            )

        # AI Agent 호출
        sanitized_payload = await _create_agent_response_payload(identifier, result)

        # 메타데이터 추가
        sanitized_payload["metadata"] = {
            "detected_source": data_source,
            "identifier": identifier,
            "country": country,
            "cached": False
        }

        # fnguide인 경우 캐시 저장
        if data_source == "fnguide":
            gcs_manager = _get_gcs_manager()
            year, quarter = _current_year_and_quarter()
            cache_prefix = f"{_RESPONSE_CACHE_PREFIX}/year={year}/quarter={quarter}"
            cache_blob = f"{cache_prefix}/{identifier}.json"

            try:
                payload_json = json.dumps(sanitized_payload, ensure_ascii=False, default=str, allow_nan=False)
                gcs_manager.upload_file(source_file=payload_json, destination_blob_name=cache_blob, encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
                gcs_manager.upload_file(source_file=payload_json, destination_blob_name=f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json", encoding="utf-8", content_type=_JSON_CONTENT_TYPE)
            except Exception as e:
                print(f"[Auto-detect] Cache write error: {e}")

        return sanitized_payload

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze '{stock}' (detected as {data_source}): {str(e)}"
        )