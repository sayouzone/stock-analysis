from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from utils import yahoofinance, naverfinance, gemini
from utils.prompt import get_news_prompt
import json
import asyncio

SERVICE_MAP = {
    "naverfinance": naverfinance.News(),
    "yahoofinance": yahoofinance.News(),
}

router = APIRouter(prefix="/news")

@router.get("/{function}/{site}/{stock}", summary="뉴스 수집/처리 (collect/process)")
async def news_collect_or_process(function: str, site: str, stock: str, period: str = "7"):
    async def event_stream():
        fn = function.lower()
        if fn not in ("collect", "process"):
            yield f"data: {json.dumps({'error': 'function must be collect or process'})}\n\n"
            return

        if period == "0":
            max_articles = 50
        elif period == "1":
            max_articles = 30
        elif period == "7":
            max_articles = 100
        else:
            max_articles = 200

        service_module = SERVICE_MAP.get(site.lower())
        if not service_module:
            yield f"data: {json.dumps({'error': f'Site {site} not found.'})}\n\n"
            return

        handler = getattr(service_module, f"news_{fn}", None)
        if not handler or not callable(handler):
            yield f"data: {json.dumps({'error': f'Function news_{fn} not available for {site}.'})}\n\n"
            return

        articles = []
        try:
            if fn == 'collect':
                async for event in handler(query=stock, max_articles=max_articles, period=period): # type: ignore
                    yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0.01)
            else:
                async for event in handler(query=stock, limit=max_articles, period=period): # type: ignore
                    if event.get("type") == "result":
                        articles = event["data"]
                    elif event.get("type") == "error":
                        yield f"data: {json.dumps(event)}\n\n"
                        return
                    else:
                        yield f"data: {json.dumps(event)}\n\n"
                    await asyncio.sleep(0.01)

                if not articles:
                    final_payload = {"type": "final", "result": [], "analysis": {"summary": "분석할 뉴스가 없습니다."}}
                    yield f"data: {json.dumps(final_payload)}\n\n"
                    return

                # AI 분석
                yield f"data: {json.dumps({'type': 'progress', 'step': 'analysis', 'status': 'start'})}\n\n"

                analysis_input = json.dumps(articles, ensure_ascii=False, indent=2)
                prompt = get_news_prompt()
                analysis_result_str = gemini.analysis(data_json=analysis_input, prompt=prompt)
                final_payload = {"type": "final", "result": articles, "analysis": analysis_result_str}
                yield f"data: {json.dumps(final_payload)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
