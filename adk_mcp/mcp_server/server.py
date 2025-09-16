from fastmcp import FastMCP
from utils.fnguide import Fundamentals

mcp = FastMCP(name="StockFundamentalsServer")

@mcp.tool(
    name="find_fnguide_data",
    description="Fetch Korean stock fundamentals data from FnGuide for a given Korean stock code.",
    tags={"finance", "stocks", "fundamentals"}
)
def fetch_fnguide_data(stock: str):
    return Fundamentals(stock).fundamentals()

if __name__ == "__main__":
    mcp.run()