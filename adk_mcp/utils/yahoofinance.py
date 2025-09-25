import os
import json
import yfinance as yf
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import pandas as pd
from datetime import datetime, timedelta
from typing import Literal, Tuple
from utils.companydict import companydict as find
from utils.gcpmanager import BQManager, GCSManager
import requests
from bs4 import BeautifulSoup
import asyncio
from typing import AsyncGenerator, Dict, Any
import re

class News:
    def __init__(self):
        self.bq_manager = BQManager()

    async def news_collect(
        self,
        query: str,
        max_articles: int = 100,
        period: str = "7",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        회사 이름(query)을 받아서 티커로 변환한 뒤,
        Yahoo Finance에서 뉴스를 수집하고, 기사 본문을 크롤링한 후
        BigQuery에 저장합니다.
        """
        yield {"type": "progress", "step": "api_call", "status": "finding ticker"}
        ticker_symbol = await asyncio.to_thread(find.get_ticker, query)

        if not ticker_symbol:
            raise ValueError(f"'{query}'에 해당하는 티커를 찾을 수 없습니다.")

        yield {"type": "progress", "step": "api_call", "status": f"Ticker '{ticker_symbol}' found. Fetching news metadata..."}

        ticker = await asyncio.to_thread(yf.Ticker, ticker_symbol)
        news_list = await asyncio.to_thread(lambda: ticker.news)

        if not news_list:
            yield {"type": "result", "data": []}
            return

        if max_articles is not None:
            news_list = news_list[:max_articles]

        yield {"type": "progress", "step": "api_call", "status": f"Found {len(news_list)} news articles. Crawling content..."}

        crawled_articles = []
        total_articles = len(news_list)
        for i, item in enumerate(news_list):
            link = item.get('content', {}).get('canonicalUrl', {}).get('url')
            item['crawled_content'] = None # Initialize to None
            if link:
                yield {"type": "progress", "step": "scraping", "current": i + 1, "total": total_articles}
                item['crawled_content'] = await asyncio.to_thread(self._crawl_content, link)
            crawled_articles.append(item)
        
        yield {"type": "progress", "step": "scraping", "status": "Crawling finished."}

        df = pd.json_normalize(crawled_articles)

        # Clean column names for BigQuery
        df.columns = df.columns.str.replace('.', '_', regex=False)

        # Rename for compatibility
        df.rename(columns={'content_pubDate': 'providerPublishTime', 'content_canonicalUrl_url': 'link'}, inplace=True)

        # Add additional metadata
        df['search_keyword'] = query
        df['crawled_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Convert publish time to datetime and then to string
        if 'providerPublishTime' in df.columns:
            df['providerPublishTime'] = pd.to_datetime(df['providerPublishTime']).dt.strftime('%Y-%m-%d %H:%M:%S')

        # Reorder columns to have crawled_content at the end
        if 'crawled_content' in df.columns:
            cols = df.columns.tolist()
            cols.remove('crawled_content')
            cols.append('crawled_content')
            df = df[cols]

        period_days = int(period)
        cutoff_date = datetime.now() - timedelta(days=period_days)
        df = df[pd.to_datetime(df['providerPublishTime']) >= cutoff_date]

        yield {"type": "progress", "step": "saving", "status": f"총 {len(df)}개의 뉴스를 BigQuery로 로드합니다."}
        table_id = f"news-yahoo-{query}" # Consistent table_id format
        await asyncio.to_thread(
            self.bq_manager.load_dataframe,
            df=df,
            table_id=table_id,
            if_exists="append",
            deduplicate_on=['link']
        )
        yield {"type": "result", "data": {"saved": len(df)}}

    async def news_process(self, query: str, limit: int | None = None, period: str = "7") -> AsyncGenerator[Dict[str, Any], None]:
        """
        BigQuery에 캐시된 Yahoo Finance 뉴스를 조회하고 반환합니다.
        """
        table_id = f"news-yahoo-{query}" # Consistent table_id
        
        # Calculate cutoff date for filtering
        period_days = int(period)
        cutoff_date = datetime.now() - timedelta(days=period_days)
        
        # Query BigQuery for cached data
        cached_df = await asyncio.to_thread(
            self.bq_manager.query_table,
            table_id=table_id,
            start_date=cutoff_date.strftime('%Y-%m-%d %H:%M:%S'), # Filter by crawled_at or providerPublishTime
            order_by_date=True # Assuming 'providerPublishTime' or 'crawled_at' can be ordered
        )

        if cached_df is None or cached_df.empty:
            yield {"type": "result", "data": []}
            return
        
        if 'providerPublishTime' in cached_df.columns:
            cached_df['providerPublishTime'] = pd.to_datetime(cached_df['providerPublishTime']).dt.strftime('%Y-%m-%d %H:%M:%S')
        cached_df.fillna('', inplace=True)
        if limit is not None:
            cached_df = cached_df.head(limit)
        yield {"type": "result", "data": cached_df.to_dict(orient='records')}

    def _crawl_content(self, url: str) -> str | None:
        """
        URL을 받아 웹 페이지의 본문 텍스트를 크롤링합니다.
        """
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Break into lines and remove leading and trailing space on each
            lines = (line.strip() for line in text.splitlines())
            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # Drop blank lines
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            print(f"Error crawling {url}: {e}")
            return None

class Market:
    def __init__(self):
        self.bq_manager = BQManager()

    async def market_collect(self, company: str, start_date: str | None = None, end_date: str | None = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Yahoo Finance로부터 시세 정보를 가져오거나 BigQuery 캐시를 사용하여
        프론트엔드 형식에 맞게 정제하여 반환합니다.
        """
        if not company:
            raise ValueError("Ticker symbol must be provided.")

        ticker = await asyncio.to_thread(yf.Ticker, company)
        ticker_info = await asyncio.to_thread(lambda: ticker.info)

        # 1. 날짜 설정
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        company_name_for_table = await asyncio.to_thread(find.get_company, company)
        table_id = f"market-yahoofinance-{company_name_for_table}"

        # 2. BigQuery에서 캐시된 데이터 조회
        yield {"type": "progress", "step": "cache_check", "status": "Checking BigQuery cache..."}
        cached_df = await asyncio.to_thread(self.bq_manager.query_table, table_id=table_id, start_date=start_date, end_date=end_date)

        # 3. 캐시된 데이터가 있으면 바로 반환
        if cached_df is not None and not cached_df.empty:
            yield {"type": "progress", "step": "cache_hit", "status": f"BigQuery 캐시에서 '{table_id}' 데이터를 사용합니다. API 호출을 건너뜁니다."}
            cached_df['date'] = pd.to_datetime(cached_df['date'])
            yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, cached_df, ticker_info, company)}
            return

        # 4. 캐시가 없으면 yfinance에서 데이터 가져오기
        yield {"type": "progress", "step": "api_call", "status": f"BigQuery에 캐시된 데이터가 없거나 부족합니다. '{company}'에 대한 API 호출을 시작합니다."}
        hist_df = await asyncio.to_thread(lambda: ticker.history(start=start_date, end=end_date))

        if hist_df.empty:
            yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, None, ticker_info, company)}
            return
            
        # 5. 가져온 데이터 BigQuery에 저장
        df_for_bq = hist_df.copy()
        df_for_bq.reset_index(inplace=True)
        df_for_bq['code'] = company
        df_for_bq['source'] = 'yahoo'
        
        df_for_bq.rename(columns={
            'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume'
        }, inplace=True)

        df_for_bq['date'] = pd.to_datetime(df_for_bq['date']).dt.date
        required_cols = ['date', 'code', 'source', 'open', 'high', 'low', 'close', 'volume']
        df_for_bq = df_for_bq[required_cols]

        for col in ['open', 'high', 'low', 'close']:
            df_for_bq[col] = df_for_bq[col].round(4)
        df_for_bq['volume'] = df_for_bq['volume'].astype('int64')

        yield {"type": "progress", "step": "saving", "status": f"총 {len(df_for_bq)}개의 시세 정보를 BigQuery로 로드합니다."}
        await asyncio.to_thread(
            self.bq_manager.load_dataframe,
            df=df_for_bq,
            table_id=table_id,
            if_exists="append",
            deduplicate_on=['date', 'code']
        )
        yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, hist_df, ticker_info, company)}

    async def market_process(self, company: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        BigQuery에 캐시된 Yahoo Finance 시세 데이터를 조회하고 반환합니다.
        """
        company_name_for_table = await asyncio.to_thread(find.get_company, company)
        table_id = f"market-yahoofinance-{company_name_for_table}"

        cached_df = await asyncio.to_thread(self.bq_manager.query_table, table_id=table_id, order_by_date=True)
        
        ticker_info = await asyncio.to_thread(lambda: yf.Ticker(company).info)

        yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, cached_df, ticker_info, company)}

    def _format_response_from_df(self, df: pd.DataFrame, ticker_info: dict, company: str):
        """DataFrame을 받아 프론트엔드 응답 형식으로 변환하는 헬퍼 함수"""
        company_name = ticker_info.get('shortName', company)
        market_cap = ticker_info.get('marketCap', 0)

        if df is None or df.empty:
            print(f"'{company_name}'에 대한 데이터가 없어 빈 응답을 반환합니다.")
            return {
                "name": company_name,
                "source": "yahoo",
                "currentPrice": {"value": 0, "changePercent": 0},
                "volume": {"value": 0, "changePercent": 0},
                "marketCap": {"value": market_cap, "changePercent": 0},
                "priceHistory": [],
                "volumeHistory": [],
            }
        
        # BQ에서 온 데이터는 'date', 'close', 'volume' 컬럼이 존재.
        # yfinance에서 온 데이터는 'Date' 인덱스와 'Close', 'Volume' 컬럼을 가짐.
        if 'date' not in df.columns:
            df.reset_index(inplace=True)
            df.rename(columns={'Date': 'date', 'Close': 'close', 'Volume': 'volume'}, inplace=True)

        df.sort_values(by='date', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)

        latest = df.iloc[0]
        previous = df.iloc[1] if len(df) > 1 else latest

        price_change_percent = ((latest['close'] - previous['close']) / previous['close']) * 100 if previous['close'] != 0 else 0
        volume_change_percent = ((latest['volume'] - previous['volume']) / previous['volume']) * 100 if previous['volume'] != 0 else 0

        latest_close = float(latest['close']) if pd.notna(latest['close']) else 0.0
        latest_volume = int(latest['volume']) if pd.notna(latest['volume']) else 0

        result = {
            "name": company_name,
            "source": "yahoo",
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
            if isinstance(item['date'], pd.Timestamp) or isinstance(item['date'], datetime.date):
                item['date'] = pd.to_datetime(item['date']).strftime('%Y-%m-%d')
            item['price'] = float(item['price'])

        for item in result['volumeHistory']:
            if isinstance(item['date'], pd.Timestamp) or isinstance(item['date'], datetime.date):
                item['date'] = pd.to_datetime(item['date']).strftime('%Y-%m-%d')
            item['volume'] = int(item['volume'])

        return result

class Fundamentals:
    GCS_CACHE_PREFIX = "yahoofinance_cache"

    def __init__(self):
        self.bq_manager = BQManager()
        self.gcs_manager = GCSManager()

    def fundamentals(
        self,
        stock: str | None = None,
        query: str | None = None,
        *,
        use_cache: bool = True,
        overwrite: bool = False,
        attribute_name_str: str | None = None
    ) -> dict[str, object]:
        
        identifier = stock or query
        if not identifier:
            raise ValueError("Must provide either 'stock' or 'query'.")

        ticker_symbol = find.get_ticker(identifier) or identifier.upper()

        # If a specific attribute is requested, bypass the full-summary cache and fetch directly.
        if attribute_name_str:
            ticker = yf.Ticker(ticker_symbol)
            if hasattr(ticker, attribute_name_str):
                data = getattr(ticker, attribute_name_str)
                # yfinance can return DataFrames, Series, or dicts. Convert to JSON-serializable format.
                if isinstance(data, pd.DataFrame):
                    return json.loads(data.to_json(orient="records", date_format="iso"))
                if isinstance(data, pd.Series):
                    return data.to_dict()
                if isinstance(data, dict):
                    return data
                return data # Fallback for other types
            else:
                raise ValueError(f"'{attribute_name_str}' is not a valid yfinance Ticker attribute.")

        # --- Logic for full summary ---
        gcs_blob_name = f"{self.GCS_CACHE_PREFIX}/{ticker_symbol}.json"

        if use_cache and not overwrite:
            cached_payload = self.gcs_manager.read_file(gcs_blob_name)
            if cached_payload:
                try:
                    payload = json.loads(cached_payload)
                    # Check if the cached data has the exchange rate if needed
                    currency = payload.get('session_state', {}).get('currency')
                    if currency and currency != 'KRW':
                        if payload.get('session_state', {}).get('raw_snapshot', {}).get('usdkrw') is None:
                            logging.info("Cached data is missing exchange rate. Refetching.")
                        else:
                            logging.info(f"Returning cached data for {ticker_symbol} from GCS: {gcs_blob_name}")
                            return payload
                    else:
                        logging.info(f"Returning cached data for {ticker_symbol} from GCS: {gcs_blob_name}")
                        return payload
                except (json.JSONDecodeError, KeyError) as e:
                    logging.warning(f"GCS cache read failed for {ticker_symbol} (corrupted/invalid JSON): {e}. Refetching.")

        ticker = yf.Ticker(ticker_symbol)

        try:
            info = ticker.info or {}
        except Exception:
            info = {}
        try:
            fast_info = ticker.fast_info or {}
        except Exception:
            fast_info = {}

        def _get(*keys, src=None):
            src = src or info
            for key in keys:
                if key in src and src[key] not in (None, ''):
                    return src[key]
            return None

        price = _get('last_price', src=fast_info) or _get('regularMarketPrice')
        change = _get('regularMarketChange')
        change_pct = _get('regularMarketChangePercent')
        volume = _get('last_volume', src=fast_info) or _get('regularMarketVolume')
        currency = _get('currency', src=fast_info) or _get('currency') or ''
        market_cap = _get('market_cap', src=fast_info) or _get('marketCap')
        trailing_pe = _get('trailingPE')
        forward_pe = _get('forwardPE')
        roe = _get('returnOnEquity')
        beta = _get('beta')
        dividend_yield_raw = _get('dividendYield')
        dividend_yield = None
        if isinstance(dividend_yield_raw, (int, float)):
            dividend_yield = dividend_yield_raw * 100 if dividend_yield_raw < 1 else dividend_yield_raw
        sector = _get('sector')
        industry = _get('industry')
        country = _get('country')
        summary = _get('longBusinessSummary')
        fifty_two_high = _get('fiftyTwoWeekHigh')
        fifty_two_low = _get('fiftyTwoWeekLow')

        usdkrw_rate = None
        if currency and currency != 'KRW':
            try:
                rate_ticker_symbol = f"{currency}KRW=X"
                rate_ticker = yf.Ticker(rate_ticker_symbol)
                rate_info = rate_ticker.fast_info or {}
                usdkrw_rate = rate_info.get('last_price')
            except Exception as e:
                logging.warning(f"Could not fetch exchange rate for {rate_ticker_symbol}: {e}")

        def fmt_signed(value):
            if value is None:
                return '-'
            try:
                return f"{value:+.2f}"
            except Exception:
                return str(value)

        def fmt_percent(value):
            if value is None:
                return '-'
            try:
                return f"{value:.2f}%"
            except Exception:
                return str(value)

        def fmt_number(value):
            if value is None:
                return '-'
            try:
                return f"{value:,}"
            except Exception:
                return str(value)

        def fmt_market_cap(value):
            if value is None:
                return '-'
            try:
                if value >= 1e12:
                    return f"{value/1e12:.2f} 조"
                if value >= 1e9:
                    return f"{value/1e9:.2f} 십억"
                if value >= 1e6:
                    return f"{value/1e6:.2f} 백만"
                return f"{value:,}"
            except Exception:
                return str(value)

        market_conditions = [
            {
                '0': '종가/ 전일대비/ 수익률',
                '1': f"{fmt_number(price)} / {fmt_signed(change)} / {fmt_percent(change_pct)}",
                '2': '거래량',
                '3': fmt_number(volume)
            },
            {
                '0': f'시가총액({currency})',
                '1': fmt_market_cap(market_cap),
                '2': 'PER / 선행 PER',
                '3': f"{trailing_pe or '-'} / {forward_pe or '-'}"
            },
            {
                '0': '배당수익률',
                '1': fmt_percent(dividend_yield),
                '2': '베타(1년)',
                '3': beta if beta is not None else '-'
            }
        ]
        if fifty_two_high or fifty_two_low:
            market_conditions.append({
                '0': '52주.최고가/ 최저가',
                '1': f"{fmt_number(fifty_two_high)} / {fmt_number(fifty_two_low)}",
                '2': '',
                '3': ''
            })

        industry_comparison = []
        if trailing_pe is not None or forward_pe is not None:
            industry_comparison.append({'category': 'PER', 'company': trailing_pe, 'kospi_electronics': forward_pe, 'KOSPI': None})
        if roe is not None:
            industry_comparison.append({'category': 'ROE', 'company': roe * 100 if roe < 1 else roe, 'kospi_electronics': None, 'KOSPI': None})
        if dividend_yield is not None:
            industry_comparison.append({'category': '배당수익률', 'company': dividend_yield, 'kospi_electronics': None, 'KOSPI': None})
        if beta is not None:
            industry_comparison.append({'category': '베타(1년)', 'company': beta, 'kospi_electronics': None, 'KOSPI': 1})

        analysis_lines = []
        if sector or industry:
            analysis_lines.append(f"• 섹터/산업: {sector or '-'} / {industry or '-'}")
        if country:
            analysis_lines.append(f"• 상장 국가: {country}")
        if market_cap:
            analysis_lines.append(f"• 시가총액: {fmt_market_cap(market_cap)} {currency}")
        if trailing_pe:
            analysis_lines.append(f"• PER: {trailing_pe}")
        if dividend_yield is not None:
            analysis_lines.append(f"• 배당수익률: {dividend_yield:.2f}%")
        if summary:
            analysis_lines.append('\n' + summary)
        analysis_text = ''.join(analysis_lines) if analysis_lines else '분석 요약을 생성할 수 없습니다.'

        score = 70
        if isinstance(trailing_pe, (int, float)) and trailing_pe < 15:
            score += 5
        if isinstance(dividend_yield, (int, float)) and dividend_yield > 2:
            score += 5
        if isinstance(beta, (int, float)) and beta < 1:
            score += 3
        if isinstance(forward_pe, (int, float)) and forward_pe < 12:
            score += 4
        score = max(55, min(95, int(round(score))))
        if score >= 85:
            rate = 'excellent'
        elif score >= 70:
            rate = 'good'
        elif score >= 60:
            rate = 'normal'
        else:
            rate = 'warning'
        rating = {
            'score': score,
            'rate': rate,
            'justification': '기본 지표(시가총액, 수익성, 배당 등)를 기반으로 산출한 단순 스코어입니다.'
        }

        result = {
            'market_conditions': market_conditions,
            'earning_issue': [],
            'holdings_status': [],
            'governance': [],
            'shareholders': [],
            'bond_rating': [],
            'analysis': [],
            'industry_comparison': industry_comparison,
            'financialhighlight_annual': [],
            'financialhighlight_netquarter': []
        }

        session_state = {
            'ticker': ticker_symbol,
            'currency': currency,
            'source': 'yahoofinance',
            'raw_snapshot': {
                'marketCap': market_cap,
                'pe': trailing_pe,
                'forwardPE': forward_pe,
                'dividendYield': dividend_yield,
                'beta': beta,
                'volume': volume,
                'usdkrw': usdkrw_rate
            }
        }

        final_data = {
            'result': result,
            'analysis': analysis_text,
            'rating': rating,
            'session_state': session_state,
            'agent_final_response': None,
        }

        try:
            payload_json = json.dumps(final_data, ensure_ascii=False, indent=4)
            self.gcs_manager.upload_file(
                source_file=payload_json,
                destination_blob_name=gcs_blob_name,
                encoding="utf-8",
                content_type="application/json; charset=utf-8",
            )
            logging.info(f"Successfully cached data for {ticker_symbol} to GCS: {gcs_blob_name}")
        except Exception as e:
            logging.error(f"GCS cache write failed for {ticker_symbol}: {e}")

        return final_data


async def _collect_ticker_metadata(ticker: yf.Ticker, fallback: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = dict(fallback)

    symbol = getattr(ticker, "ticker", None) or metadata.get("company_id")
    metadata["company_id"] = symbol or metadata.get("company_id")

    info: Dict[str, Any] = {}
    try:
        info = await asyncio.to_thread(ticker.get_info)
    except Exception as exc:
        logging.warning("Failed to fetch ticker info for %s: %s", symbol, exc)

    try:
        fast_info = await asyncio.to_thread(lambda: ticker.fast_info)
    except Exception as exc:
        logging.warning("Failed to fetch fast info for %s: %s", symbol, exc)
        fast_info = {}

    metadata["company_name"] = (
        info.get("longName")
        or info.get("shortName")
        or metadata.get("company_name")
        or metadata.get("company_id")
    )
    metadata["exchange"] = (
        info.get("exchange")
        or info.get("fullExchangeName")
        or fast_info.get("exchange")
        or metadata.get("exchange")
    )
    metadata["currency"] = (
        info.get("currency")
        or fast_info.get("currency")
        or metadata.get("currency")
    )
    metadata["market_cap"] = (
        info.get("marketCap")
        or fast_info.get("market_cap")
        or metadata.get("market_cap")
    )
    metadata["shares_outstanding"] = (
        info.get("sharesOutstanding")
        or fast_info.get("shares_outstanding")
        or fast_info.get("shares")
        or metadata.get("shares_outstanding")
    )
    metadata["sector"] = (
        info.get("sector")
        or info.get("industry")
        or metadata.get("sector")
    )

    if not metadata.get("company_id"):
        metadata["company_id"] = metadata.get("company_name")
    if not metadata.get("company_name"):
        metadata["company_name"] = metadata.get("company_id")

    return metadata


async def fetch_market_dataframe(
    company: str,
    start_date: str,
    end_date: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fetch raw Yahoo Finance market data and related metadata for a company."""

    ticker_symbol = await asyncio.to_thread(find.get_ticker, company)
    if not ticker_symbol:
        ticker_symbol = company

    ticker = await asyncio.to_thread(yf.Ticker, ticker_symbol)
    hist_df = await asyncio.to_thread(
        lambda: ticker.history(start=start_date, end=end_date, auto_adjust=False)
    )

    if hist_df.empty:
        return pd.DataFrame(), {}

    hist_df.reset_index(inplace=True)
    hist_df.rename(
        columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Adj Close': 'adj_close',
            'Volume': 'volume',
        },
        inplace=True,
    )

    company_name = await asyncio.to_thread(find.get_company, company)
    metadata = await _collect_ticker_metadata(
        ticker,
        fallback={
            "company_id": ticker_symbol,
            "company_name": company_name or ticker_symbol,
            "exchange": None,
            "currency": "USD",
            "market_cap": None,
            "shares_outstanding": None,
            "sector": None,
            "source": "Yahoo",
        },
    )

    metadata.setdefault("source", "Yahoo")

    return hist_df, metadata
