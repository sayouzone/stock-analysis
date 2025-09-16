from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from utils import yahoofinance, fnguide, gemini, opendart, prompt
from utils.companydict import companydict as find

# --- Pydantic Data Validation Model ---
# RESTful 방식으로 변경함에 따라 Request Body를 사용하지 않으므로 Pydantic 모델은 제거합니다.

# --- 서비스 매핑 ---
SERVICE_MAP = {
    "fnguide": fnguide.Fundamentals(),
    "yahoofinance": yahoofinance.Fundamentals(), # Changed from YahooCrawler to Fundamentals
    "opendart": opendart.OpenDartCrawler(), 
}

# --- API 라우터 정의 ---
router = APIRouter(prefix="/fundamentals")

# --- 엔드포인트 구현 ---
@router.get("/{site}/{stock}", summary="기업 펀더멘탈(Fundamentals) 데이터 분석")
def get_fundamentals_data(site: str, stock: str):
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
            service_module : fnguide.Fundamentals
            result = service_module.fundamentals(stock=identifier)
            analysis = gemini.analysis(stock=identifier, prompt=prompt.get_fundamentals_prompt())

            return {"result": result, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))