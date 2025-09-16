from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, RedirectResponse
from utils import naverfinance, yahoofinance, gemini
from utils.prompt import get_market_prompt
from utils.companydict import companydict as find
from datetime import date
import json
import numpy as np
import asyncio
from typing import Any, Dict, Callable, AsyncIterable, TypedDict, cast

# --- Numpy 타입 JSON 인코더 ---
class NpEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super(NpEncoder, self).default(o)

# --- 서비스 매핑 ---
SERVICE_MAP = {
    "naver": naverfinance.Market(),
    "yahoo": yahoofinance.Market(),
}
class ErrorResult(TypedDict):
    error: str

class ValidationResult(TypedDict):
    service_module: Any
    ticker: str
    handler: Callable[..., AsyncIterable[Dict[str, Any]]]
    kwargs: Dict[str, Any]

# Helper functions for market_collect_or_process
def _validate_and_get_params(fn_raw: str, site: str, stock: str, start_date: date | None, end_date: date | None) -> ValidationResult | ErrorResult:
    fn = fn_raw.strip()
    if fn not in ("collect", "process"):
        return {"error": "function must be collect or process"}

    service_module = SERVICE_MAP.get(site.lower())
    if not service_module:
        return {"error": f"Site {site} not found."}

    ticker = find.get_ticker(stock) if site.lower() == 'yahoo' else find.get_code(stock)
    if not ticker:
        return {"error": f"Stock {stock} not found."}

    handler = getattr(service_module, f"market_{fn}", None)
    if not handler or not callable(handler):
        return {"error": f"Function market_{fn} not available for {site}."}

    kwargs: Dict[str, Any] = {}
    if ticker:
        kwargs["company"] = ticker
    if start_date:
        kwargs["start_date"] = start_date.strftime('%Y-%m-%d')
    if end_date:
        kwargs["end_date"] = end_date.strftime('%Y-%m-%d')
    if not callable(handler):
        return {"error": f"Internal: {site}.Market.market_{fn} is not callable (got {type(handler).__name__})."}
    result: ValidationResult = {
        "service_module": service_module,
        "ticker": ticker,
        "handler": cast(Callable[..., AsyncIterable[Dict[str, Any]]], handler),
        "kwargs": kwargs,
    }
    return result

async def _perform_analysis_and_format_response(market_data, fn):
    if fn == 'process' and market_data:
        yield f"data: {json.dumps({'type': 'progress', 'step': 'analysis', 'status': 'start'})}\n\n"


        summary_for_analysis = {
            "name": market_data.get("name"),
            "currentPrice": market_data.get("currentPrice"),
            "volume": market_data.get("volume"),
            "marketCap": market_data.get("marketCap")
        }
        analysis_input = json.dumps(summary_for_analysis, cls=NpEncoder, ensure_ascii=False, indent=2)
        prompt = get_market_prompt()
        analysis_result_str = gemini.analysis(data_json=analysis_input, prompt=prompt)
        if analysis_result_str is None:
            analysis_result_str = json.dumps({
                "summary": "AI 분석 결과가 없습니다.",
                "key_issues": "-",
                "risk_factors": "-",
                "investment_implication": "분석 오류"
            }, ensure_ascii=False)
        analysis_result_obj = json.loads(analysis_result_str)
        final_payload = {"type": "final", "result": market_data, "analysis": analysis_result_obj}
        yield f"data: {json.dumps(final_payload, cls=NpEncoder, ensure_ascii=False)}\n\n"

# --- API 라우터 정의 ---
router = APIRouter(prefix="/market")

# --- 새로운 경로 스타일: /market/{function}/{site}/{stock}
@router.get("/{function}/{site}/{stock}", summary="시장 데이터 수집/처리 (collect/process)")
async def market_collect_or_process(function: str, site: str, stock: str, start_date: date | None = Query(None), end_date: date | None = Query(None)):
    async def event_stream():
        validation_result = _validate_and_get_params(function.lower(), site.lower(), stock, start_date, end_date)
        if "error" in validation_result:
            yield f"data: {json.dumps(validation_result)}\n\n"
            return

        params = cast(ValidationResult, validation_result)
        handler = params["handler"]
        kwargs = params["kwargs"]
        fn = function.lower()

        try:
            market_data = None
            error_occurred = False
            # Directly iterate over the handler's async generator
            async for event in handler(**kwargs):
                if event.get("type") == "result":
                    market_data = event.get("data")
                elif event.get("type") == "error":
                    error_occurred = True

                yield f"data: {json.dumps(event, cls=NpEncoder)}\n\n"
                await asyncio.sleep(0.01)

            if error_occurred:
                return

            # After collecting data, perform analysis if needed
            async for chunk in _perform_analysis_and_format_response(market_data, fn):
                yield chunk

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# remove old endpoints; only function-first below

# --- Compatibility alias: redirect old pattern to new process route ---
@router.get("/{site}/{stock}", summary="[compat] Redirect to /market/process/{site}/{stock}")
async def market_compat_redirect(site: str, stock: str, start_date: date | None = Query(None), end_date: date | None = Query(None)):
    params = []
    if start_date:
        params.append(f"start_date={start_date.strftime('%Y-%m-%d')}")
    if end_date:
        params.append(f"end_date={end_date.strftime('%Y-%m-%d')}")
    qs = ("?" + "&".join(params)) if params else ""
    return RedirectResponse(url=f"/market/process/{site}/{stock}{qs}", status_code=307)
