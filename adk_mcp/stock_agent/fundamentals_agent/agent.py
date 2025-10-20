import os
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

import logging

from typing import Dict, List, Optional, Literal, AsyncGenerator, Any
from typing_extensions import override

from google.adk.agents import LlmAgent, LoopAgent, BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.planners import BuiltInPlanner
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event
from google.adk.utils.context_utils import Aclosing
from pydantic import BaseModel, Field

from stock_agent.tools import (
    fundamentals_mcp_tool,
    # 웹 검색 기능 제거
    # hybrid_web_search,
    # brave_raw_search,
    # WEB_SEARCH_TOOL_AVAILABLE,
)
from stock_agent.fundamentals_agent.prompt import fetch_fundamentals_data_instructions
from google.adk.tools.set_model_response_tool import SetModelResponseTool
from utils.gcpmanager import GCSManager

full_instruction = fetch_fundamentals_data_instructions()

os.getenv("GOOGLE_API_KEY")

CURRENT_DATE = date.today().isoformat()
CURRENT_DATE_LINE_KO = f"오늘 날짜는 {CURRENT_DATE}입니다."
CURRENT_DATE_LINE_EN = f"Today's date is {CURRENT_DATE}."

FUNDAMENTALS_FETCHER_GUIDANCE = """
# 재무제표 데이터 수집 가이드

## 티커 형식 기반 Tool 선택

**한국 주식** → `find_fnguide_data`:
- 6자리 숫자: 005930, 000660, 035720
- .KS/.KQ 접미사: 005930.KS, 035720.KQ
- 한국 기업명: 삼성전자, SK하이닉스

**해외 주식** → `get_yahoofinance_fundamentals`:
- 알파벳 티커: AAPL, TSLA, GOOGL
- 해외 기업명: Apple, Tesla, Microsoft

## 사용 예시

# 한국 주식
find_fnguide_data(stock="005930")
find_fnguide_data(stock="삼성전자")

# 해외 주식
get_yahoofinance_fundamentals(query="AAPL")
get_yahoofinance_fundamentals(query="Apple")

## 데이터 키 매핑

FnGuide:
- "재무상태표" → balance_sheet
- "포괄손익계산서" → income_statement
- "현금흐름표" → cash_flow

Yahoo Finance:
- 이미 올바른 키 이름 사용 (변환 불필요)
"""

if full_instruction:
    fundamentals_fetcher_instruction = f"{CURRENT_DATE_LINE_KO}\n\n{full_instruction}\n\n{FUNDAMENTALS_FETCHER_GUIDANCE}"
else:
    fundamentals_fetcher_instruction = f"{CURRENT_DATE_LINE_KO}\n\n{FUNDAMENTALS_FETCHER_GUIDANCE}"

# --- Runtime configuration (tunable via environment variables) ---
FAST_MODE = os.getenv("FUNDAMENTALS_AGENT_FAST_MODE", "true").lower() == "true"
DEFAULT_THINKING_MODEL = "gemini-2.5-flash" if FAST_MODE else "gemini-2.5-pro"
THINKING_MODEL = os.getenv("FUNDAMENTALS_THINKING_MODEL", DEFAULT_THINKING_MODEL)


def _supports_thinking(model_name: str) -> bool:
    overridden = os.getenv("FUNDAMENTALS_FORCE_THINKING")
    if overridden:
        return overridden.lower() in {"1", "true", "yes", "on"}
    name = model_name.lower()
    if "flash" in name and "thinking" not in name:
        return False
    return True


SUPPORTS_THINKING = _supports_thinking(THINKING_MODEL)

if FAST_MODE:
    DEFAULT_ANALYST_BUDGET = "256"
    DEFAULT_REVIEWER_BUDGET = "192"
    DEFAULT_REVISER_BUDGET = "192"
    DEFAULT_RATER_BUDGET = "128"
    DEFAULT_REVIEW_LOOPS = "0"
else:
    DEFAULT_ANALYST_BUDGET = "1024"
    DEFAULT_REVIEWER_BUDGET = "512"
    DEFAULT_REVISER_BUDGET = "512"
    DEFAULT_RATER_BUDGET = "512"
    DEFAULT_REVIEW_LOOPS = "3"

