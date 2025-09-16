import requests
from bs4 import BeautifulSoup
import pandas as pd

import json
from google.cloud import storage

import io
import re

class Fundamentals:
    def __init__(self, stock):
        self.stock = stock
        self.url = f'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}'

        self.storage_client = storage.Client('sayouzone-ai')
        self.bucket = self.storage_client.bucket('FnGuide')
    
    def get_fundamentals(self):
        request = requests.get(self.url)

        soup = BeautifulSoup(request.text, 'html.parser')
        tables = soup.find_all('table')

        processing_map = self._df_mapping(tables)

        return self.load_to_gcs(processing_map)
    
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
                           .set_index('운용사명', inplace=True))
        
        governance = (pd.read_html(io.StringIO(str(tables[3])))[0]
                      .dropna(inplace=True)
                      .set_index('항목'))

        shareholders = (pd.read_html(io.StringIO(str(tables[4])))[0]
                        .fillna(0)
                        .set_index('주주구분'))

        industry_comparison = (pd.read_html(io.StringIO(str(tables[8])))[0]
                               .set_index('구분', inplace=True))
        
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
                                     .set_index('IFRS', inplace=True))['Annual']
        
        financialhighlight_netquarter = (pd.read_html(io.StringIO(str(tables[12])))[0]
                                     .fillna('없음')
                                     .rename(columns={'IFRS(연결)': 'IFRS'})
                                     .set_index('IFRS', inplace=True))['Net Quarter']
        
        return {
            "json" : [market_conditions, earning_issue, analysis],
            "to_csv" : [holdings_status, governance, shareholders, industry_comparison, bond_rating, financialhighlight_annual, financialhighlight_netquarter]
        }
        
    
    def load_to_gcs(self, processing_map: dict):
        data_dict = {}
        for key, value in processing_map.items():
            if key == "json":
                for json_data in value:
                    file_name = f"{self.stock}_{json_data}.json"
                    blob = self.bucket.blob(file_name)

                    file_content = blob.download_as_string()
                    
                    data_dict[json_data] = file_content.decode('utf-8')
            elif key == "to_csv":
                for csv_data in value:
                    try:
                        file_name = f"{self.stock}_{csv_data}.csv"
                        blob = self.bucket.blob(file_name)
                        file_content = blob.download_as_string()
                        df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
                        data_dict[csv_data] = df
                    except Exception as e:
                        print(f"CSV 파일 읽기 오류: {e}")
                        # 다른 파일 형식이면 content 자체를 반환
                        data_dict[csv_data] = file_content.decode('utf-8')
        return data_dict