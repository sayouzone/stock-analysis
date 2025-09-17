from pathlib import Path
import sys

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.fnguide import Fundamentals

mcp = FastMCP(name="StockFundamentalsServer")

@mcp.tool(
    name="find_fnguide_data",
    description="Fetch Korean stock fundamentals data from FnGuide for a given Korea stock code.",
    tags={"finance", "stocks", "fundamentals", "Korea"}
)
def fetch_fnguide_data(stock: str):
    return Fundamentals(stock).fundamentals()

if __name__ == "__main__":
    mcp.run()
