from fastapi import APIRouter
from utils.gcpmanager import GCSManager
from google.cloud import storage

gcs_manager = GCSManager()
# --- API 라우터 정의 ---
router = APIRouter(prefix="/fundamentals")
# --- 헬퍼 함수 ---
def _check_cache(stock):
    client = storage.Client(project="sayouzone-ai")
    bucket = client.bucket(bucket_name="sayouzone-ai-stocks")
    blob = bucket.blob("Fundamentals/{stock}.json")

    content_bytes = blob.download_as_bytes()
    return content_bytes

def _save_to_cache(stock, data):
    client = storage.Client(project="sayouzone-ai")
    bucket = client.bucket(bucket_name="sayouzone-ai-stocks")
    blob = bucket.blob(f"Fundamentals/{stock}.json")
    blob.upload_from_string(data)
    
@router.get("/{stock}", summary="티커 기반 재무제표 조회")
async def get_fundamentals(stock: str, nocache: bool = False):
    """
    1. 캐시 조회 우선
    2. 캐시 없으면 Agent 호출하여 데이터 수집
    3. Agent가 MCP tool 자동 선택 (티커 형식 기반)
    """
    
    # 1. 캐시 조회
    if not nocache:
        cached_data = await _check_cache(stock)
        if cached_data:
            return cached_data

    from stock_agent.fundamentals_agent.agent import call_agent_async
    agent_result = await call_agent_async(user_input_ticker=stock)

    await _save_to_cache(stock, agent_result)
    return {"result": agent_result}