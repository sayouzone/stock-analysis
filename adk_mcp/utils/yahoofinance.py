import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Literal
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

    async def news_collect(self, query: str, max_articles: int = 100, period: str = "7") -> AsyncGenerator[Dict[str, Any], None]:
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
            yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, cached_df, company)}
            return

        # 4. 캐시가 없으면 yfinance에서 데이터 가져오기
        yield {"type": "progress", "step": "api_call", "status": f"BigQuery에 캐시된 데이터가 없거나 부족합니다. '{company}'에 대한 API 호출을 시작합니다."}
        ticker = await asyncio.to_thread(yf.Ticker, company)
        hist_df = await asyncio.to_thread(lambda: ticker.history(start=start_date, end=end_date))

        if hist_df.empty:
            yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, None, company)}
            return
            
        # 5. 가져온 데이터 BigQuery에 저장
        yield {"type": "progress", "step": "saving", "status": f"총 {len(df_for_bq)}개의 시세 정보를 BigQuery로 로드합니다."}
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

        await asyncio.to_thread(
            self.bq_manager.load_dataframe,
            df=df_for_bq,
            table_id=table_id,
            if_exists="append",
            deduplicate_on=['date', 'code']
        )
        yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, hist_df, company)}

        # 6. 프론트엔드 응답 준비
        # BQ에 저장 후, API에서 가져온 데이터를 바로 포맷하여 반환

    async def market_process(self, company: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        BigQuery에 캐시된 Yahoo Finance 시세 데이터를 조회하고 반환합니다.
        """
        company_name_for_table = await asyncio.to_thread(find.get_company, company)
        table_id = f"market-yahoofinance-{company_name_for_table}"

        cached_df = await asyncio.to_thread(self.bq_manager.query_table, table_id=table_id, order_by_date=True)
        
        if cached_df is None or cached_df.empty:
            yield {"type": "result", "data": {}}
            return
        yield {"type": "result", "data": await asyncio.to_thread(self._format_response_from_df, cached_df, company)}

    def _format_response_from_df(self, df: pd.DataFrame, company: str):
        """DataFrame을 받아 프론트엔드 응답 형식으로 변환하는 헬퍼 함수"""
        ticker = yf.Ticker(company)
        company_name = ticker.info.get('shortName', company)
        market_cap = ticker.info.get('marketCap', 0)

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
    def __init__(self):
        self.bq_manager = BQManager() # Added for consistency, even if not used for caching here
        self.gcs_manager = GCSManager()

    def fundamentals(self, query: str, attribute_name_str: Literal[ # Renamed from 'get' to 'fundamentals' for router compatibility
        "income_stmt", "quarterly_income_stmt", "ttm_income_stmt", "balance_sheet", "cashflow", "quarterly_cashflow",
        "ttm_cashflow", "sustainability", "earnings_estimate", "revenue_estimate", "earnings_history", "eps_trend",
        "eps_revisions", "growth_estimates", "insider_purchases", "insider_transactions", "insider_roster_holders",
        "major_holders", "institutional_holders", "mutualfund_holders"
    ]):
        ticker_symbol = find.get_ticker(query)
        if not ticker_symbol:
            raise ValueError(f"'{query}'에 해당하는 티커를 찾을 수 없습니다.")

        ticker = yf.Ticker(ticker_symbol)
        print(f"\n'{attribute_name_str}' 속성을 동적으로 가져옵니다...")
        try:
            data_attribute = getattr(ticker, attribute_name_str, None)

            if data_attribute is None:
                print(f"오류: '{attribute_name_str}' 속성을 찾을 수 없습니다.")
                return None

            print(f"'{attribute_name_str}' 속성 가져오기 완료.")
            print(f"  - 타입: {type(data_attribute)}")
            if isinstance(data_attribute, pd.DataFrame):
                print("  - 데이터 미리보기 (상위 3줄):")
                print(data_attribute.head(3))
            elif isinstance(data_attribute, dict):
                print("  - 데이터 미리보기 (일부 키):")
                for i, (key, value) in enumerate(data_attribute.items()):
                    if i >= 3:
                        break
                    print(f"    {key}: {value}")
            else:
                print(f"  - 데이터: {data_attribute}")

            if isinstance(data_attribute, (pd.DataFrame, pd.Series)):
                self._upload_table_to_gcs(
                    ticker_symbol=ticker_symbol,
                    attribute_name=attribute_name_str,
                    data_table=data_attribute,
                )

            return data_attribute

        except Exception as e:
            print(f"예상치 못한 오류 발생: {e}")
        return None

    def _upload_table_to_gcs(self, *, ticker_symbol: str, attribute_name: str, data_table: pd.DataFrame | pd.Series):
        """Upload DataFrame/Series fundamentals data to GCS following FnGuide naming rules."""
        if getattr(self.gcs_manager, "_storage_available", False) is False:
            print("GCS 클라이언트가 비활성화되어 업로드를 건너뜁니다.")
            return

        if isinstance(data_table, pd.DataFrame) and data_table.empty:
            print("업로드할 데이터프레임이 비어 있어 업로드를 건너뜁니다.")
            return

        folder_name = self._build_folder_path(ticker_symbol)
        existing_files = set(self.gcs_manager.list_files(folder_name=folder_name))
        file_name = f"{folder_name}{attribute_name}.csv"

        if file_name in existing_files:
            print(f"'{file_name}' 파일이 이미 존재하여 업로드를 건너뜁니다.")
            return

        csv_payload = data_table.to_csv()
        self.gcs_manager.upload_file(
            source_file=csv_payload,
            destination_blob_name=file_name,
            encoding="utf-8",
            content_type="text/csv; charset=utf-8",
        )

    def _build_folder_path(self, ticker_symbol: str) -> str:
        """Build the Yahoo Finance fundamentals folder path for the provided ticker."""
        now = datetime.now()
        current_quarter = f"{now.year}-Q{((now.month - 1) // 3) + 1}"
        safe_ticker = re.sub(r"[^0-9A-Za-z_-]", "_", ticker_symbol)
        return f"/Fundamentals/YahooFinance/{safe_ticker}/{current_quarter}/"
