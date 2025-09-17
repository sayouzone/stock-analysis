from google.cloud import bigquery
import json
import os

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)

GOOGLE_CLOUD_PROJECT = "sayouzone-ai"

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
    tool_filter=['find_fnguide_data'],
)
