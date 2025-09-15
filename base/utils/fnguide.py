import requests
from bs4 import BeautifulSoup
import pandas as pd

import json
from google.cloud import storage
storage_client = storage.Client(project='sayonzone-ai')
bucket_name = 'sayouzone-ai-stocks'
bucket = storage_client.get_bucket(bucket_name)

import io

from abc import ABC, abstractmethod
class fundamentals:
    def __init__(self):
        self.site = 'FnGuide'
    def funtamentals_collect(self, company: str):
        url = 'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A' + company

        request = requests.get(url)
        soup = BeautifulSoup(request.text, 'html.parser')

        tables = soup.find_all('table')

        if tables:
            if tables[0]:
                df = pd.read_html(io.StringIO(str(tables[0])))
                original_dict = df[0].dropna().to_dict(orient='tight')
                my_list = original_dict['data']
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
                blob = bucket.blob(f'{self.site}/{company}/{company}_market_status_20250915.json')
                market_status = json.dumps(json_dict, ensure_ascii=False, indent=4)
                blob.upload_from_string(market_status, content_type='application/json')
