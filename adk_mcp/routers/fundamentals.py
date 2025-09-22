import json
import os
import math
from datetime import datetime, date, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from utils import yahoofinance, fnguide, opendart
from utils.companydict import companydict as find
from utils.gcpmanager import GCSManager

from stock_agent.fundamentals_agent import agent as fundamentals_agent

# --- Pydantic Data Validation Model ---
# RESTful 방식으로 변경함에 따라 Request Body를 사용하지 않으므로 Pydantic 모델은 제거합니다.

# --- 서비스 매핑 ---
SERVICE_MAP = {
    "fnguide": fnguide.Fundamentals(),
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

# --- API 라우터 정의 ---
router = APIRouter(prefix="/fundamentals")

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

    try:
        if current_site == "fnguide":
            gcs_manager = _get_gcs_manager()
            year, quarter = _current_year_and_quarter()
            cache_prefix = f"{_RESPONSE_CACHE_PREFIX}/year={year}/quarter={quarter}"
            cache_blob = f"{cache_prefix}/{identifier}.json"
            if not nocache:
                cached_payload = gcs_manager.read_file(cache_blob)
                if not cached_payload:
                    legacy_cache_blob = f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json"
                    cached_payload = gcs_manager.read_file(legacy_cache_blob)
                if cached_payload:
                    try:
                        payload_dict = json.loads(cached_payload)
                        return _sanitize_for_json(payload_dict)
                    except json.JSONDecodeError:
                        # fall through to refresh the cache when corrupted
                        pass

            if not nocache:
                agent_state_blob = f"{_AGENT_STATE_CACHE_PREFIX}/year={year}/quarter={quarter}/{identifier}.json"
                agent_state_raw = gcs_manager.read_file(agent_state_blob)
                if not agent_state_raw:
                    legacy_state_blob = f"{_AGENT_STATE_CACHE_PREFIX}/{identifier}.json"
                    agent_state_raw = gcs_manager.read_file(legacy_state_blob)
                if agent_state_raw:
                    try:
                        final_state = json.loads(agent_state_raw)
                        result = service_module.fundamentals(
                            stock=identifier,
                            use_cache=True,
                            overwrite=False,
                        )
                        analysis_payload = final_state.get("analysis_result", final_state)
                        rating_payload = final_state.get("rating")
                        response_payload = {
                            "result": result,
                            "analysis": analysis_payload,
                            "rating": rating_payload,
                            "session_state": final_state,
                            "agent_final_response": final_state.get("agent_final_response"),
                        }
                        sanitized_payload = _sanitize_for_json(response_payload)
                        try:
                            payload_json = json.dumps(
                                sanitized_payload,
                                ensure_ascii=False,
                                default=str,
                                allow_nan=False,
                            )
                            gcs_manager.upload_file(
                                source_file=payload_json,
                                destination_blob_name=cache_blob,
                                encoding="utf-8",
                                content_type=_JSON_CONTENT_TYPE,
                            )
                            legacy_cache_blob = f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json"
                            gcs_manager.upload_file(
                                source_file=payload_json,
                                destination_blob_name=legacy_cache_blob,
                                encoding="utf-8",
                                content_type=_JSON_CONTENT_TYPE,
                            )
                        except Exception:
                            pass
                        return sanitized_payload
                    except json.JSONDecodeError:
                        # cached agent state corrupted, continue with fresh run
                        pass

            service_module: fnguide.Fundamentals
            result = service_module.fundamentals(
                stock=identifier,
                use_cache=not nocache,
                overwrite=True if nocache else False,
            )

            final_response, final_state_json, rating = await fundamentals_agent.call_agent_async(user_input_ticker=identifier)

            try:
                final_state = json.loads(final_state_json)
            except json.JSONDecodeError:
                final_state = {}

            analysis_payload = final_state.get("analysis_result", final_state)
            rating_payload = rating or final_state.get("rating")
            agent_final_response = (
                final_response if final_response and final_response != "No final response captured." else None
            )

            response_payload = {
                "result": result,
                "analysis": analysis_payload,
                "rating": rating_payload,
                "session_state": final_state,
                "agent_final_response": agent_final_response,
            }
            sanitized_payload = _sanitize_for_json(response_payload)

            try:
                payload_json = json.dumps(
                    sanitized_payload,
                    ensure_ascii=False,
                    default=str,
                    allow_nan=False,
                )
                gcs_manager.upload_file(
                    source_file=payload_json,
                    destination_blob_name=cache_blob,
                    encoding="utf-8",
                    content_type=_JSON_CONTENT_TYPE,
                )
                legacy_cache_blob = f"{_RESPONSE_CACHE_PREFIX}/{identifier}.json"
                gcs_manager.upload_file(
                    source_file=payload_json,
                    destination_blob_name=legacy_cache_blob,
                    encoding="utf-8",
                    content_type=_JSON_CONTENT_TYPE,
                )
            except Exception:
                # Cache write failures shouldn't break the response
                pass

            return sanitized_payload
        else:
            result = service_module.fundamentals(
                stock=identifier,
                use_cache=not nocache,
                overwrite=True if nocache else False,
            )

            final_response, final_state_json, rating = await fundamentals_agent.call_agent_async(user_input_ticker=identifier)

            try:
                final_state = json.loads(final_state_json)
            except json.JSONDecodeError:
                final_state = {}

            analysis_payload = final_state.get("analysis_result", final_state)
            rating_payload = rating or final_state.get("rating")
            agent_final_response = (
                final_response if final_response and final_response != "No final response captured." else None
            )

            response_payload = {
                "result": result,
                "analysis": analysis_payload,
                "rating": rating_payload,
                "session_state": final_state,
                "agent_final_response": agent_final_response,
            }
            return _sanitize_for_json(response_payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
