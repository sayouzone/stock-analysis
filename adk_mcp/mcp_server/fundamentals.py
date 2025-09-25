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
from utils.gcpmanager import GCSManager

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

@mcp.tool(
    name="save_fundamentals_data_to_gcs",
    description="Saves fundamentals data to a CSV file in Google Cloud Storage.",
    tags={"gcs", "fundamentals", "storage"}
)
def save_fundamentals_data_to_gcs(fundamentals_data: dict | list, gcs_path: str, file_name: str):
    """
    fundamentals_data: The JSON-like object returned from fetch_fnguide_data or fetch_yahoofinance_data.
    gcs_path: The destination folder path in the GCS bucket.
    file_name: The name of the CSV file.
    """
    if not fundamentals_data:
        raise ValueError("fundamentals_data cannot be empty.")

    if isinstance(fundamentals_data, list):
        df = pd.DataFrame(fundamentals_data)
    elif isinstance(fundamentals_data, dict):
        df = pd.DataFrame([fundamentals_data])
    else:
        raise TypeError("fundamentals_data must be a dict or a list of dicts.")

    csv_data = df.to_csv(index=False)

    gcs_manager = GCSManager()
    destination_blob_name = f"{gcs_path}/{file_name}"
    
    success = gcs_manager.upload_file(
        source_file=csv_data,
        destination_blob_name=destination_blob_name,
        content_type="text/csv"
    )

    if success:
        return f"Successfully saved fundamentals data to gs://{gcs_manager.bucket_name}/{destination_blob_name}"
    else:
        raise Exception("Failed to upload file to GCS.")
