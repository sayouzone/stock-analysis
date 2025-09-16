import OpenDartReader
import pandas as pd
import re
import time
import requests
from utils.companydict import companydict
from utils import gcpmanager
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
import os
from contextlib import contextmanager
from typing import cast

@contextmanager
def change_dir(destination):
    """
    Context manager to temporarily change the current working directory.
    """
    cwd = None # Initialize cwd
    try:
        cwd = os.getcwd()
        os.chdir(destination)
        yield
    finally:
        # cwd가 None이 아닌 경우에만 원래 디렉토리로 변경합니다.
        if cwd is not None:
            os.chdir(cwd)

load_dotenv()

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"

class OpenDartCrawler:
    bucket = None

    def __init__(
        self,
        company: str = "005930",
    ):
        # 환경 변수에서 버킷 이름 가져오기
        bucket_name = "sayouzone-ai-stocks"
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME이 .env 파일에 설정되지 않았습니다!")

        dart_api_key = "746df482bd123aa8acc6b8df2cd650bb67083299"
        if not dart_api_key:
            raise ValueError("DART_API_KEY not found in environment variables.")

        if os.environ.get('K_SERVICE'):
            with change_dir('/tmp'):
                self.dart = OpenDartReader(dart_api_key) # pyright: ignore[reportCallIssue]
        else:
            self.dart = OpenDartReader(dart_api_key) # pyright: ignore[reportCallIssue]

        self.company = company

        # GCP CLient and Bucket Initialization
        self.gcs_manager = gcpmanager.GCSManager()

    def fundamentals(
        self,
        company: str = "005930",
        start_date: str = "2025-01-01",
        end_date: str = "2025-08-19",
        count: int = 5
        ):

        if company:
            self.company = company
        
        self.folder_name = companydict.get_company(self.company)

        folder_path = f"OpenDart/{self.folder_name}/"

        df = self.dart.list(self.company, start=start_date, end=end_date)
        df["report_nm"] = df["report_nm"].str.strip()

        gcs_files = self.gcs_manager.list_files(folder_name=folder_path)
        existing_rcept_nos = {f.split('_')[-1].replace('.pdf', '') for f in gcs_files}

        is_already_downloaded = df["rcept_no"].apply(lambda x: x in existing_rcept_nos)

        is_ir_meeting = df["report_nm"] == "기업설명회(IR)개최(안내공시)"

        df_filtered = df[~is_already_downloaded & ~is_ir_meeting]

        df_refilter = df_filtered[["rcept_no", "flr_nm"]].head(count).copy()

        for row in df_refilter.itertuples():
            # 1. attach_files 메서드를 호출하여 파일 목록을 가져옵니다.
            #    이 메서드는 내부에 이미 예외 처리가 되어있다고 가정합니다.
            files = self.dart.attach_files(str(row.rcept_no))

            # 2. 만약 위 메서드가 실패하여 파일 목록이 비어있다면, 
            #    안전하게 보강된 로직으로 한 번 더 시도합니다.
            if not files:
                url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row.rcept_no}"
                try:
                    r = requests.get(url, headers={"User-Agent": USER_AGENT})
                    r.raise_for_status() # HTTP 오류가 있으면 예외 발생

                    pattern = r"openPdfDownload\('(\d+)',\s*'(\d+)'\)"
                    match = re.findall(pattern, r.text)
                    
                    if match:
                        rcp_no, dcm_no = match[0]
                        download_url = f"http://dart.fss.or.kr/pdf/download/main.do?rcpNo={rcp_no}&dcm_no={dcm_no}"
                        
                        r_download = requests.get(download_url, headers={"User-Agent": USER_AGENT})
                        r_download.raise_for_status()
                        
                        soup = BeautifulSoup(r_download.text, "lxml")
                        table = soup.find("table")
                        
                        attach_files_dict = {}
                        # --- Pylance 오류를 해결하는 근본적인 수정 ---
                        if isinstance(table, Tag):
                            # .tbody 대신 .find('tbody')를 명시적으로 사용
                            tbody = table.find("tbody")
                            if isinstance(tbody, Tag):
                                for tr in tbody.find_all("tr"):
                                    if isinstance(tr, Tag):
                                        tds = tr.find_all("td")
                                    
                                    # tds, a, href가 모두 존재하는지 안전하게 확인
                                        if len(tds) > 1:
                                            td_0 = tds[0]
                                            td_1 = tds[1]
                                            if isinstance(td_0, Tag) and isinstance(td_1, Tag):
                                                # Pylance가 타입을 정확히 인지하도록 cast 사용
                                                a_tag = cast(Tag, td_1).find('a')
                                                if isinstance(a_tag, Tag):
                                                    href = a_tag.get('href')
                                                    # href가 존재할 경우, str()로 명시적 변환하여 '+' 연산 오류 방지
                                                    if href is not None:
                                                        fname = td_0.text.strip()
                                                        flink = "http://dart.fss.or.kr" + str(href)
                                                        attach_files_dict[fname] = flink
                        files = attach_files_dict

                except requests.exceptions.RequestException as e:
                    print(f"네트워크 오류 발생 (rcpNo: {row.rcept_no}): {e}")
                    # 오류 발생 시 이 row는 건너뜁니다.
                    time.sleep(3)
                    continue
                except Exception as e:
                    print(f"파싱 중 알 수 없는 오류 발생 (rcpNo: {row.rcept_no}): {e}")
                    time.sleep(3)
                    continue

            # 3. 최종적으로 얻은 파일 목록을 처리합니다.
            if not files:
                print(f"파일 목록을 찾지 못했습니다 (rcpNo: {row.rcept_no})")
                time.sleep(3)
                continue

            for title, url in files.items():
                fn = title if title else url.split("/")[-1]
                if fn.endswith(".html"):
                    continue

                # GCP Upload
                try:
                    file_name = fn.replace(".pdf", f"_{row.rcept_no}.pdf")
                    r_file = requests.get(url, stream=True, headers={"User-Agent": USER_AGENT})
                    r_file.raise_for_status()
                    
                    self.gcs_manager.upload_file(
                        source_file=r_file.content,
                        destination_blob_name=folder_path + file_name
                    )
                except requests.exceptions.RequestException as e:
                    print(f"파일 다운로드/업로드 실패 (URL: {url}): {e}")
                    continue

            time.sleep(3)