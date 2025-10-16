import requests
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

import pandas as pd
import json
from io import StringIO

from google.cloud import storage

def get_fnguide_fundamentals(company:str):
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{company}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        # 버튼 눌러서 테이블 펼치기
        button_selector = ".btn_acdopen"
    
        while True:
            try:
                buttons = page.locator(f"{button_selector}:visible").all()
                if len(buttons) == 0:
                    break

                button = buttons[0]
                try:
                    button.wait_for(state="visible", timeout=2000)
                    button.scroll_into_view_if_needed()
                    button.click(timeout=2000, force=False)
                    page.wait_for_timeout(500)

                except TimeoutError:
                    try:
                        button.click(force=True)
                        page.wait_for_timeout(500)
                    except:
                        print(f"버튼 클릭 실패, 다음으로 진행")
                        page.wait_for_timeout(500)
                        continue

            except Exception as e:
                print(e)
                break

        # 모든 테이블 데이터 수집
        result_dict = {}
        table_titles = ["포괄손익계산서", "재무상태표", "현금흐름표"]

        for title in table_titles:
            try:
                print(f"\n{title} 데이터 수집 중...")
                table_locator = page.locator("table:visible").filter(has_text=title)

                # 1. thead에서 날짜/기간 데이터 추출 (DataFrame의 index가 됨)
                index_list = []
                thead_ths = (table_locator.locator("thead:visible")
                                          .locator("th:visible")
                                          .all())
                for th in thead_ths:
                    text = th.inner_text().strip()
                    if text:  # 빈 문자열 제외
                        index_list.append(text)

                print(f"  - 기간 데이터: {index_list}")

                # 2. tbody에서 항목별 데이터 수집
                data_dict = {}  # {컬럼명_튜플: [값들]}
                tbody_trs = (table_locator.locator("tbody:visible")
                                          .locator("tr:visible")
                                          .all())

                # 마지막으로 나온 span 텍스트를 저장 (상위 카테고리)
                last_span_text = None

                for tr in tbody_trs:
                    try:
                        target_div = tr.locator("div").first

                        th = target_div.locator("th")
                        span = th.locator("span").first

                        column_name_tuple = None

                        # 1. span이 존재하는 경우: 새로운 상위 카테고리 시작
                        if span.count() > 0:
                            span_text = span.inner_text().strip()
                            th_text = th.inner_text().strip()
                            last_span_text = span_text  # 상위 카테고리 저장
                            column_name_tuple = (span_text, th_text)
                        # 2. span은 없지만 th가 존재하는 경우: 이전 상위 카테고리의 하위 항목
                        elif th.count() > 0:
                            th_text = th.inner_text().strip()
                            # 이전 span이 있으면 멀티인덱스, 없으면 단일 인덱스
                            if last_span_text:
                                column_name_tuple = (last_span_text, th_text)
                            else:
                                column_name_tuple = (th_text, "")
                        # 3. 둘 다 없는 경우: div 텍스트 사용
                        else:
                            div_text = target_div.inner_text().strip()
                            if last_span_text:
                                column_name_tuple = (last_span_text, div_text)
                            else:
                                column_name_tuple = (div_text, "")

                        # td 값들 추출
                        values = [td.inner_text().strip() for td in tr.locator("td").all()]

                        # 데이터 딕셔너리에 추가
                        if column_name_tuple and values:
                            data_dict[column_name_tuple] = values

                    except Exception as e:
                        print(f"  - 행 처리 중 에러: {e}")
                        continue

                # 3. DataFrame 생성
                if data_dict and index_list:
                    df = pd.DataFrame(data_dict, index=index_list)

                    # 4. 멀티인덱스로 columns 변환
                    df.columns = pd.MultiIndex.from_tuples(df.columns)

                    result_dict[title] = df
                    print(f"  - 완료! DataFrame shape: {df.shape}")
                else:
                    print(f"  - 데이터 없음")

            except Exception as e:
                print(f"{title} 수집 실패: {e}")
                continue

        browser.close()

        return result_dict

if __name__ == "__main__":
    get_fnguide_fundamentals("005930")
