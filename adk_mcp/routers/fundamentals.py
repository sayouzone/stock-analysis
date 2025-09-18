import json
import os

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
_FNGUIDE_CACHE_PREFIX = "Fundamentals/cache"

def _get_gcs_manager() -> GCSManager:
    return GCSManager(bucket_name=_GCS_BUCKET) if _GCS_BUCKET else GCSManager()

# --- API 라우터 정의 ---
router = APIRouter(prefix="/fundamentals")

# --- 엔드포인트 구현 ---
@router.get("/{site}/{stock}", summary="기업 펀더멘탈(Fundamentals) 데이터 분석")
async def get_fundamentals_data(site: str, stock: str):
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
    elif current_site == 'fnguide':
        identifier = find.get_code(stock) # fnguide는 종목코드
    elif current_site == 'opendart':
        identifier = find.get_code(stock)
    if not identifier:
        raise HTTPException(status_code=404, detail=f"Stock '{stock}' not found for {site}.")

    try:
        if current_site == "fnguide":
            cache_blob = f"{_FNGUIDE_CACHE_PREFIX}/{identifier}.json"
            gcs_manager = _get_gcs_manager()
            cached_payload = gcs_manager.read_file(cache_blob)
            if cached_payload:
                try:
                    payload_dict = json.loads(cached_payload)
                    return payload_dict
                except json.JSONDecodeError:
                    # fall through to refresh the cache when corrupted
                    pass

            agent_state_blob = f"Fundamentals/{identifier}.json"
            agent_state_raw = gcs_manager.read_file(agent_state_blob)
            if agent_state_raw:
                try:
                    final_state = json.loads(agent_state_raw)
                    result = service_module.fundamentals(stock=identifier)
                    analysis_payload = final_state.get("analysis_result", final_state)
                    rating_payload = final_state.get("rating")
                    response_payload = {
                        "result": result,
                        "analysis": analysis_payload,
                        "rating": rating_payload,
                        "session_state": final_state,
                        "agent_final_response": final_state.get("agent_final_response"),
                    }
                    try:
                        gcs_manager.upload_file(
                            source_file=json.dumps(response_payload, ensure_ascii=False, default=str),
                            destination_blob_name=cache_blob,
                            encoding="utf-8",
                            content_type="application/json; charset=utf-8",
                        )
                    except Exception:
                        pass
                    return response_payload
                except json.JSONDecodeError:
                    # cached agent state corrupted, continue with fresh run
                    pass

            service_module: fnguide.Fundamentals
            result = service_module.fundamentals(stock=identifier)

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

            try:
                gcs_manager.upload_file(
                    source_file=json.dumps(response_payload, ensure_ascii=False, default=str),
                    destination_blob_name=cache_blob,
                    encoding="utf-8",
                    content_type="application/json; charset=utf-8",
                )
            except Exception:
                # Cache write failures shouldn't break the response
                pass

            return response_payload
        else:
            return service_module.fundamentals(stock=identifier)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
