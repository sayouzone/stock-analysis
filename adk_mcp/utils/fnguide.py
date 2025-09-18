import requests
from bs4 import BeautifulSoup
import pandas as pd
import lxml

import json
from .gcpmanager import GCSManager

import io
import re

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

    def __init__(self, stock : str = '005930'):
        self.stock = stock
        self.url = f'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}'
        self.gcs = GCSManager(bucket_name="sayouzone-ai-stocks")
    
    def fundamentals(self, stock : str = None):
        if stock:
            self.stock = stock
            self.url = f'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}'

        folder_name = f"/Fundamentals/FnGuide/{self.stock}/"
        existing_files = set(self.gcs.list_files(folder_name=folder_name))

        processed_data = self._load_from_gcs(folder_name, existing_files)
        if processed_data is None:
            request = requests.get(self.url)

            soup = BeautifulSoup(request.text, 'lxml')
            tables = soup.find_all('table')

            processed_data = self._df_mapping(tables)

            # GCS에 데이터를 업로드합니다.
            self.upload_to_gcs(processed_data, existing_files=existing_files)

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
        market_conditions = (pd.read_html(io.StringIO(str(tables[0])))[0]
                             .dropna()
                             .to_dict(orient='tight'))

        my_list = market_conditions['data']
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
        json_dict = {
            "종가(원)": values[0],
            "전일대비(원)": values[1],
            "수익률(%)": values[2],
            "거래량(주))": values[3],
            "최고가(52주)": values[4],
            "최저가(52주)": values[5],
            "거래대금(억원)": values[6],
            "수익률(1M)": values[7],
            "수익률(3M)": values[8],
            "수익률(6M)": values[9],
            "수익률(1Y)": values[10],
            "외국인지분율(%)": values[11],
            "시가총액(상장예정포함,억원)": values[12],
            "베타(1년)": values[13],
            "시가총액(보통주,억원)": values[14],
            "액면가(원)": values[15],
            "발행주식수(보통주)": values[16],
            "발행주식수(우선주)": values[17],
            "종가(NXT)": values[18],
            "유동주식수(주)": values[19],
            "유동비율(%)": values[20],
            "거래량(NXT, 주)": values[21],
            "거래대금(NXT,억원)": values[22],
        }
        market_conditions = json.dumps(json_dict, ensure_ascii=False, indent=4)

        # 단순 json
        earning_issue = (pd.read_html(io.StringIO(str(tables[1])))[0]
                        .to_json(orient='records', force_ascii=False, indent=4))
        
        analysis = (pd.read_html(io.StringIO(str(tables[7])))[0]
                    .to_json(orient='records', force_ascii=False, indent=4))

        holdings_status = (pd.read_html(io.StringIO(str(tables[2])))[0]
                           .set_index('운용사명'))
        
        governance = (pd.read_html(io.StringIO(str(tables[3])))[0]
                      .dropna()
                      .set_index('항목'))

        shareholders = (pd.read_html(io.StringIO(str(tables[4])))[0]
                        .fillna(0)
                        .set_index('주주구분'))

        industry_comparison = pd.read_html(io.StringIO(str(tables[8])))[0].set_index('구분')
        
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
        
        financialhighlight_netquarter = (pd.read_html(io.StringIO(str(tables[12])))[0]
                                     .fillna('없음')
                                     .rename(columns={'IFRS(연결)': 'IFRS'})
                                     .set_index('IFRS'))['Net Quarter']
        
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

    
    def upload_to_gcs(self, processed_data: dict, *, existing_files: set[str] | None = None):
        """처리된 데이터를 GCS에 업로드합니다."""
        json_names = self.JSON_NAMES
        csv_names = self.CSV_NAMES

        folder_name = f"/FnGuide/{self.stock}/"
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
                file_name = f"{folder_name}" + f"{csv_names[i]}.csv"
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
