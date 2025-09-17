import os

import logging

from typing import Dict, List, Union, Optional, Literal, AsyncGenerator, Any
from typing_extensions import override

from google.adk.agents import LlmAgent, LoopAgent, BaseAgent
from google.adk.planners import BuiltInPlanner
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event
from pydantic import BaseModel, Field

from stock_agent.tools import fundamentals_mcp_tool
from stock_agent.prompt import fetch_fundamentals_data_instructions
from google.adk.tools import google_search
from tavily import TavilyClient

full_instruction = fetch_fundamentals_data_instructions()

# --- Constants ---
APP_NAME = "fundamentals_analysis_app"
USER_ID = "12345"
SESSION_ID = "123344"
THINKING_MODEL = "gemini-2.5-pro"

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FundamentalsData(BaseModel):
    ticker: str = Field(description="The stock ticker symbol of the company.")
    country: str = Field(description="The country where the company is listed.")
    balance_sheet: Optional[str] = Field(default=None, description="The company's balance sheet data.")
    income_statement: Optional[str] = Field(default=None, description="The company's income statement data.")
    cash_flow: Optional[str] = Field(default=None, description="The company's cash flow statement data.")
    profitability : Optional[str] = Field(default=None, description="The company's profitability metrics.")
    stability : Optional[str] = Field(default=None, description="The company's financial stability metrics.")
    growth : Optional[str] = Field(default=None, description="The company's growth metrics.")
    economic_moat : Optional[str] = Field(default=None, description="The company's economic moat assessment.")
    management_capability : Optional[str] = Field(default=None, description="The company's management capability evaluation.")
    industry_macro_environment : Optional[str] = Field(default=None, description="The industry and macroeconomic environment overview.")
    
class AnalysisResult(BaseModel):
    ticker : str = Field(description="The stock ticker symbol of the company.")
    country : str = Field(description="The country where the company is listed.")
    balance_sheet: str = Field(description="Summary of the company's balance sheet.")
    income_statement: str = Field(description="Summary of the company's income statement.")
    cash_flow: str = Field(description="Summary of the company's cash flow statement.")
    profitability : str = Field(description="Analysis of the company's profitability.")
    stability : str = Field(description="Analysis of the company's financial stability.")
    growth : str = Field(description="Analysis of the company's growth potential.")
    economic_moat : str = Field(description="Assessment of the company's economic moat.")
    management_capability : str = Field(description="Evaluation of the company's management capability.")
    industry_macro_environment : str = Field(description="Overview of the industry and macroeconomic environment.")

analysis_result_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "ticker": types.Schema(type=types.Type.STRING),
        "country": types.Schema(type=types.Type.STRING),
        "balance_sheet": types.Schema(type=types.Type.STRING),
        "income_statement": types.Schema(type=types.Type.STRING),
        "cash_flow": types.Schema(type=types.Type.STRING),
        "profitability": types.Schema(type=types.Type.STRING),
        "stability": types.Schema(type=types.Type.STRING),
        "growth": types.Schema(type=types.Type.STRING),
        "economic_moat": types.Schema(type=types.Type.STRING),
        "management_capability": types.Schema(type=types.Type.STRING),
        "industry_macro_environment": types.Schema(type=types.Type.STRING),
    },
    required=[
        "ticker",
        "country",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "profitability",
        "stability",
        "growth",
        "economic_moat",
        "management_capability",
        "industry_macro_environment",
    ],
)

