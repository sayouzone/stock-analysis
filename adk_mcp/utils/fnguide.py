import requests
from bs4 import BeautifulSoup
import pandas as pd
import lxml

import json
from .gcpmanager import GCSManager

import io
import re
from datetime import date

class Fundamentals:
    JSON_NAMES = ["market_conditions", "earning_issue", "analysis"]
    CSV_NAMES = [
        "holdings_status",
        "governance",
        "shareholders",
        "industry_comparison",
        "bond_rating",
        "financialhighlight_annual",
        "financialhighlight_netquarter",
    ]
    CSV_SERIES_NAMES = {
        "financialhighlight_annual",
        "financialhighlight_netquarter",
    }

    _market_conditions_map = {
        "종가(원)": "close_price",
        "전일대비(원)": "change_price",
        "수익률(%)": "change_rate",
        "거래량(주))": "volume",
        "최고가(52주)": "high_52w",
        "최저가(52주)": "low_52w",
        "거래대금(억원)": "trading_value_100m",
        "수익률(1M)": "return_1m",
        "수익률(3M)": "return_3m",
        "수익률(6M)": "return_6m",
        "수익률(1Y)": "return_1y",
        "외국인지분율(%)": "foreign_ownership_ratio",
        "시가총액(상장예정포함,억원)": "market_cap_incl_ipo_100m",
        "베타(1년)": "beta_1y",
        "시가총액(보통주,억원)": "market_cap_common_100m",
        "액면가(원)": "par_value",
        "발행주식수(보통주)": "shares_outstanding_common",
        "발행주식수(우선주)": "shares_outstanding_preferred",
        "종가(NXT)": "close_price_nxt",
        "유동주식수(주)": "floating_shares",
        "유동비율(%)": "floating_ratio",
        "거래량(NXT, 주)": "volume_nxt",
        "거래대금(NXT,억원)": "trading_value_nxt_100m",
    }

    _index_rename_map = {
        '운용사명': 'asset_manager',
        '항목': 'item',
        '주주구분': 'shareholder_type',
        '구분': 'category',
    }

    _financial_metrics_map = {
        '매출액': 'revenue',
        '영업이익': 'operating_income',
        '당기순이익': 'net_income',
        '지배주주순이익': 'controlling_interest_net_income',
        '자산총계': 'total_assets',
        '부채총계': 'total_liabilities',
        '자본총계': 'total_equity',
        '지배주주지분': 'controlling_interest_equity',
        '자본금': 'capital_stock',
        '영업활동현금흐름': 'op_cash_flow',
        '투자활동현금흐름': 'inv_cash_flow',
        '재무활동현금흐름': 'fin_cash_flow',
        'EPS(원)': 'eps_krw',
        'PER(배)': 'per_ratio',
        'BPS(원)': 'bps_krw',
        'PBR(배)': 'pbr_ratio',
        'DPS(원)': 'dps_krw',
        '배당수익률(%)': 'dividend_yield_ratio',
        'ROE(%)': 'roe_percent',
        'ROA(%)': 'roa_percent',
        '영업이익률(%)': 'operating_margin_ratio',
        '순이익률(%)': 'net_margin_ratio',
        '부채비율(%)': 'debt_ratio',
        '유보율(%)': 'retention_ratio',
        '없음': 'N/A'
    }

    _earning_issue_cols_map = {
        "Workday": "date",
        "제목": "title",
        "정보제공": "provider",
    }

    _analysis_cols_map = {
        "날짜": "date",
        "투자의견": "opinion",
        "목표주가": "target_price",
        "증권사": "broker",
        "Unnamed: 4": "price_changed"
    }

    def __init__(self, stock : str = '005930'):
        self.stock = stock
        self.url = f'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}'
        self.gcs = GCSManager(bucket_name="sayouzone-ai-stocks")
    
    def fundamentals(self, stock : str = None):
        if stock:
            self.stock = stock
            self.url = f'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}'

        today = date.today()
        current_quarter = f"{today.year}-Q{(today.month - 1) // 3 + 1}"
        folder_name = f"/Fundamentals/FnGuide/{self.stock}/{current_quarter}/"

        existing_files = set(self.gcs.list_files(folder_name=folder_name))

        processed_data = self._load_from_gcs(folder_name, existing_files)
        if processed_data is None:
            request = requests.get(self.url)

            soup = BeautifulSoup(request.text, 'lxml')
            tables = soup.find_all('table')

            processed_data = self._df_mapping(tables)

            # GCS에 데이터를 업로드합니다.
            self.upload_to_gcs(processed_data, folder_name=folder_name, existing_files=existing_files)

        # API가 반환할 수 있도록 데이터를 직렬화 가능한 딕셔너리 형태로 가공합니다.
        return_data = {}
        json_names = self.JSON_NAMES
        df_names = self.CSV_NAMES

        for i, json_str in enumerate(processed_data.get("json", [])):
            return_data[json_names[i]] = json.loads(json_str)

        for i, df in enumerate(processed_data.get("to_csv", [])):
            if isinstance(df, pd.Series):
                return_data[df_names[i]] = df.to_dict()
            else:
                # DataFrame의 인덱스를 컬럼으로 변환하여 to_dict에 포함
                return_data[df_names[i]] = df.reset_index().to_dict(orient='records')

        return return_data
    
    def _df_mapping(self, tables):
        market_conditions_df = pd.read_html(io.StringIO(str(tables[0])))[0].dropna()
        my_list = market_conditions_df.to_dict(orient='tight')['data']
        
        values_list = []
        for text in my_list:
            first_values = text[1::2]
            final_values = []
            for value in first_values:
                if '/' in value:
                    split_values = value.replace(' ', '').split('/')
                    final_values.extend(split_values)
                else:
                    final_values.append(value)
            values_list.append(final_values)
        
        values = [item for sublist in values_list for item in sublist]
        
        original_keys = [
            "종가(원)", "전일대비(원)", "수익률(%)", "거래량(주))", "최고가(52주)", "최저가(52주)",
            "거래대금(억원)", "수익률(1M)", "수익률(3M)", "수익률(6M)", "수익률(1Y)", "외국인지분율(%)",
            "시가총액(상장예정포함,억원)", "베타(1년)", "시가총액(보통주,억원)", "액면가(원)",
            "발행주식수(보통주)", "발행주식수(우선주)", "종가(NXT)", "유동주식수(주)", "유동비율(%)",
            "거래량(NXT, 주)", "거래대금(NXT,억원)"
        ]
        json_dict = {self._market_conditions_map.get(key, key): value for key, value in zip(original_keys, values)}
        market_conditions = json.dumps(json_dict, ensure_ascii=False, indent=4)

        # Earning Issue
        earning_issue_df = pd.read_html(io.StringIO(str(tables[1])))[0]
        earning_issue_df = earning_issue_df.rename(columns=self._earning_issue_cols_map)
        earning_issue = earning_issue_df.to_json(orient='records', force_ascii=False, indent=4)

        # Analysis
        analysis_df = pd.read_html(io.StringIO(str(tables[7])))[0]
        analysis_df = analysis_df.rename(columns=self._analysis_cols_map)
        analysis = analysis_df.to_json(orient='records', force_ascii=False, indent=4)

        # Holdings Status
        holdings_status = pd.read_html(io.StringIO(str(tables[2])))[0].set_index('운용사명')
        holdings_status.index.name = self._index_rename_map.get(holdings_status.index.name, holdings_status.index.name)

        # Governance
        governance = pd.read_html(io.StringIO(str(tables[3])))[0].dropna().set_index('항목')
        governance.index.name = self._index_rename_map.get(governance.index.name, governance.index.name)

        # Shareholders
        shareholders = pd.read_html(io.StringIO(str(tables[4])))[0].fillna(0).set_index('주주구분')
        shareholders.index.name = self._index_rename_map.get(shareholders.index.name, shareholders.index.name)

        # Industry Comparison
        industry_comparison = pd.read_html(io.StringIO(str(tables[8])))[0].set_index('구분')
        industry_comparison.index.name = self._index_rename_map.get(industry_comparison.index.name, industry_comparison.index.name)
        industry_comparison = industry_comparison.rename(index=self._financial_metrics_map)
        
        # tables[5] (기업어음)은 데이터 부족으로 건너뜀
        # 문자열 파싱
        bond_rating = (pd.read_html(io.StringIO(str(tables[6])))[0]
                       .T
                       .rename(columns={0: 'raw'})
                       .assign(
                           raw=lambda df: df['raw'].fillna(""),
                           bond_rating=lambda df: df['raw'].str[:3],
                           rating_date=lambda df: df['raw'].str[3:].replace(r'\D', '', regex=True))
                        .drop(columns=['raw']))
        
        financialhighlight_annual = (pd.read_html(io.StringIO(str(tables[11])))[0]
                                     .fillna('없음')
                                     .rename(columns={'IFRS(연결)': 'IFRS'})
                                     .set_index('IFRS'))['Annual']
        financialhighlight_annual = financialhighlight_annual.rename(index=self._financial_metrics_map)
        financialhighlight_annual.index.name = 'metric'
        
        financialhighlight_netquarter = (pd.read_html(io.StringIO(str(tables[12])))[0]
                                     .fillna('없음')
                                     .rename(columns={'IFRS(연결)': 'IFRS'})
                                     .set_index('IFRS'))['Net Quarter']
        financialhighlight_netquarter = financialhighlight_netquarter.rename(index=self._financial_metrics_map)
        financialhighlight_netquarter.index.name = 'metric'
        
        return {
            "json" : [market_conditions, earning_issue, analysis],
            "to_csv" : [holdings_status, governance, shareholders, industry_comparison, bond_rating, financialhighlight_annual, financialhighlight_netquarter]
        }
        
    def _load_from_gcs(self, folder_name: str, existing_files: set[str]):
        """필요한 파일이 모두 존재하면 GCS에서 데이터를 불러옵니다."""
        required_paths = {
            f"{folder_name}{name}.json" for name in self.JSON_NAMES
        } | {
            f"{folder_name}{name}.csv" for name in self.CSV_NAMES
        }

        if not required_paths.issubset(existing_files):
            return None

        try:
            json_payloads = []
            for name in self.JSON_NAMES:
                blob_name = f"{folder_name}{name}.json"
                content = self.gcs.read_file(blob_name)
                if content is None:
                    return None
                json_payloads.append(content)

            csv_payloads = []
            for name in self.CSV_NAMES:
                blob_name = f"{folder_name}{name}.csv"
                content = self.gcs.read_file(blob_name)
                if content is None:
                    return None
                frame = pd.read_csv(io.StringIO(content), index_col=0)
                if name in self.CSV_SERIES_NAMES:
                    frame = frame.squeeze("columns")
                csv_payloads.append(frame)

            return {"json": json_payloads, "to_csv": csv_payloads}
        except Exception as exc:
            print(f"GCS 데이터 로드 중 오류 발생: {exc}")
            return None

    
    def upload_to_gcs(self, processed_data: dict, *, folder_name: str, existing_files: set[str] | None = None):
        """처리된 데이터를 GCS에 업로드합니다."""
        json_names = self.JSON_NAMES
        csv_names = self.CSV_NAMES

        if existing_files is None:
            existing_files = set(self.gcs.list_files(folder_name=folder_name))
        # JSON 데이터 업로드
        for i, json_data in enumerate(processed_data.get("json", [])):
            if i < len(json_names):
                file_name = f"{folder_name}{json_names[i]}.json"
                if file_name in existing_files:
                    continue
                self.gcs.upload_file(
                    source_file=json_data,
                    destination_blob_name=file_name,
                    encoding="utf-8",
                    content_type="application/json; charset=utf-8",
                )
                existing_files.add(file_name)

        # CSV 데이터(DataFrame/Series) 업로드
        for i, df_data in enumerate(processed_data.get("to_csv", [])):
            if i < len(csv_names):
                file_name = f"{folder_name}{csv_names[i]}.csv"
                if file_name in existing_files:
                    continue
                # DataFrame/Series를 CSV 문자열로 변환하여 업로드
                csv_string = df_data.to_csv()
                self.gcs.upload_file(
                    source_file=csv_string,
                    destination_blob_name=file_name,
                    encoding="utf-8",
                    content_type="text/csv; charset=utf-8",
                )
                existing_files.add(file_name)