from pathlib import Path
import sys
from typing import Any
from decimal import Decimal

import numpy as np
import pandas as pd

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.gcpmanager import GCSManager, BQManager
from utils.yahoofinance import fetch_market_dataframe as fetch_yahoo_market_dataframe
from utils.naverfinance import fetch_market_dataframe as fetch_naver_market_dataframe

mcp = FastMCP(name="GCloudServer")

MARKET_SCHEMA_COLUMNS = [
    "company_id",
    "company_name",
    "exchange",
    "currency",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "change",
    "change_percent",
    "turnover",
    "market_cap",
    "sector",
    "source",
]


def _prepare_market_dataframe(df: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    prepared_df = df.copy()

    prepared_df["date"] = pd.to_datetime(prepared_df["date"], errors="coerce")
    prepared_df.dropna(subset=["date"], inplace=True)

    for price_column in ["open", "high", "low", "close"]:
        if price_column in prepared_df.columns:
            prepared_df[price_column] = pd.to_numeric(prepared_df[price_column], errors="coerce")

    if "volume" in prepared_df.columns:
        prepared_df["volume"] = pd.to_numeric(prepared_df["volume"], errors="coerce")
    else:
        prepared_df["volume"] = np.nan

    if "adj_close" in prepared_df.columns:
        prepared_df["adj_close"] = pd.to_numeric(prepared_df["adj_close"], errors="coerce")
    elif "Adj Close" in prepared_df.columns:
        prepared_df["adj_close"] = pd.to_numeric(prepared_df["Adj Close"], errors="coerce")
    else:
        prepared_df["adj_close"] = prepared_df.get("close")

    prepared_df.sort_values(["date"], inplace=True)

    prepared_df["company_id"] = metadata.get("company_id")
    prepared_df["company_name"] = metadata.get("company_name")
    prepared_df["exchange"] = metadata.get("exchange")
    prepared_df["currency"] = metadata.get("currency")
    prepared_df["sector"] = metadata.get("sector")
    prepared_df["source"] = metadata.get("source")

    if prepared_df["company_id"].isna().all():
        prepared_df["company_id"] = metadata.get("company_name")

    prepared_df.sort_values(["company_id", "date"], inplace=True)

    prepared_df["change"] = prepared_df.groupby("company_id")["close"].diff()
    prev_close = prepared_df.groupby("company_id")["close"].shift(1)
    prepared_df["change_percent"] = prepared_df["change"] / prev_close
    prepared_df.loc[~np.isfinite(prepared_df["change_percent"]), "change_percent"] = np.nan
    prepared_df["turnover"] = prepared_df["close"] * prepared_df["volume"]

    prepared_df["change"] = prepared_df["change"].round(6)
    prepared_df["change_percent"] = prepared_df["change_percent"].round(6)

    prepared_df["volume"] = prepared_df["volume"].round().astype("Int64")
    prepared_df["turnover"] = prepared_df["turnover"].round(6)
    for price_column in ["open", "high", "low", "close", "adj_close"]:
        if price_column in prepared_df.columns:
            prepared_df[price_column] = prepared_df[price_column].round(6)

    shares_outstanding = metadata.get("shares_outstanding")
    shares_outstanding_value: float | None
    try:
        shares_outstanding_value = float(shares_outstanding) if shares_outstanding is not None else None
    except (TypeError, ValueError):
        shares_outstanding_value = None
    if shares_outstanding_value is not None and np.isfinite(shares_outstanding_value) and shares_outstanding_value > 0:
        prepared_df["market_cap"] = prepared_df["close"] * shares_outstanding_value
    else:
        prepared_df["market_cap"] = metadata.get("market_cap")

    if "market_cap" in prepared_df.columns:
        prepared_df["market_cap"] = pd.to_numeric(prepared_df["market_cap"], errors="coerce")
        prepared_df["market_cap"] = prepared_df["market_cap"].round(6)

    prepared_df["date"] = prepared_df["date"].dt.date

    prepared_df = prepared_df.reindex(columns=MARKET_SCHEMA_COLUMNS)

    decimal_scale_map = {
        "open": 6,
        "high": 6,
        "low": 6,
        "close": 6,
        "adj_close": 6,
        "change": 6,
        "turnover": 6,
    }

    integer_decimal_columns = {"market_cap"}

    def _to_decimal(value: Any, places: int | None) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, float) and np.isnan(value):
            return None
        if places is None:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return None
            if not np.isfinite(numeric_value):
                return None
            return Decimal(str(int(round(numeric_value))))
        formatted = f"{float(value):.{places}f}"
        return Decimal(formatted)

    for column, scale in decimal_scale_map.items():
        if column in prepared_df.columns:
            prepared_df[column] = prepared_df[column].apply(lambda v: _to_decimal(v, scale))

    for column in integer_decimal_columns:
        if column in prepared_df.columns:
            prepared_df[column] = prepared_df[column].apply(lambda v: _to_decimal(v, None))

    prepared_df = prepared_df.dropna(subset=["date"])

    return prepared_df

