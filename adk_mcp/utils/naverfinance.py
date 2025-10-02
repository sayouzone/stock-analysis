import asyncio
from bs4 import BeautifulSoup # type: ignore
import httpx # type: ignore
import re
import random
import pandas as pd # type: ignore
from datetime import datetime, timedelta
from io import StringIO
from urllib import parse
from typing import Dict, Any, Tuple

NAVER_FINANCE_BASE_URL = 'https://finance.naver.com'
NAVER_M_STOCK_API_BASE = 'https://m.stock.naver.com/api/stock'

DEFAULT_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
from utils.gcpmanager import BQManager


HTML_PARSER = 'html.parser'


def _build_mobile_headers(company_code: str) -> Dict[str, str]:
    return {
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://m.stock.naver.com/domestic/stock/{company_code}',
    }


def _build_summary_headers(company_code: str) -> Dict[str, str]:
    return {
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'{NAVER_FINANCE_BASE_URL}/item/main.nhn?code={company_code}',
    }


def _infer_currency(nation_code: str | None) -> str | None:
    if not nation_code:
        return None
    nation_code = nation_code.upper()
    if nation_code in {'KOR', 'KR'}:
        return 'KRW'
    if nation_code in {'USA', 'US'}:
        return 'USD'
    if nation_code in {'JPN', 'JP'}:
        return 'JPY'
    if nation_code in {'CHN', 'CN'}:
        return 'CNY'
    return None

