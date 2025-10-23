from google.cloud import bigquery
import json
import os
import logging
import pathlib
from typing import Any, Optional, List

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)

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

# Get the project root directory (parent of stock_agent)
_project_root = pathlib.Path(__file__).parent.parent
_mcp_server_path = _project_root / "mcp_server" / "server.py"

fundamentals_mcp_tool = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params = StdioServerParameters(
            command='fastmcp',
            args=['run', f"{_mcp_server_path}:mcp", "--project", str(_project_root)],
        ),
        timeout=30,
    ),
    tool_filter=[
        'find_fnguide_data',
        'find_yahoofinance_data',
        'get_yahoofinance_fundamentals',  # 재무제표 3종 자동 수집
        'save_fundamentals_data_to_gcs'
    ],
)

_market_mcp_path = _project_root / "mcp_server" / "market.py"

market_mcp_tool = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command='fastmcp',
            args=['run', f"{_market_mcp_path}:mcp", "--project", str(_project_root)],
        ),
        timeout=30,
    ),
    tool_filter=['collect_market_data', 'process_market_data', 'save_market_data_to_gcs'],
)

_gcloud_mcp_path = _project_root / "mcp_server" / "gcloud.py"

gcloud_mcp_tool = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command='fastmcp',
            args=['run', f"{_gcloud_mcp_path}:mcp", "--project", str(_project_root)],
        ),
        timeout=60,  # Increased timeout for potentially long-running cloud operations
    ),
    tool_filter=['list_gcs_files', 'read_gcs_file', 'fetch_and_save_market_data_to_bq', 'save_data_to_bq'],
)