@mcp.tool(
    name="list_gcs_files",
    description="Lists files in a specified Google Cloud Storage folder.",
    tags={"gcs", "storage"}
)
def list_gcs_files(folder_name: str | None = None):
    """
    folder_name: The folder path in the GCS bucket to list files from.
    """
    gcs_manager = GCSManager()
    return gcs_manager.list_files(folder_name=folder_name)

@mcp.tool(
    name="read_gcs_file",
    description="Reads a file from Google Cloud Storage.",
    tags={"gcs", "storage"}
)
def read_gcs_file(blob_name: str):
    """
    blob_name: The full path to the file in the GCS bucket.
    """
    gcs_manager = GCSManager()
    return gcs_manager.read_file(blob_name=blob_name)

@mcp.tool(
    name="fetch_and_save_market_data_to_bq",
    description="Fetches raw market data and saves it to the 'sayouzone-ai.stocks_silver.market' BigQuery table.",
    tags={"gcs", "market", "storage", "bigquery"}
)
async def fetch_and_save_market_data_to_bq(site: str, company: str, start_date: str, end_date: str):
    """
    site: 'naver' or 'yahoo'
    company: company name or ticker/code
    start_date: YYYY-MM-DD
    end_date: YYYY-MM-DD
    """
    site_normalized = site.lower()

    if site_normalized == 'yahoo':
        raw_df, metadata = await fetch_yahoo_market_dataframe(company, start_date, end_date)
        default_source = "Yahoo"
    elif site_normalized == 'naver':
        raw_df, metadata = await fetch_naver_market_dataframe(company, start_date, end_date)
        default_source = "Naver"
    else:
        raise ValueError("Site must be 'naver' or 'yahoo'.")

    if raw_df.empty:
        return "No data found to save."

    metadata = metadata or {}
    metadata.setdefault("source", default_source)
    if not metadata.get("company_id") and metadata.get("company_name"):
        metadata["company_id"] = metadata["company_name"]
    if not metadata.get("company_name") and metadata.get("company_id"):
        metadata["company_name"] = metadata["company_id"]

    df_to_load = _prepare_market_dataframe(raw_df, metadata)

    if df_to_load.empty:
        return "No data found to save."

    bq_manager = BQManager()
    success = bq_manager.load_dataframe(
        df=df_to_load,
        table_id="sayouzone-ai.stocks_silver.market",
        if_exists="append"
    )

    if success:
        return f"Successfully loaded {len(df_to_load)} rows to sayouzone-ai.stocks_silver.market"
    else:
        raise Exception("Failed to load data to BigQuery.")

if __name__ == "__main__":
    mcp.run()

@mcp.tool(
    name="save_data_to_bq",
    description="Saves a list of dictionaries to a specified BigQuery table.",
    tags={"bigquery", "storage"}
)
def save_data_to_bq(data: list[dict], table_id: str, if_exists: str = "append"):
    """
    Saves data to a BigQuery table.

    Args:
        data: A list of dictionaries, where each dictionary represents a row.
        table_id: The ID of the BigQuery table (e.g., 'project.dataset.table').
        if_exists: What to do if the table already exists ('append' or 'replace'). Defaults to 'append'.
    """
    if not data:
        return "No data provided to save."

    df = pd.DataFrame(data)
    bq_manager = BQManager()
    
    success = bq_manager.load_dataframe(
        df=df,
        table_id=table_id,
        if_exists=if_exists
    )

    if success:
        return f"Successfully loaded {len(df)} rows to {table_id}"
    else:
        raise Exception(f"Failed to load data to BigQuery table {table_id}")