if SUPPORTS_THINKING:
    ANALYST_THINKING_BUDGET = int(os.getenv("FUNDAMENTALS_ANALYST_THINKING_BUDGET", DEFAULT_ANALYST_BUDGET))
    REVIEWER_THINKING_BUDGET = int(os.getenv("FUNDAMENTALS_REVIEWER_THINKING_BUDGET", DEFAULT_REVIEWER_BUDGET))
    REVISER_THINKING_BUDGET = int(os.getenv("FUNDAMENTALS_REVISER_THINKING_BUDGET", DEFAULT_REVISER_BUDGET))
    RATER_THINKING_BUDGET = int(os.getenv("FUNDAMENTALS_RATER_THINKING_BUDGET", DEFAULT_RATER_BUDGET))
else:
    ANALYST_THINKING_BUDGET = 0
    REVIEWER_THINKING_BUDGET = 0
    REVISER_THINKING_BUDGET = 0
    RATER_THINKING_BUDGET = 0

REVIEW_LOOP_MAX_ITERATIONS = int(os.getenv("FUNDAMENTALS_REVIEW_MAX_ITERATIONS", DEFAULT_REVIEW_LOOPS))

# --- Constants ---
APP_NAME = "fundamentals_analysis_app"
USER_ID = "12345"
SESSION_ID = "123344"

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _strip_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _upload_json_payload(
    gcs_manager: GCSManager,
    *,
    blob_name: str,
    payload: dict[str, Any],
) -> bool:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to serialize payload for %s: %s", blob_name, exc)
        return False

    return gcs_manager.upload_file(
        source_file=serialized,
        destination_blob_name=blob_name,
        encoding="utf-8",
        content_type="application/json; charset=utf-8",
    )
def _upload_to_destinations(
    gcs_manager: GCSManager,
    *,
    payload: dict[str, Any],
    base_filename: str,
    destinations: List[str],
) -> None:
    """
    주어진 페이로드를 여러 목적지 경로에 업로드합니다.
    
    Args:
        gcs_manager: GCSManager 인스턴스.
        payload: 업로드할 JSON 데이터 (dict).
        base_filename: 업로드될 파일의 기본 이름 (예: "005930.json").
        destinations: 업로드할 경로(prefix)의 리스트. 빈 문자열("")은 버킷 루트를 의미합니다.
    """
    for prefix in destinations:
        # prefix가 있으면 경로를 조합하고, 없으면(버킷 루트) 파일 이름만 사용합니다.
        blob_name = f"{prefix}/{base_filename}" if prefix else base_filename
        
        # 경로 맨 앞에 있을 수 있는 슬래시 제거
        blob_name = blob_name.lstrip('/')

        _upload_json_payload(gcs_manager, blob_name=blob_name, payload=payload)



def _fallback_fundamentals_data(ticker: str, message: str) -> dict[str, str]:
    """재무제표 3종만 포함하는 폴백 데이터"""
    fallback_message = (message[:480] + "…") if len(message) > 480 else message
    return {
        "ticker": ticker or "",
        "country": "Unknown",
        "balance_sheet": fallback_message,
        "income_statement": fallback_message,
        "cash_flow": fallback_message,
    }

def _normalize_fundamentals_payload(value: Any, *, ticker: str) -> dict[str, Any]:
    if value is None:
        return _fallback_fundamentals_data(ticker, "펀더멘털 데이터를 생성하지 못했습니다.")
    if isinstance(value, str):
        # LLM이 반환하는 마크다운 형식의 JSON 문자열(```json ... ```)을 정리한다.
        clean_value = value.strip()
        if clean_value.startswith("```json"):
            clean_value = clean_value[7:]
        if clean_value.endswith("```"):
            clean_value = clean_value[:-3]
        
        try:
            parsed = json.loads(clean_value)
        except json.JSONDecodeError:
            # 파싱 실패 시 원본 문자열로 폴백 데이터를 생성한다.
            return _fallback_fundamentals_data(ticker, value)
        
        if not isinstance(parsed, dict):
            return _fallback_fundamentals_data(ticker, str(parsed))
        value = parsed

    if isinstance(value, (list, tuple, set)):
        return _fallback_fundamentals_data(ticker, str(list(value)))
    if not isinstance(value, dict):
        return _fallback_fundamentals_data(ticker, str(value))

    merged: dict[str, Any] = {**value}
    merged["ticker"] = ticker or str(merged.get("ticker", ""))
    merged.setdefault("country", "Unknown")

    defaults = _fallback_fundamentals_data(merged["ticker"], "데이터가 제공되지 않았습니다.")
    for key, fallback in defaults.items():
        if key == "ticker":
            continue
        if not merged.get(key):
            merged[key] = fallback
        elif not isinstance(merged[key], str):
            merged[key] = str(merged[key])
    return merged


