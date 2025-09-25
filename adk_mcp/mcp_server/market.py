from pathlib import Path
import sys
import asyncio

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.naverfinance import Market as NaverMarket
from utils.yahoofinance import Market as YahooMarket
from utils.companydict import companydict as find
import pandas as pd
from utils.gcpmanager import GCSManager

mcp = FastMCP(name="StockMarketServer")

async def _get_market_data(site, company, start_date=None, end_date=None, fn="collect"):
    if site.lower() == "naver":
        service_module = NaverMarket()
        ticker = find.get_code(company) or company
    elif site.lower() == "yahoo":
        service_module = YahooMarket()
        ticker = find.get_ticker(company) or company
    else:
        raise ValueError(f"Site {site} not found.")

    if not ticker:
        raise ValueError(f"Stock {company} not found.")

    handler = getattr(service_module, f"market_{fn}", None)
    if not handler or not callable(handler):
        raise ValueError(f"Function market_{fn} not available for {site}.")

    kwargs = {"company": ticker}
    if start_date and fn == "collect":
        kwargs["start_date"] = start_date
    if end_date and fn == "collect":
        kwargs["end_date"] = end_date

    final_result = None
    # The handlers are async generators. We need to iterate through them.
    async for event in handler(**kwargs):
        if event.get("type") == "result":
            final_result = event.get("data")
        elif event.get("type") == "error":
            raise Exception(event.get("message"))
            
    return final_result

@mcp.tool(
    name="collect_market_data",
    description="Collect market data (price, volume, etc.) for a given stock. Use 'naver' for Korean stocks and 'yahoo' for overseas stocks.",
    tags={"finance", "stocks", "market", "korea", "global"}
)
async def collect_market_data(site: str, company: str, start_date: str | None = None, end_date: str | None = None):
    """
    site: 'naver' or 'yahoo'
    company: company name or ticker/code
    start_date: YYYY-MM-DD
    end_date: YYYY-MM-DD
    """
    return await _get_market_data(site, company, start_date, end_date, fn="collect")

@mcp.tool(
    name="process_market_data",
    description="Process cached market data for a given stock from either Naver Finance or Yahoo Finance.",
    tags={"finance", "stocks", "market", "korea", "global"}
)
async def process_market_data(site: str, company: str):
    """
    site: 'naver' or 'yahoo'
    company: company name or ticker/code
    """
    return await _get_market_data(site, company, fn="process")

@mcp.tool(
    name="save_market_data_to_gcs",
    description="Saves market data to a CSV file in Google Cloud Storage.",
    tags={"gcs", "market", "storage"}
)
def save_market_data_to_gcs(market_data: dict, gcs_path: str, file_name: str):
    """
    market_data: The JSON-like object returned from collect_market_data or process_market_data.
    gcs_path: The destination folder path in the GCS bucket.
    file_name: The name of the CSV file.
    """
    if not market_data:
        raise ValueError("market_data cannot be empty.")

    price_history = market_data.get("priceHistory")
    if not price_history:
        raise ValueError("market_data does not contain 'priceHistory'.")

    df = pd.DataFrame(price_history)
    csv_data = df.to_csv(index=False)

    gcs_manager = GCSManager()
    destination_blob_name = f"{gcs_path}/{file_name}"
    
    success = gcs_manager.upload_file(
        source_file=csv_data,
        destination_blob_name=destination_blob_name,
        content_type="text/csv"
    )

    if success:
        return f"Successfully saved market data to gs://{gcs_manager.bucket_name}/{destination_blob_name}"
    else:
        raise Exception("Failed to upload file to GCS.")

if __name__ == "__main__":
    mcp.run()