class News:
    """Independent Naver news pipeline (no NaverCrawler dependency)."""
    def __init__(self, bq_manager: BQManager):
        self.bq_manager = bq_manager
        self.client = httpx.AsyncClient(headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        }, follow_redirects=True)

    async def collect(self, query: str, max_articles: int = 100):
        table_id = f"news-naver-{query}"

        enc_text = parse.quote(query)
        api_url = f"https://openapi.naver.com/v1/search/news.json?query={enc_text}&display={max_articles}"

        client_id = 'YOUR_NAVER_CLIENT_ID'
        client_secret = 'YOUR_NAVER_CLIENT_SECRET'
        api_headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret
        }

        try:
            response = await self.client.get(api_url, headers=api_headers)
            response.raise_for_status()
            search_result = response.json()
            news_list = search_result.get('items', [])
            yield {"type": "progress", "step": "api_call", "status": "done", "total": len(news_list)}

        except Exception as e:
            yield {"type": "error", "message": f"API request failed: {e}"}
            return

        scraped_treasures: list[dict] = []
        total_articles = len(news_list)
        for i, news_item in enumerate(news_list):
            news_url = news_item.get('link')
            if not news_url or 'news.naver.com' not in news_url:
                continue

            try:
                yield {"type": "progress", "step": "scraping", "current": i + 1, "total": total_articles}
                response = await self.client.get(news_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, HTML_PARSER)

                title = soup.select_one('h2#title_area')
                content = soup.select_one('div#newsct_article')
                press = soup.select_one('img.media_end_head_top_logo_img') 

                cleaned_title = title.get_text(strip=True) if title else "제목 없음"
                cleaned_content = content.get_text(strip=True) if content else "본문 없음"
                cleaned_press = press['alt'] if press and 'alt' in press.attrs else "언론사 불명"

                treasure_box = {
                    'search_keyword': query,
                    'original_link': news_url,
                    'title': cleaned_title,
                    'press': cleaned_press,
                    'content': cleaned_content[:500],
                    'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                scraped_treasures.append(treasure_box)
                await asyncio.sleep(random.uniform(0.1, 0.3))

            except Exception as e:
                print(f"Error scraping {news_url}: {e}")
                continue

        if not scraped_treasures:
            yield {"type": "result", "data": []}
            return

        yield {"type": "progress", "step": "saving", "status": "saving to BigQuery"}
        _ = self._prepare_and_save_news_data(scraped_treasures, table_id)
        yield {"type": "result", "data": {"saved": len(scraped_treasures)}}

    async def process(self, query: str, limit: int | None = None):
        table_id = f"news-naver-{query}"
        cached_df = self.bq_manager.query_table(table_id=table_id, order_by_date=False)
        if cached_df is None or cached_df.empty:
            yield {"type": "result", "data": []}
            return
        if 'crawled_at' in cached_df.columns:
            cached_df['crawled_at'] = pd.to_datetime(cached_df['crawled_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        cached_df.fillna('', inplace=True)
        if 'content' in cached_df.columns:
            cached_df['content'] = cached_df['content'].str.slice(0, 500)
        if limit is not None:
            cached_df = cached_df.head(limit)
        yield {"type": "result", "data": cached_df.to_dict(orient='records')}

    def _prepare_and_save_news_data(self, treasures: list[dict], table_id: str) -> pd.DataFrame:
        df_treasures = pd.DataFrame(treasures)
        self.bq_manager.load_dataframe(
            df=df_treasures,
            table_id=table_id,
            if_exists="append",
            deduplicate_on=['original_link']
        )
        return df_treasures

class Market:
    def __init__(self, bq_manager: BQManager, company_dict: Any, company: str | None = None):
        self._header = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Accept' : "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        }
        self.base_url = 'https://finance.naver.com'
        self.company = company or '005930'
        self.bq_manager = bq_manager
        self.company_dict = company_dict
        self.client = httpx.AsyncClient(headers=self._header, follow_redirects=True)

    async def market_collect(self, company: str | None = None, start_date: str | None = None, end_date: str | None = None, max_page: int = 10):
        if company:
            self.company = company

        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        company_name = self.company_dict.get_company_by_code(self.company) or self.company
        table_id = f"market-naverfinance-{company_name}"

        crawled_df = pd.DataFrame()
        async for progress_update in _crawl_price_history(self.company, self.client, max_page=max_page):
            if progress_update["type"] == "progress":
                yield progress_update
            elif progress_update["type"] == "result":
                crawled_df = progress_update["data"]

        if crawled_df.empty:
            yield {"type": "error", "message": "Failed to crawl market data."}
            return

        # Filter by date range
        crawled_df = crawled_df[
            (crawled_df['date'] >= pd.to_datetime(start_date)) &
            (crawled_df['date'] <= pd.to_datetime(end_date))
        ]

        yield {"type": "progress", "step": "saving", "status": "saving to BigQuery"}
        df_saved = self._prepare_and_save_market_data(crawled_df, table_id)
        yield {"type": "result", "data": {"saved": len(df_saved)}}
    
    def _prepare_and_save_market_data(self, df: pd.DataFrame, table_id: str) -> pd.DataFrame:
        """Clean market dataframe and persist to BigQuery in one step.

        - Ensures required columns and types
        - Adds code/source columns
        - Saves to BigQuery with deduplication
        - Returns the dataframe that was saved
        """
        df_for_bq = df.copy()
        if 'date' in df_for_bq.columns:
            df_for_bq['date'] = pd.to_datetime(df_for_bq['date']).dt.date

        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_for_bq.columns:
                df_for_bq[col] = pd.to_numeric(df_for_bq[col], errors='coerce').fillna(0)
                if col == 'volume':
                    df_for_bq[col] = df_for_bq[col].astype('int64')
                else:
                    df_for_bq[col] = df_for_bq[col].astype(float)

        df_for_bq['code'] = self.company
        df_for_bq['source'] = 'naver'

        self.bq_manager.load_dataframe(
            df=df_for_bq,
            table_id=table_id,
            if_exists="append",
            deduplicate_on=['date', 'code']
        )

        return df_for_bq

    async def _get_market_cap(self):
        """현재 종목의 시가총액을 스크래핑하여 숫자로 반환합니다."""
        try:
            url = f'https://finance.naver.com/item/sise.naver?code={self.company}'
            response = await self.client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, HTML_PARSER)
            
            market_sum_tag = soup.select_one('#_market_sum')
            if market_sum_tag:
                market_sum_text = market_sum_tag.get_text(strip=True)
                
                market_sum = 0
                parts = market_sum_text.replace(',', '').split('조')
                if len(parts) > 1:
                    market_sum += int(parts[0]) * 1_0000_0000_0000
                    remaining = parts[1]
                else:
                    remaining = parts[0]
                
                if '억' in remaining:
                    market_sum += int(remaining.replace('억', '')) * 1_0000_0000
                
                return market_sum
            return 0
        except Exception:
            return 0
    
    async def market_process(self, company: str | None = None):
        if company:
            self.company = company
        
        company_name = self.company_dict.get_company_by_code(self.company) or self.company
        table_id = f"market-naverfinance-{company_name}"
        
        cached_df = self.bq_manager.query_table(table_id=table_id, order_by_date=True)
        
        if cached_df is None or cached_df.empty:
            yield {"type": "result", "data": {}}
            return

        formatted_data = await self._format_response_from_df(cached_df)
        yield {"type": "result", "data": formatted_data}

    async def _format_response_from_df(self, df: pd.DataFrame):
        company_name = self.company_dict.get_company_by_code(self.company) or self.company
        market_cap = await self._get_market_cap()

        if df is None or df.empty:
            return {
                "name": company_name,
                "source": "naver",
                "currentPrice": {"value": 0, "changePercent": 0},
                "volume": {"value": 0, "changePercent": 0},
                "marketCap": {"value": market_cap, "changePercent": 0},
                "priceHistory": [],
                "volumeHistory": [],
            }
            
        df.sort_values(by='date', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)

        latest = df.iloc[0]
        previous = df.iloc[1] if len(df) > 1 else latest

        price_change_percent = ((latest['close'] - previous['close']) / previous['close']) * 100 if previous['close'] != 0 else 0
        volume_change_percent = ((latest['volume'] - previous['volume']) / previous['volume']) * 100 if previous['volume'] != 0 else 0

        latest_close = float(latest['close']) if pd.notna(latest['close']) else 0.0
        latest_volume = int(latest['volume']) if pd.notna(latest['volume']) else 0

        result = {
            "name": company_name or self.company,
            "source": "naver",
            "currentPrice": {
                "value": latest_close,
                "changePercent": round(price_change_percent, 2)
            },
            "volume": {
                "value": latest_volume,
                "changePercent": round(volume_change_percent, 2)
            },
            "marketCap": {
                "value": market_cap,
                "changePercent": 0 
            },
            "priceHistory": df.rename(columns={'close': 'price'})[['date', 'price']].to_dict(orient='records'),
            "volumeHistory": df[['date', 'volume']].to_dict(orient='records')
        }

        for item in result['priceHistory']:
            if isinstance(item['date'], pd.Timestamp):
                item['date'] = item['date'].strftime('%Y-%m-%d')

        for item in result['volumeHistory']:
            if isinstance(item['date'], pd.Timestamp):
                item['date'] = item['date'].strftime('%Y-%m-%d')

        return result


async def _fetch_company_metadata(company_code: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    latest_price: float | None = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            basic_resp = await client.get(
                f"{NAVER_M_STOCK_API_BASE}/{company_code}/basic",
                headers=_build_mobile_headers(company_code),
            )
            basic_resp.raise_for_status()
            basic_json = basic_resp.json()

            metadata["company_name"] = basic_json.get("stockName")

            exchange_info = basic_json.get("stockExchangeType") or {}
            metadata["exchange"] = (
                exchange_info.get("name")
                or basic_json.get("stockExchangeName")
            )
            metadata["currency"] = (
                _infer_currency(exchange_info.get("nationCode"))
                or "KRW"
            )

            closing_price = basic_json.get("closePrice")
            if closing_price is not None:
                try:
                    latest_price = float(str(closing_price).replace(',', ''))
                except ValueError:
                    latest_price = None
        except Exception as exc:
            metadata.setdefault("_errors", {})["basic"] = str(exc)

        try:
            summary_resp = await client.get(
                f"https://api.finance.naver.com/service/itemSummary.naver?itemcode={company_code}",
                headers=_build_summary_headers(company_code),
            )
            summary_resp.raise_for_status()
            summary_json = summary_resp.json()
            market_sum = summary_json.get("marketSum")
            if isinstance(market_sum, (int, float)):
                market_cap = float(market_sum) * 1_000_000  # marketSum is in million KRW
                metadata["market_cap"] = market_cap
                if latest_price and latest_price > 0:
                    metadata["shares_outstanding"] = int(round(market_cap / latest_price))
            else:
                metadata.setdefault("_warnings", []).append("marketSum missing")
        except Exception as exc:
            metadata.setdefault("_errors", {})["summary"] = str(exc)

    return metadata


async def _find_last_page_number(company_code: str, client: httpx.AsyncClient) -> int:
    try:
        url = f"{NAVER_FINANCE_BASE_URL}/item/sise_day.nhn?code={company_code}&page=1"
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, HTML_PARSER)
        match = None
        pg_rr_tag = soup.select_one('.pgRR a')
        if pg_rr_tag:
            href_value = pg_rr_tag.get('href')
            if isinstance(href_value, str):
                match = re.search(r'page=(\d+)', href_value)
        if match:
            last_page_number = int(match.group(1))
        else:
            last_page_number = 1
    except Exception:
        last_page_number = 1
    return last_page_number


async def _crawl_price_history(
    company_code: str,
    client: httpx.AsyncClient,
    max_page: int | None = None,
):
    last_page = await _find_last_page_number(company_code, client)
    final_max_page = min(max_page, last_page) if max_page else last_page

    full_df = []
    for page in range(1, final_max_page + 1):
        yield {"type": "progress", "step": "scraping", "current": page, "total": final_max_page}
        try:
            url = f"{NAVER_FINANCE_BASE_URL}/item/sise_day.nhn?code={company_code}&page={page}"
            response = await client.get(url)
            response.raise_for_status()

            dfs = pd.read_html(StringIO(response.text))
            df = dfs[0]
            df.dropna(how='all', inplace=True)
            if not df.empty:
                full_df.append(df)

            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception as exc:
            print(f"Error scraping page {page}: {exc}")
            continue

    if not full_df:
        yield {"type": "result", "data": pd.DataFrame()}
        return

    crawled_df = pd.concat(full_df, ignore_index=True)
    crawled_df.rename(columns={
        '날짜': 'date',
        '종가': 'close',
        '시가': 'open',
        '고가': 'high',
        '저가': 'low',
        '거래량': 'volume'
    }, inplace=True)

    if '전일비' in crawled_df.columns:
        crawled_df.drop(columns=['전일비'], inplace=True)

    numeric_cols = ['close', 'open', 'high', 'low', 'volume']
    for col in numeric_cols:
        if col in crawled_df.columns:
            crawled_df[col] = pd.to_numeric(
                crawled_df[col].astype(str).str.replace(',', '', regex=False),
                errors='coerce'
            ).fillna(0)
            if col == 'volume':
                crawled_df[col] = crawled_df[col].astype('int64')

    crawled_df['date'] = pd.to_datetime(crawled_df['date'], errors='coerce')
    crawled_df.dropna(subset=['date'], inplace=True)
    
    yield {"type": "result", "data": crawled_df}


async def fetch_market_dataframe(
    company: str,
    start_date: str,
    end_date: str,
    company_dict: Any,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fetch Naver Finance market data and metadata for a company code or name."""

    company_code = company_dict.get_code(company)
    if not company_code and company.isdigit():
        company_code = company
    if not company_code:
        raise ValueError(f"Code for {company} not found.")

    crawled_df = pd.DataFrame()
    async with httpx.AsyncClient(
        headers={
            'User-Agent': DEFAULT_USER_AGENT,
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        },
        follow_redirects=True,
    ) as client:
        async for update in _crawl_price_history(company_code, client):
            if update['type'] == 'result':
                crawled_df = update['data']

    if not crawled_df.empty:
        crawled_df = crawled_df[
            (crawled_df['date'] >= pd.to_datetime(start_date)) &
            (crawled_df['date'] <= pd.to_datetime(end_date))
        ]

    metadata: Dict[str, Any] = {
        "company_id": company_dict.get_ticker(company) or company_code,
        "company_name": company_dict.get_company_by_code(company_code) or company,
        "exchange": "KRX",
        "currency": "KRW",
        "market_cap": None,
        "shares_outstanding": None,
        "sector": None,
        "source": "Naver",
    }

    api_metadata = await _fetch_company_metadata(company_code)

    if api_metadata:
        for key, value in api_metadata.items():
            if key in {"_errors", "_warnings"}:
                continue
            if value in (None, "", []):
                continue
            metadata[key] = value

    if not metadata.get("company_name"):
        metadata["company_name"] = company
    if not metadata.get("currency"):
        metadata["currency"] = "KRW"
    if not metadata.get("exchange"):
        metadata["exchange"] = "KRX"

    return crawled_df, metadata