def tavily_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    search_depth: Literal["basic", "advanced"] = "basic",
    max_results: int = 5,
    include_answer: Literal["none", "basic", "advanced"] = "basic",
    raw_content: Literal["none", "markdown", "text"] = "none",
    include_images: bool = False,
    include_image_descriptions: bool = False,
    # 시간/범위 필터 (SDK가 제공하는 옵션)
    days: Optional[int] = None,                 # topic="news"일 때만 의미 있음
    time_range: Optional[Literal["day", "week", "month", "year", "d", "w", "m", "y"]] = None,
    start_date: Optional[str] = None,           # YYYY-MM-DD
    end_date: Optional[str] = None,             # YYYY-MM-DD
    # 도메인 화이트/블랙리스트
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    country: Optional[str] = None,              # topic="general"에서 우선순위 부스팅
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Tavily Search API를 호출하는 ADK Function Tool.
    ADK는 이 함수 시그니처/도크스트링을 읽어 자동으로 Tool 스키마를 생성해요.

    Args:
        query: 질의문(필수).
        topic: "general" | "news" | "finance".
        search_depth: "basic" | "advanced".
        max_results: 0~20.
        include_answer: "none" | "basic" | "advanced".
        raw_content: "none" | "markdown" | "text".
        include_images: 이미지 URL 포함 여부.
        include_image_descriptions: 이미지 설명 포함 여부.
        days/time_range/start_date/end_date: 신선도/기간 필터(뉴스에 유용).
        include_domains/exclude_domains: 도메인 필터링.
        country: 특정 국가 우선순위(일반 검색 전용).
        timeout: 요청 타임아웃(초).

    Returns:
        dict: {status, query, answer?, results, images?, request_id, tips?}
              - results: [{title, url, score, published_date?, snippet}]
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "error_message": "환경변수 TAVILY_API_KEY가 설정되어 있지 않습니다.",
            "tip": "export TAVILY_API_KEY='tvly-***' 형태로 설정하세요.",
        }

    client = TavilyClient(api_key=api_key)

    # Tavily SDK 파라미터 구성 (문서 기준)
    params: Dict[str, Any] = {
        "query": query,
        "topic": topic,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": include_answer if include_answer != "none" else False,
        "include_raw_content": False if raw_content == "none" else raw_content,
        "include_images": include_images,
        "include_image_descriptions": include_image_descriptions,
        "timeout": timeout,
    }

    # 선택 파라미터만 주입
    if include_domains:
        params["include_domains"] = include_domains
    if exclude_domains:
        params["exclude_domains"] = exclude_domains
    if country:
        params["country"] = country

    # 기간 관련: 문서에 따라 news 토픽에서 days 사용, time_range/start/end도 지원
    if days is not None:
        params["days"] = days
    if time_range is not None:
        params["time_range"] = time_range
    if start_date is not None:
        params["start_date"] = start_date
    if end_date is not None:
        params["end_date"] = end_date

    try:
        resp: Dict[str, Any] = client.search(**params)
    except Exception as e:
        return {"status": "error", "error_message": f"Tavily 호출 실패: {e!s}"}

    # 결과 축약/정돈(LLM이 쓰기 쉬운 형태)
    results = []
    for r in resp.get("results", []):
        results.append(
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "score": r.get("score"),
                "published_date": r.get("published_date"),
                "snippet": (r.get("content") or "")[:500],
            }
        )

    out: Dict[str, Any] = {
        "status": "success",
        "query": resp.get("query", query),
        "results": results,
        "request_id": resp.get("request_id"),
    }
    if "answer" in resp:
        out["answer"] = resp["answer"]
    if "images" in resp:
        out["images"] = resp["images"]

    # 사용 팁(뉴스일 때 days/time_range 권장 등)
    tips = []
    if topic == "news" and days is None and time_range is None and (start_date is None and end_date is None):
        tips.append("속보성 검색이면 days=1~7 또는 time_range='week'를 고려하세요.")
    if search_depth == "basic":
        tips.append("정밀도가 필요하면 search_depth='advanced'를 사용하세요.")
    if tips:
        out["tips"] = tips

    return out

def tavily_extract(
    urls: List[str],
    extract_depth: Literal["basic", "advanced"] = "basic",
    format: Literal["markdown", "text"] = "markdown",
    include_images: bool = False,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Tavily Extract API로 URL 본문을 구조화해서 추출하는 도구.

    Args:
        urls: 단일 URL 또는 URL 리스트(최대 20개).
        extract_depth: "basic"|"advanced" (advanced가 더 풍부하지만 느릴 수 있음).
        format: "markdown"|"text".
        include_images: 이미지 URL 포함 여부.
        timeout: 초 단위 타임아웃(없으면 기본값).

    Returns:
        dict: {status, results, failed_results, request_id}
              - results: [{url, raw_content, images?, favicon?}]
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "error_message": "환경변수 TAVILY_API_KEY가 설정되어 있지 않습니다.",
        }

    if isinstance(urls, str):  # allow single URL inputs gracefully
        urls = [urls]

    client = TavilyClient(api_key=api_key)

    try:
        resp = client.extract(
            urls=urls,
            extract_depth=extract_depth,
            format=format,
            include_images=include_images,
            timeout=timeout,
        )
    except Exception as e:
        return {"status": "error", "error_message": f"Tavily Extract 호출 실패: {e!s}"}

    return {"status": "success", **resp}

