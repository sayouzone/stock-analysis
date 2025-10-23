from pathlib import Path
import sys
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types

from stock_agent.tools import (
    fundamentals_mcp_tool,
    market_mcp_tool,
    gcloud_mcp_tool,
)

# --- Planner Configuration ---
DEFAULT_THINKING_MODEL = "gemini-2.5-flash"
THINKING_MODEL = os.getenv("DATA_AGENT_THINKING_MODEL", DEFAULT_THINKING_MODEL)

def _supports_thinking(model_name: str) -> bool:
    overridden = os.getenv("DATA_AGENT_FORCE_THINKING")
    if overridden:
        return overridden.lower() in {"1", "true", "yes", "on"}
    name = model_name.lower()
    if "flash" in name and "thinking" not in name:
        return False
    return True

SUPPORTS_THINKING = _supports_thinking(THINKING_MODEL)
DEFAULT_THINKING_BUDGET = "256"
THINKING_BUDGET = int(os.getenv("DATA_AGENT_THINKING_BUDGET", DEFAULT_THINKING_BUDGET))

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

# Combine all the MCP toolsets into a single list of tools for the agent
ALL_DATA_TOOLS = [
    fundamentals_mcp_tool,
    market_mcp_tool,
    gcloud_mcp_tool,
]

# Define the instructions for the new agent
DATA_AGENT_INSTRUCTIONS = """
You are an expert data agent for stock market information.
Your goal is to fulfill user requests by calling a sequence of tools.

You have tools to:
1.  Fetch market data (`collect_market_data`).
2.  Fetch fundamental data (`find_fnguide_data`, `find_yahoofinance_data`).
3.  Save data to Google Cloud Storage (`save_market_data_to_gcs`, `save_fundamentals_data_to_gcs`).
4.  Save data to BigQuery (`fetch_and_save_market_data_to_bq`, `save_data_to_bq`).
5.  List and read files from GCS (`list_gcs_files`, `read_gcs_file`).

**IMPORTANT**: You must chain tools together. For example, to fulfill a request like "save the market data for AAPL to a file", you must first call `collect_market_data` and then use the output of that tool as the input for `save_market_data_to_gcs`.

Think step-by-step and use the tools to achieve the user's goal.
"""

# Create the LlmAgent instance
StockDataAgent = LlmAgent(
    model="gemini-2.5-flash",
    planner=_make_planner(THINKING_BUDGET),
    name="StockDataAgent",
    description="An agent for fetching, processing, and storing stock market data.",
    instruction=DATA_AGENT_INSTRUCTIONS,
    tools=ALL_DATA_TOOLS,
    output_key="data_agent_result",
)

# Expose the agent for the ADK loader
root_agent = StockDataAgent
