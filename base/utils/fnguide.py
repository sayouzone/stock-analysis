import requests
from bs4 import BeautifulSoup

import pandas as pd

import io
class fundamentals:

    @staticmethod
    def funtamentals_collect(company: str):
        url = 'https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A' + company

        request = requests.get(url)
        soup = BeautifulSoup(request.text, 'html.parser')

        tables = soup.find_all('table', class_='us_table_ty1 h_fix zigbg_no')
        for i, table in enumerate(tables):
            table_html_string = io.StringIO(str(table))
            df = pd.read_html(table_html_string)[0]

            df.set_index(df.columns[0], inplace=True)
        return df