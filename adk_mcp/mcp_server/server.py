from pathlib import Path
import sys

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.fnguide import Fundamentals as FnGuideFundamentals
from utils.yahoofinance import Fundamentals as YahooFundamentals
import pandas as pd
import json

mcp = FastMCP(name="StockFundamentalsServer")

@mcp.tool(
    name="find_fnguide_data",
    description="Fetch Korean stock fundamentals data from FnGuide for a given Korea stock code.",
    tags={"finance", "stocks", "fundamentals", "korea"}
)
def fetch_fnguide_data(stock: str):
    return FnGuideFundamentals(stock).fundamentals()


@mcp.tool(
    name="find_yahoofinance_data",
    description=(
        "Fetch fundamentals data for a given company from Yahoo Finance."
        "The attribute parameter should match yfinance.Ticker attribute names "
        "such as 'income_stmt', 'balance_sheet', or 'cashflow'."
    ),
    tags={"finance", "stocks", "fundamentals", "global"}
)
def fetch_yahoofinance_data(query: str, attribute: str):
    data = YahooFundamentals().fundamentals(query=query, attribute_name_str=attribute)

    if isinstance(data, pd.DataFrame):
        return json.loads(data.to_json(orient="records", date_format="iso"))
    if isinstance(data, pd.Series):
        return data.to_dict()
    if isinstance(data, dict):
        return data
    return data

if __name__ == "__main__":
    mcp.run()