class FundamentalsAnalysisAgent(BaseAgent):
    """
    Custom agent for a company fundamentals analysis and refinement workflow.

    This agent orchestrates a sequence of LLM agents to company fundamentals analysis, 
    review it, revise it, and output for json.
    """
    country_finder: LlmAgent
    fundamentals_fetcher: LlmAgent
    analyst: LlmAgent
    reviewer: LlmAgent
    reviser: LlmAgent

    loop_agent: LoopAgent

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
            self,
            name: str,
            country_finder: LlmAgent,
            fundamentals_fetcher: LlmAgent,
            analyst: LlmAgent,
            reviewer: LlmAgent,
            reviser: LlmAgent,
    ):
        """
        Initializes the FundamentalsAnalysisAgent.

        Args:
            name: The name of the agent.
            analyst: An LlmAgent to analyze the fundamentals of a company.
            reviewer: An LlmAgent to review the analysis result.
            reviser: An LlmAgent to revise the analysis result based on commentary.
        """

        # Create internal agents *before* calling super().__init__
        loop_agent = LoopAgent(
            name="ReviewerReviserLoop", sub_agents=[reviewer, reviser], max_iterations=3
        )

        sub_agents_list = [
            country_finder,
            fundamentals_fetcher,
            analyst,
            loop_agent
        ]

        super().__init__(
            name=name,
            country_finder=country_finder,
            fundamentals_fetcher=fundamentals_fetcher,
            analyst=analyst,
            reviewer=reviewer,
            reviser=reviser,
            loop_agent=loop_agent,
            sub_agents=sub_agents_list,
        )
    
    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Implements the custom orchestration logic for the company fundamentals analysis workflow.
        Uses the instance attributes assigned by Pydantic (e.g., self.analyst).
        """
        logger.info(f"[{self.name}]")

        # 1. Initial Country Finding
        logger.info(f"[{self.name}] Running CountryFinder...")
        async for event in self.country_finder.run_async(ctx):
            logger.info(f"[{self.name}] Event from CountryFinder: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event
        
        # Check if analysis result before proceeding
        if "stock_country" not in ctx.session.state or not ctx.session.state["stock_country"]:
            logger.warning(f"[{self.name}] No stock_country found in context after CountryFinder. Exiting.")
            return

        logger.info(f"[{self.name}]")

        # 2. Fetch Fundamentals Data
        logger.info(f"[{self.name}] Running FundamentalsFetcher...")
        async for event in self.fundamentals_fetcher.run_async(ctx):
            logger.info(f"[{self.name}] Event from FundamentalsFetcher: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        # Check if fundamentals data before proceeding
        if "fundamentals_data" not in ctx.session.state or not ctx.session.state["fundamentals_data"]:
            logger.warning(f"[{self.name}] No fundamentals_data found in context after FundamentalsFetcher. Exiting.")
            return

        logger.info(f"[{self.name}]")

        # 3. Initial Analysis
        logger.info(f"[{self.name}] Running Analyst...")
        async for event in self.analyst.run_async(ctx):
            logger.info(f"[{self.name}] Event from Analyst: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event
        
        # Check if analysis result before proceeding
        if "analysis_result" not in ctx.session.state or not ctx.session.state["analysis_result"]:
            logger.warning(f"[{self.name}] No analysis_result found in context after Analyst. Exiting.")
            return
        
        logger.info(f"[{self.name}]")

        # 4. Review and Revise Loop
        logger.info(f"[{self.name}] Running ReviewerReviserLoop...")
        async for event in self.loop_agent.run_async(ctx):
            logger.info(f"[{self.name}] Event from ReviewerReviserLoop: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event
        
        logger.info(f"[{self.name}] Completed all steps.")

country_finder = LlmAgent(
    model = "gemini-2.5-flash",
    name = "CountryFinder",
    instruction="""
    You are an expert in stock markets and ticker symbols. 
    Your task is to identify the country associated with a given stock ticker symbol from a user's query. 
    Use the provided tool to look up the ticker symbol in a google search and return the corresponding country. 
    If the ticker symbol is not found, respond with 'Unknown'.
    Example:
    User Query: "PSTG"
    Response: "United States"

    User Query: "005930"
    Response: "Korea"
    """,
    description="Determines which country's stock the ticker symbol corresponds to in the user's query.",
    tools=[google_search],
    output_key="stock_country"
)

fundamentals_fetcher = LlmAgent(
    model = "gemini-2.5-flash",
    name = "FundamentalsFetcher",
    description="""
    Fetches comprehensive fundamentals data for a specified stock ticker and country.
    """,
    instruction=full_instruction,
    output_schema=FundamentalsData,
    output_key="fundamentals_data",
    tools=[fundamentals_mcp_tool, tavily_search, tavily_extract]
)

analyst = LlmAgent(
    model=THINKING_MODEL,
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=1024,
        ),
    ),
    name="Analyst",
    generate_content_config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=analysis_result_schema,
    ),
    instruction="""
    You are a seasoned financial analyst.
    Your task is to analyze the provided: {{fundamentals_data}}.
    Deliver a comprehensive analysis covering:
    - Balance Sheet
    - Income Statement
    - Cash Flow
    - Profitability
    - Stability
    - Growth
    - Economic Moat
    - Management Capability
    - Industry & Macro Environment

    Output MUST be a single valid JSON object matching this schema:
    {
      "ticker": "...",
      "country": "...",
      "balance_sheet": "...",
      "income_statement": "...",
      "cash_flow": "...",
      "profitability": "...",
      "stability": "...",
      "growth": "...",
      "economic_moat": "...",
      "management_capability": "...",
      "industry_macro_environment": "..."
    }

    Rules:
    - Fill every field with a concise, well-supported narrative paragraph.
    - Do not emit markdown, bullet lists, or code fences.
    - Do not include trailing comments or additional text outside the JSON object.
    """,
    input_schema=FundamentalsData,
    output_schema=AnalysisResult,
    output_key="analysis_result"
)

reviewer = LlmAgent(
    model=THINKING_MODEL,
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=512,
        ),
    ),
    name="Reviewer",
    instruction="""
    You are a meticulous financial analyst.
    Your task is to review the provided: {{fundamentals_data}}, {{analysis_result}}.
    Identify any gaps, inconsistencies, or areas that need further clarification or evidence.
    Provide constructive feedback and specific suggestions for improvement.
    """,
    input_schema=AnalysisResult,
    output_key="review_comments"
)

reviser = LlmAgent(
    model=THINKING_MODEL,
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=512,
        ),
    ),
    name="Reviser",
    instruction="""
    You are a skilled financial analyst.
    Your task is to revise the provided: {{fundamentals_data}}, {{analysis_result}} based on the review comments: {{review_comments}}.
    Address each comment with specific improvements, additional evidence, or clarifications as needed.
    Ensure the revised analysis is comprehensive, accurate, and well-supported.
    """,
    input_schema=AnalysisResult,
    output_key="analysis_result"
)

fundamentals_analysis_agent = FundamentalsAnalysisAgent(
    name="FundamentalsAnalysisAgent",
    country_finder=country_finder,
    fundamentals_fetcher=fundamentals_fetcher,
    analyst=analyst,
    reviewer=reviewer,
    reviser=reviser,
)

# FastMCP 및 ADK 로더가 찾을 수 있도록 루트 에이전트 별칭을 노출한다.
root_agent = fundamentals_analysis_agent

INITIAL_STATE = {"ticker": "005930"}

async def setup_session_and_runner():
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, state=INITIAL_STATE)
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
    """

    session_service, runner = await setup_session_and_runner()

    current_session = await session_service.get_session(app_name=APP_NAME, 
                                                  user_id=USER_ID, 
                                                  session_id=SESSION_ID)
    if not current_session:
        logger.error("Session not found!")
        return

    current_session.state["ticker"] = user_input_ticker
    logger.info(f"Updated session state topic to: {user_input_ticker}")

    content = types.Content(role='user', parts=[types.Part(text=f"Generate a story about: {user_input_ticker}")])
    events = runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content)

    final_response = "No final response captured."
    async for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            logger.info(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
            final_response = event.content.parts[0].text

    print("\n--- Agent Interaction Result ---")
    print("Agent Final Response: ", final_response)

    final_session = await session_service.get_session(app_name=APP_NAME, 
                                                user_id=USER_ID, 
                                                session_id=SESSION_ID)
    print("Final Session State:")
    import json
    print(json.dumps(final_session.state, indent=2))
    print("-------------------------------\n")
