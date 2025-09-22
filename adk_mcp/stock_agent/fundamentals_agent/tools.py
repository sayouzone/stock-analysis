from google.cloud import bigquery
import json
import os
import logging
from typing import Any, Optional, List

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)

from utils.websearchtool import BraveExaHybridWebToolset

GOOGLE_CLOUD_PROJECT = "sayouzone-ai"
logger = logging.getLogger(__name__)

def clean_sql_query(text):
    return (
        text.replace("\\n", " ")
        .replace("\n", " ")
        .replace("\\", "")
        .replace("```sql", "")
        .replace("```", "")
        .strip()
    )

def execute_bigquery_sql(sql: str) -> str:
    """Executes a BigQuery SQL query and returns the result as a JSON string."""
    print(f"Executing BigQuery SQL query: {sql}")
    cleaned_sql = clean_sql_query(sql)
    print(f"Cleaned SQL query: {cleaned_sql}")
    try:
        # The client uses the GOOGLE_CLOUD_PROJECT environment variable.
        client = bigquery.Client(project=GOOGLE_CLOUD_PROJECT)
        query_job = client.query(cleaned_sql)  # Make an API request.
        results = query_job.result()  # Wait for the job to complete.

        # Convert RowIterator to a list of dictionaries
        sql_results = [dict(row) for row in results]

        # Return the results as a JSON string.
        if not sql_results:
            return "Query returned no results."
        else:
            # Use json.dumps for proper JSON formatting, handle non-serializable
            # types like datetime
            return (
                json.dumps(sql_results, default=str)
                .replace("```sql", "")
                .replace("```", "")
            )
    except Exception as e:
        return f"Error executing BigQuery query: {str(e)}"

fundamentals_mcp_tool = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params = StdioServerParameters(
            command='fastmcp',
            args=['run', "mcp_server/server.py:mcp", "--project", "."],
        ),
        timeout=30,
    ),
    tool_filter=['find_fnguide_data', 'find_yahoofinance_data'],
)


try:
    _hybrid_toolset = BraveExaHybridWebToolset()
    WEB_SEARCH_TOOL_AVAILABLE = True
except Exception as exc:  # pragma: no cover - defensive logging
    logger.warning("Hybrid web search tool unavailable: %s", exc)
    _hybrid_toolset = None
    WEB_SEARCH_TOOL_AVAILABLE = False


def hybrid_web_search(
    query: str,
    top_k: int = 10,
    brave_kinds: Optional[List[str]] = None,
    brave_each_k: int = 8,
    exa_k: int = 8,
    exa_type: str = "auto",
    fuse_w_brave: float = 1.0,
    fuse_w_exa: float = 1.2,
    enrich_with_exa_contents: bool = True,
    enrich_limit: int = 5,
    lang: str = "ko",
    country: str = "kr"
) -> dict[str, Any]:
    """
    Brave(메인) + Exa(보강) 하이브리드 검색
    - Brave: 다양한 vertical(웹/뉴스/이미지/비디오)
    - Exa: 의미 기반 보강 검색
    - RRF 결합으로 최종 top_k 선정
    - (옵션) Exa contents로 상위 N개 요약/텍스트 취합
    """
    if _hybrid_toolset is None:
        return {"status": "error", "error": "Hybrid web search tool is not configured."}
    return _hybrid_toolset.hybrid_web_search(
        query=query,
        top_k=top_k,
        brave_kinds=brave_kinds,
        brave_each_k=brave_each_k,
        exa_k=exa_k,
        exa_type=exa_type,
        fuse_w_brave=fuse_w_brave,
        fuse_w_exa=fuse_w_exa,
        enrich_with_exa_contents=enrich_with_exa_contents,
        enrich_limit=enrich_limit,
        lang=lang,
        country=country
    )


def brave_raw_search(
    query: str,
    kind: str = "web",
    count: int = 10,
    country: str = "kr",
    lang: str = "ko"
) -> dict[str, Any]:
    """
    Brave 단일 엔드포인트 검색
    kind: web | news | images | videos
    """
    if _hybrid_toolset is None:
        return {"status": "error", "error": "Hybrid web search tool is not configured."}
    return _hybrid_toolset.brave_raw(
        query=query,
        kind=kind,
        count=count,
        country=country,
        lang=lang
    )