def _make_planner(thinking_budget: int | None) -> BuiltInPlanner | None:
    if not SUPPORTS_THINKING:
        return None
    if not thinking_budget or thinking_budget <= 0:
        return None
    return BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=thinking_budget,
        ),
    )


class FundamentalsData(BaseModel):
    """재무제표 3종만 포함하는 기본 데이터 모델"""
    ticker: str = Field(description="The stock ticker symbol of the company.")
    country: str = Field(description="The country where the company is listed.")
    balance_sheet: Optional[str] = Field(default=None, description="The company's balance sheet data (재무상태표).")
    income_statement: Optional[str] = Field(default=None, description="The company's income statement data (손익계산서).")
    cash_flow: Optional[str] = Field(default=None, description="The company's cash flow statement data (현금흐름표).")
    
class AnalysisResult(BaseModel):
    """재무제표 3종에 대한 분석 결과 모델"""
    ticker: str = Field(description="The stock ticker symbol of the company.")
    country: str = Field(description="The country where the company is listed.")
    balance_sheet: str = Field(description="재무상태표 분석 - 자산, 부채, 자본 구조 및 건전성 평가")
    income_statement: str = Field(description="손익계산서 분석 - 매출, 비용, 영업이익, 순이익 추이 분석")
    cash_flow: str = Field(description="현금흐름표 분석 - 영업/투자/재무 활동 현금흐름 분석")

class RatingResult(BaseModel):
    score: int = Field(description="Numerical score from 1 to 100")
    rate: str = Field(description="Qualitative rating: excellent, good, normal, warning")
    justification: Optional[str] = Field(default=None, description="Short explanation for the rating")

# --- JSON Formatter Agent to ensure valid JSON output ---
json_formatter = LlmAgent(
    model=THINKING_MODEL,
    name="JsonFormatter",
    instruction=(
        f"{CURRENT_DATE_LINE_EN}\n"
        "You are an expert in formatting text into JSON.\n"
        "Your task is to take the provided {{analysis_result}} and ensure it is formatted as a valid JSON object.\n"
        "Ensure the output strictly adheres to JSON syntax, including proper use of braces, brackets, commas, and quotation marks.\n"
        "Do not include any additional text or commentary outside of the JSON object."
    ),
    input_schema=AnalysisResult,
    output_key="analysis_result"
)

async def run_json_formatter_callback(
    *, callback_context: CallbackContext
) -> Optional[types.Content]:
    """Runs the json_formatter agent and returns its final content.

    The callback mirrors BaseAgent.after_agent_callback contract by using the
    existing invocation context, copying any state updates produced by the
    formatter, and returning the formatter's final response so that it becomes
    the agent reply.
    """

    # Nothing to format when the intermediate result is missing.
    current_result = callback_context.state.get("analysis_result")
    if not current_result:
        return None

    formatter_ctx = json_formatter._create_invocation_context(
        callback_context._invocation_context
    )

    formatted_content: Optional[types.Content] = None
    async with Aclosing(json_formatter.run_async(formatter_ctx)) as agen:
        async for event in agen:
            if event.actions and event.actions.state_delta:
                callback_context.state.update(event.actions.state_delta)
            if event.content:
                formatted_content = event.content

    return formatted_content

