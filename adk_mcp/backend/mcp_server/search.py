from pathlib import Path
import sys
from typing import Dict, List, Optional

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.websearchtool import (
    brave_search_async,
    exa_search_async,
    hybrid_web_search_async,
)

mcp = FastMCP(name="SearchServer")


@mcp.tool(
    name="brave_search",
    description="Query the Brave Search API for web, news, image, or video results.",
    tags={"search", "brave", "web"}
)
async def brave_search(
    query: str,
    kind: str = "web",
    count: int = 10,
    country: str = "kr",
    lang: str = "ko",
    safesearch: str = "moderate",
) -> Dict:
    """Return raw Brave results for the requested vertical."""
    return await brave_search_async(
        query=query,
        kind=kind,
        count=count,
        country=country,
        lang=lang,
        safesearch=safesearch,
    )


@mcp.tool(
    name="exa_search",
    description="Run an Exa semantic search query and return structured results.",
    tags={"search", "exa", "web"}
)
async def exa_search(
    query: str,
    num_results: int = 10,
    search_type: str = "auto",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    category: Optional[str] = None,
    start_published: Optional[str] = None,
    end_published: Optional[str] = None,
) -> Dict:
    """Return Exa results for the query using the specified search type."""
    return await exa_search_async(
        query=query,
        num_results=num_results,
        search_type=search_type,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        category=category,
        start_published=start_published,
        end_published=end_published,
    )


@mcp.tool(
    name="hybrid_web_search",
    description="Run a Brave + Exa hybrid search with reciprocal-rank fusion and optional Exa content enrichment.",
    tags={"search", "brave", "exa", "hybrid"}
)
async def hybrid_web_search(
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
    country: str = "kr",
    safesearch: str = "moderate",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    category: Optional[str] = None,
    start_published: Optional[str] = None,
    end_published: Optional[str] = None,
) -> Dict:
    """Fuse Brave and Exa search results and optionally enrich the top URLs."""
    return await hybrid_web_search_async(
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
        country=country,
        safesearch=safesearch,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        category=category,
        start_published=start_published,
        end_published=end_published,
    )


if __name__ == "__main__":
    mcp.run()