class FundamentalsAnalysisAgent(BaseAgent):
    """
    Custom agent for a company fundamentals analysis and refinement workflow.

    This agent orchestrates a sequence of LLM agents to company fundamentals analysis, 
    review it, revise it, and output for json.
    """
    fundamentals_fetcher: LlmAgent
    analyst: LlmAgent
    reviewer: LlmAgent
    reviser: LlmAgent
    rater: LlmAgent
    json_formatter: LlmAgent

    loop_agent: LoopAgent

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
            self,
            name: str,
            fundamentals_fetcher: LlmAgent,
            analyst: LlmAgent,
            reviewer: LlmAgent,
            reviser: LlmAgent,
            rater: LlmAgent,
            json_formatter: LlmAgent,
    ):
        """
        Initializes the FundamentalsAnalysisAgent.

        Args:
            name: The name of the agent.
            analyst: An LlmAgent to analyze the fundamentals of a company.
            reviewer: An LlmAgent to review the analysis result.
            reviser: An LlmAgent to revise the analysis result based on commentary.
            rater: An LlmAgent to score the final analysis outcome.
            json_formatter: An LlmAgent to enforce JSON formatting on outputs.
        """

        # Create internal agents *before* calling super().__init__
        loop_agent = LoopAgent(
            name="ReviewerReviserLoop",
            sub_agents=[reviewer, reviser],
            max_iterations=REVIEW_LOOP_MAX_ITERATIONS,
        )

        sub_agents_list = [
            fundamentals_fetcher,
            analyst,
            loop_agent,
            rater,
            json_formatter,
        ]

        super().__init__(
            name=name,
            fundamentals_fetcher=fundamentals_fetcher,
            analyst=analyst,
            reviewer=reviewer,
            reviser=reviser,
            rater=rater,
            json_formatter=json_formatter,
            loop_agent=loop_agent,
            sub_agents=sub_agents_list,
        )
    
    @override
    async def _run_async_impl(
        self,
        ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Implements the custom orchestration logic for the company fundamentals analysis workflow.
        Uses the instance attributes assigned by Pydantic (e.g., self.analyst).
        """
        logger.info(f"[{self.name}]")

        logger.info(f"[{self.name}] Running FundamentalsFetcher...")
        async for event in self.fundamentals_fetcher.run_async(ctx):
            logger.info(f"[{self.name}] Event from FundamentalsFetcher: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        # Check if fundamentals data before proceeding
        if "fundamentals_data" not in ctx.session.state or not ctx.session.state["fundamentals_data"]:
            logger.warning(f"[{self.name}] No fundamentals_data found in context after FundamentalsFetcher. Exiting.")
            return

        ticker_value = str(ctx.session.state.get("ticker", ""))
        ctx.session.state["fundamentals_data"] = _normalize_fundamentals_payload(
            ctx.session.state.get("fundamentals_data"),
            ticker=ticker_value,
        )

        logger.info(f"[{self.name}]")

        # 2. Initial Analysis
        logger.info(f"[{self.name}] Running Analyst...")
        async for event in self.analyst.run_async(ctx):
            logger.info(f"[{self.name}] Event from Analyst: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event
        
        # Check if analysis result before proceeding
        if "analysis_result" not in ctx.session.state or not ctx.session.state["analysis_result"]:
            logger.warning(f"[{self.name}] No analysis_result found in context after Analyst. Exiting.")
            return
        
        logger.info(f"[{self.name}]")

        # 3. Review and Revise Loop (optional)
        if self.loop_agent.max_iterations > 0:
            logger.info(f"[{self.name}] Running ReviewerReviserLoop (max_iterations={self.loop_agent.max_iterations})...")
            async for event in self.loop_agent.run_async(ctx):
                logger.info(f"[{self.name}] Event from ReviewerReviserLoop: {event.model_dump_json(indent=2, exclude_none=True)}")
                yield event
        else:
            logger.info(f"[{self.name}] Skipping ReviewerReviserLoop (fast mode).")

        logger.info(f"[{self.name}]")

        # 4. Rating for finalcial analysis quality
        logger.info(f"[{self.name}] Running Rater...")
        async for event in self.rater.run_async(ctx):
            logger.info(f"[{self.name}] Event from Rater: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event
        
        logger.info(f"[{self.name}] Completed all steps.")

# 웹 검색 도구 제거 - fundamentals_mcp_tool만 사용
_FETCHER_TOOLS: List[Any] = [fundamentals_mcp_tool]

fundamentals_fetcher = LlmAgent(
    model = "gemini-2.5-flash",
    name = "FundamentalsFetcher",
    description="""
    Fetches comprehensive fundamentals data for a specified stock ticker and country.
    """,
    instruction=fundamentals_fetcher_instruction,
    output_key="fundamentals_data",
    tools=_FETCHER_TOOLS,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True
)

analyst = LlmAgent(
    model=THINKING_MODEL,
    planner=_make_planner(ANALYST_THINKING_BUDGET),
    name="Analyst",
    tools=[SetModelResponseTool(AnalysisResult)],
    instruction=(
        f"{CURRENT_DATE_LINE_EN}\n"
        "You are a seasoned financial analyst.\n"
        "Your task is to analyze the provided: {{fundamentals_data}}. \n"
        "Deliver a comprehensive analysis covering ONLY the three financial statements:\n"
        "- Balance Sheet (재무상태표): 자산, 부채, 자본의 구조와 건전성 분석\n"
        "- Income Statement (손익계산서): 매출, 비용, 영업이익, 순이익의 추이 및 수익성 분석\n"
        "- Cash Flow (현금흐름표): 영업/투자/재무 활동별 현금흐름 분석 및 유동성 평가\n"
        "\n"
        "Language requirement:\n"
        "- Write all narrative text in Korean. Use clear, natural Korean suitable for professional financial reports.\n"
        "\n"
        "Output MUST be a single valid JSON object matching this schema:\n"
        "{\n"
        "  \"ticker\": \"...\",\n"
        "  \"country\": \"...\",\n"
        "  \"balance_sheet\": \"...\",\n"
        "  \"income_statement\": \"...\",\n"
        "  \"cash_flow\": \"...\"\n"
        "}\n"
        "\n"
        "Rules:\n"
        "- Fill every field with a detailed, well-supported narrative paragraph (minimum 3-5 sentences per field).\n"
        "- Focus on quantitative data, trends, ratios, and year-over-year comparisons.\n"
        "- Do not emit markdown, bullet lists, or code fences.\n"
        "- Do not include trailing comments or additional text outside the JSON object."
    ),
    input_schema=FundamentalsData,
    output_key="analysis_result",
    after_agent_callback=run_json_formatter_callback
)


reviewer = LlmAgent(
    model=THINKING_MODEL,
    planner=_make_planner(REVIEWER_THINKING_BUDGET),
    name="Reviewer",
    instruction=(
        f"{CURRENT_DATE_LINE_EN}\n"
        "You are a meticulous financial analyst.\n"
        "Your task is to review the provided: {{fundamentals_data}}, {{analysis_result}}. \n"
        "Identify any gaps, inconsistencies, or areas that need further clarification or evidence.\n"
        "Provide constructive feedback and specific suggestions for improvement.\n"
        "\n"
        "Language requirement:\n"
        "- Write your review comments in Korean."
    ),
    input_schema=AnalysisResult,
    output_key="review_comments"
)

reviser = LlmAgent(
    model=THINKING_MODEL,
    planner=_make_planner(REVISER_THINKING_BUDGET),
    name="Reviser",
    instruction=(
        f"{CURRENT_DATE_LINE_EN}\n"
        "You are a skilled financial analyst.\n"
        "Your task is to revise the provided: {{fundamentals_data}}, {{analysis_result}} based on the review comments: {{review_comments}}. \n"
        "Address each comment with specific improvements, additional evidence, or clarifications as needed.\n"
        "Ensure the revised analysis is comprehensive, accurate, and well-supported.\n"
        "\n"
        "Language requirement:\n"
        "- Ensure all narrative fields in the final JSON remain in Korean."
    ),
    input_schema=AnalysisResult,
    output_key="analysis_result",
    after_agent_callback=run_json_formatter_callback
)

rater = LlmAgent(
    model=THINKING_MODEL,
    planner=_make_planner(RATER_THINKING_BUDGET),
    name="Rater",
    instruction=(
        f"{CURRENT_DATE_LINE_EN}\n"
        "You are an expert financial analyst.\n"
        "Your task is to rate the quality of the provided {{analysis_result}} on a scale from 1 to 100,\n"
        "considering accuracy, depth, clarity, and relevance.\n"
        "Provide a brief justification for your rating.\n"
        "Output must be a JSON object with the following fields:\n"
        "{\n"
        "  \"score\": <1-100>,\n"
        "  \"rate\": \"excellent\" | \"good\" | \"normal\" | \"warning\",\n"
        "  \"justification\": \"short explanation\"\n"
        "}\n"
        "\n"
        "score guide:\n"
        "85-100: excellent\n"
        "70-84: good\n"
        "55-69: normal\n"
        "-54: warning"
    ),
    input_schema=AnalysisResult,
    output_schema=RatingResult,
    output_key="rating",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True
)

fundamentals_analysis_agent = FundamentalsAnalysisAgent(
    name="FundamentalsAnalysisAgent",
    fundamentals_fetcher=fundamentals_fetcher,
    analyst=analyst,
    reviewer=reviewer,
    reviser=reviser,
    rater=rater,
    json_formatter=json_formatter,
)

# FastMCP 및 ADK 로더가 찾을 수 있도록 루트 에이전트 별칭을 노출한다.
root_agent = fundamentals_analysis_agent

async def setup_session_and_runner(ticker: str):
    session_service = InMemorySessionService()
    initial_state = {"ticker": ticker}
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, state=initial_state)
    logger.info(f"Initial session state: {session.state}")
    runner = Runner(
        agent=fundamentals_analysis_agent, # Pass the custom orchestrator agent
        app_name=APP_NAME,
        session_service=session_service
    )
    return session_service, runner

async def call_agent_async(user_input_ticker: str):
    """
    Sends a new topic to the agent (overwriting the initial one if needed)
    and runs the workflow.

    Returns:
        tuple[str, str, dict | None]:
            - final natural-language response from the agent (if any)
            - JSON string representation of the final session state (uploaded to GCS)
            - rating output from the rater agent as a dictionary, if produced
    """

    session_service, runner = await setup_session_and_runner(ticker=user_input_ticker)

    content = types.Content(role='user', parts=[types.Part(text=f"Analysis a stock about: {user_input_ticker}")])
    events = runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content)

    final_response = "No final response captured."
    run_error: str | None = None

    try:
        async for event in events:
            if event.is_final_response() and event.content and event.content.parts:
                logger.info(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
                final_response = event.content.parts[0].text
    except Exception as exc:  # pragma: no cover - defensive logging
        run_error = str(exc)
        logger.error("Agent run failed due to an unexpected error: %s", exc, exc_info=True)

    print("\n--- Agent Interaction Result ---")
    print("Agent Final Response: ", final_response)

    final_session = await session_service.get_session(app_name=APP_NAME, 
                                                user_id=USER_ID, 
                                                session_id=SESSION_ID)
    print("Final Session State:")
    import json
    session_state = final_session.state if final_session else {}
    if isinstance(session_state, dict):
        final_state = dict(session_state)
    else:
        final_state = dict(session_state.items()) if session_state else {}
    def _to_serializable(value):
        if hasattr(value, "model_dump"):
            return _to_serializable(value.model_dump())
        if isinstance(value, dict):
            return {k: _to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_to_serializable(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    final_state = _to_serializable(final_state)

    if final_response and final_response != "No final response captured.":
        final_state["agent_final_response"] = final_response

    raw_rating = final_state.get("rating")
    if hasattr(raw_rating, "model_dump"):
        final_rating = raw_rating.model_dump()
        final_state["rating"] = final_rating
    else:
        final_rating = raw_rating

    if run_error and not final_state.get("agent_run_error"):
        final_state["agent_run_error"] = run_error

    # Upload full session snapshot (partitioned and legacy path retained for compatibility)
    has_error = bool(final_state.get("agent_run_error"))

    gcs_bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
    gcs_manager = GCSManager(bucket_name=gcs_bucket_name) if gcs_bucket_name else GCSManager()

    now = datetime.now(timezone.utc)
    AGENT_STATE_CACHE_PREFIX = "Fundamentals/cache/agent_state"
    partition_prefix = f"{AGENT_STATE_CACHE_PREFIX}/year={now.year}/quarter={(now.month - 1)//3 + 1}"

    # --- ▼▼▼ 기존 업로드 로직을 아래 코드로 대체합니다 ▼▼▼ ---

    if not has_error:
        # 1. 전체 세션 스냅샷 업로드 (파티션 경로 & 레거시 경로)
        state_filename = f"{user_input_ticker}.json"
        state_destinations = [partition_prefix, AGENT_STATE_CACHE_PREFIX]
        _upload_to_destinations(
            gcs_manager,
            payload=final_state,
            base_filename=state_filename,
            destinations=state_destinations
        )

        # 2. 간결한 분석 페이로드 업로드 (버킷 루트 & 파티션 경로)
        analysis_filename = f"{user_input_ticker}_analysis.json"
        saved_timestamp = now.isoformat().replace("+00:00", "Z")
        analysis_payload = _strip_none(
            {
                "ticker": user_input_ticker,
                "saved_at": saved_timestamp,
                "analysis_result": final_state.get("analysis_result"),
                "rating": final_rating,
                "agent_final_response": final_state.get("agent_final_response"),
                "agent_run_error": final_state.get("agent_run_error"),
            }
        )
        # 버킷 루트는 빈 문자열("")로 표현
        analysis_destinations = ["", partition_prefix]
        _upload_to_destinations(
            gcs_manager,
            payload=analysis_payload,
            base_filename=analysis_filename,
            destinations=analysis_destinations
        )

    final_result = json.dumps(final_state, indent=2, ensure_ascii=False, default=str)
    print(final_result)
    if final_rating:
        print("\nRating Result:")
        print(json.dumps(final_rating, indent=2, ensure_ascii=False))
    print("-------------------------------\n")
    return final_response, final_result, final_rating
