"""
FnGuide 크롤러 - 정적/동적 재무 데이터 수집 + GCS 저장

FnGuide 웹사이트에서 기업 재무 정보를 크롤링하여 GCS에 저장합니다.

주요 기능:
- 정적 테이블: requests + pandas.read_html로 시장 상황, 지배구조 등 수집
- 동적 테이블: Playwright로 포괄손익계산서, 재무상태표, 현금흐름표 수집
- GCS 연동: 파티션 기반 폴더 구조(year=YYYY/quarter=Q/)로 데이터 저장
- 캐싱: use_cache 파라미터로 기존 데이터 재사용
- 레거시 호환: 구 폴더 구조 및 오타 폴더명 지원

사용 예시:
    >>> crawler = FnGuideCrawler(stock="005930")
    >>> data = crawler.get_all_fundamentals(use_cache=True)
    >>> print(data.keys())
"""

import requests
from playwright.sync_api import sync_playwright, TimeoutError
import pandas as pd
from datetime import date
from io import StringIO
import json


# 파티션 폴더명 접두사 (GCS 저장 경로용)
QUARTER_PREFIX = "quarter="


class FnGuideCrawler:
    """FnGuide 데이터 크롤러 - 동적/정적 테이블 수집 + GCS 저장"""

    # 정적 HTML에서 가져올 테이블 (원본 utils/fnguide.py)
    STATIC_TABLE_MAP = [
        ("market_conditions", 0),
        ("earning_issue", 1),
        ("holdings_status", 2),
        ("governance", 3),
        ("shareholders", 4),
        ("bond_rating", 6),
        ("analysis", 7),
        ("industry_comparison", 8),
        ("financialhighlight_annual", 11),
        ("financialhighlight_netquarter", 12),
    ]

    # Playwright로 가져올 동적 테이블
    DYNAMIC_TABLE_TITLES = ["포괄손익계산서", "재무상태표", "현금흐름표"]

    def __init__(self, stock: str = "005930", bucket_name: str = "sayouzone-ai-stocks"):
        """
        FnGuide 크롤러 초기화

        Args:
            stock: 종목 코드 (6자리, 예: "005930")
            bucket_name: GCS 버킷 이름
        """
        self.stock = stock
        self.static_url = f"https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}"
        self.dynamic_url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{stock}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701"
        self._translator = _FnGuideTranslator()

        # GCS Manager 초기화
        from utils.gcpmanager import GCSManager
        self.gcs = GCSManager(bucket_name=bucket_name)

    def get_all_fundamentals(
        self,
        stock: str | None = None,
        *,
        use_cache: bool = False,
        overwrite: bool = True,
    ) -> dict[str, str | None]:
        """
        재무제표 3종을 yfinance와 동일한 스키마로 반환 (GCS 캐싱/저장 포함)

        Args:
            stock: 종목 코드 (None이면 초기화 시 설정한 종목 사용)
            use_cache: True일 경우 GCS에서 캐시된 데이터 조회 시도
            overwrite: False일 경우 기존 파일이 있으면 덮어쓰지 않음

        Returns:
            dict: {
                "ticker": str,
                "country": str,
                "balance_sheet": str | None,      # JSON 문자열
                "income_statement": str | None,   # JSON 문자열
                "cash_flow": str | None           # JSON 문자열
            }
        """
        if stock:
            self.stock = stock
            self.static_url = f"https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}"
            self.dynamic_url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{stock}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701"

        # GCS 폴더 구조 설정 (파티션 기반: year=YYYY/quarter=Q/)
        today = date.today()
        quarter = (today.month - 1) // 3 + 1  # 1~3월=1, 4~6월=2, 7~9월=3, 10~12월=4
        year_partition = f"year={today.year}"
        quarter_partition = f"{QUARTER_PREFIX}{quarter}"
        folder_name = (
            f"Fundamentals/FnGuide/{year_partition}/"
            f"{quarter_partition}/"
        )
        file_base = self.stock

        # 레거시 호환성을 위한 폴더 경로 설정
        misspelled_folder = self._partition_alias(folder_name)  # quater= 오타 지원
        legacy_folder = self._legacy_folder_from_current(
            folder_name, stock=self.stock, year=today.year, quarter=quarter
        )
        existing_files: dict[str, str] | None = None
        cached_data: dict[str, list[dict]] | None = None

        # 캐시 사용 로직
        if use_cache:
            # GCS에서 기존 파일 목록 수집
            existing_files = self._collect_existing_files(
                folder_name,
                misspelled_folder,
                legacy_folder,
            )
            # 캐시된 데이터 로드 시도
            cached_data = self._load_from_gcs(
                folder_name,
                file_base,
                existing_files,
                legacy_folder,
            )
            # 캐시가 있고 overwrite=False이면 캐시 반환
            if cached_data is not None and not overwrite:
                return cached_data

        # overwrite=False이고 아직 파일 목록을 가져오지 않았다면 수집
        if existing_files is None and not overwrite:
            existing_files = self._collect_existing_files(
                folder_name,
                misspelled_folder,
                legacy_folder,
            )

        # 데이터 수집
        raw_data = {}

        # 1. 정적 테이블 수집은 GCS에만 저장 (기존 호환성 유지)
        static_data = self._get_static_tables()
        raw_data.update(static_data)

        # 2. 동적 테이블 수집 (Playwright로 재무제표 3종)
        dynamic_data = self._get_dynamic_tables()
        raw_data.update(dynamic_data)

        # 3. GCS 업로드용 CSV 페이로드 생성
        csv_payloads: dict[str, str] = {}
        for name, records in raw_data.items():
            if records:  # 빈 리스트가 아닐 때만 CSV 변환
                try:
                    df = pd.DataFrame(records)
                    csv_payloads[name] = df.to_csv(index=False)
                except Exception as e:
                    print(f"'{name}' CSV 변환 실패: {e}")
                    csv_payloads[name] = ""
            else:
                csv_payloads[name] = ""

        # 4. GCS에 업로드
        self.upload_to_gcs(
            csv_payloads,
            folder_name=folder_name,
            file_base=file_base,
            existing_files=existing_files,
            overwrite=overwrite,
            legacy_folder=legacy_folder,
        )

        # 5. yfinance와 동일한 스키마로 재무제표 3종만 반환
        # FnGuide 한글 키명 → 영문 키명 매핑
        result = {
            "ticker": self.stock,
            "country": "KR",
            "balance_sheet": None,
            "income_statement": None,
            "cash_flow": None
        }

        # 재무상태표 (포괄손익계산서 → income_statement)
        if "포괄손익계산서" in dynamic_data and dynamic_data["포괄손익계산서"]:
            result["income_statement"] = json.dumps(
                dynamic_data["포괄손익계산서"],
                ensure_ascii=False
            )

        # 재무상태표
        if "재무상태표" in dynamic_data and dynamic_data["재무상태표"]:
            result["balance_sheet"] = json.dumps(
                dynamic_data["재무상태표"],
                ensure_ascii=False
            )

        # 현금흐름표
        if "현금흐름표" in dynamic_data and dynamic_data["현금흐름표"]:
            result["cash_flow"] = json.dumps(
                dynamic_data["현금흐름표"],
                ensure_ascii=False
            )

        return result

    def fundamentals(
        self,
        stock: str | None = None,
        *,
        use_cache: bool = False,
        overwrite: bool = True,
    ) -> dict[str, str | None]:
        """
        기존 시스템 호환성을 위한 별칭 메서드

        routers/fundamentals.py에서 호출하는 메서드명과 일치시키기 위한
        래퍼 메서드입니다. 내부적으로 get_all_fundamentals()를 호출합니다.

        Args:
            stock: 종목 코드 (None이면 초기화 시 설정한 종목 사용)
            use_cache: True일 경우 GCS에서 캐시된 데이터 조회 시도
            overwrite: False일 경우 기존 파일이 있으면 덮어쓰지 않음

        Returns:
            dict: {
                "ticker": str,
                "country": str,
                "balance_sheet": str | None,      # JSON 문자열
                "income_statement": str | None,   # JSON 문자열
                "cash_flow": str | None           # JSON 문자열
            }
        """
        return self.get_all_fundamentals(
            stock=stock,
            use_cache=use_cache,
            overwrite=overwrite,
        )

    def _get_static_tables(self) -> dict[str, list[dict]]:
        """
        정적 HTML 테이블 수집

        requests로 HTML을 가져온 후 pandas.read_html()로 파싱하여
        시장 상황, 지배구조, 주주 현황 등의 정적 데이터를 수집

        Returns:
            dict[str, list[dict]]: 테이블명을 키로 하는 레코드 딕셔너리
        """
        response = requests.get(self.static_url)
        response.raise_for_status()
        tables = pd.read_html(response.text)

        datasets = {}
        for name, index in self.STATIC_TABLE_MAP:
            if index < len(tables):
                frame = tables[index]
                # 한글 컬럼명을 영문으로 번역
                frame = self._translator.translate_dataframe(
                    frame,
                    stock_code=self.stock,
                )
                datasets[name] = frame.to_dict(orient="records")
            else:
                print(f"경고: '{name}'에 해당하는 테이블(index {index})을 찾지 못해 빈 데이터로 저장합니다.")
                datasets[name] = []

        return datasets

    def _get_dynamic_tables(self) -> dict[str, list[dict]]:
        """
        동적 테이블 수집 (Playwright 사용)

        JavaScript로 렌더링되는 재무제표 3종(포괄손익계산서, 재무상태표, 현금흐름표)을
        Playwright로 크롤링하여 멀티인덱스 DataFrame으로 구조화

        Returns:
            dict[str, list[dict]]: 테이블명을 키로 하는 레코드 딕셔너리
        """
        result_dict = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.dynamic_url, wait_until="networkidle")

            # 접힌 테이블을 모두 펼치기 위해 아코디언 버튼 자동 클릭
            button_selector = ".btn_acdopen"

            while True:
                try:
                    # 화면에 보이는 버튼 찾기
                    buttons = page.locator(f"{button_selector}:visible").all()
                    if len(buttons) == 0:  # 더 이상 클릭할 버튼이 없으면 종료
                        break

                    button = buttons[0]
                    try:
                        # 버튼이 클릭 가능한 상태가 될 때까지 대기
                        button.wait_for(state="visible", timeout=2000)
                        button.scroll_into_view_if_needed()
                        button.click(timeout=2000, force=False)
                        page.wait_for_timeout(500)  # DOM 업데이트 대기

                    except TimeoutError:
                        # 일반 클릭 실패 시 강제 클릭 시도
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
            for title in self.DYNAMIC_TABLE_TITLES:
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

                    # 마지막으로 나온 span 텍스트를 저장 (상위 카테고리 추적용)
                    last_span_text = None

                    for tr in tbody_trs:
                        try:
                            target_div = tr.locator("div").first

                            th = target_div.locator("th")
                            span = th.locator("span").first

                            column_name_tuple = None

                            # 1. span이 존재하는 경우: 새로운 상위 카테고리 시작
                            #    예: <span>유동자산</span> → ("유동자산", "유동자산")
                            if span.count() > 0:
                                span_text = span.inner_text().strip()
                                th_text = th.inner_text().strip()
                                last_span_text = span_text  # 상위 카테고리 저장
                                column_name_tuple = (span_text, th_text)

                            # 2. span은 없지만 th가 존재하는 경우: 이전 상위 카테고리의 하위 항목
                            #    예: <th>현금및현금성자산</th> → ("유동자산", "현금및현금성자산")
                            elif th.count() > 0:
                                th_text = th.inner_text().strip()
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

                            # td 값들 추출 (각 기간별 데이터)
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
                        #    예: ("유동자산", "현금및현금성자산"), ("유동자산", "단기투자자산") ...
                        df.columns = pd.MultiIndex.from_tuples(df.columns)

                        result_dict[title] = df.to_dict(orient="records")
                        print(f"  - 완료! DataFrame shape: {df.shape}")
                    else:
                        print(f"  - 데이터 없음")
                        result_dict[title] = []

                except Exception as e:
                    print(f"{title} 수집 실패: {e}")
                    result_dict[title] = []

            browser.close()

        return result_dict

    # ==================== GCS 연동 메서드 ====================

    def _load_from_gcs(
        self,
        folder_name: str,
        file_base: str,
        existing_files: dict[str, str] | None,
        legacy_folder: str | None,
    ) -> dict[str, list[dict]] | None:
        """
        GCS에서 캐시된 데이터 로드

        Args:
            folder_name: 현재 파티션 폴더 경로 (예: "Fundamentals/FnGuide/year=2025/quarter=1/")
            file_base: 파일명 접두사 (종목 코드)
            existing_files: 기존 파일 목록 (None이면 자동 수집)
            legacy_folder: 레거시 폴더 경로

        Returns:
            dict[str, list[dict]] | None: 캐시된 데이터 또는 None (캐시 없음)
        """
        if existing_files is None:
            alias_folder = self._partition_alias(folder_name)
            existing_files = self._collect_existing_files(
                folder_name,
                alias_folder,
                legacy_folder,
            )

        cached_data: dict[str, list[dict]] = {}

        # 정적 + 동적 테이블 모두 확인
        all_table_names = [name for name, _ in self.STATIC_TABLE_MAP] + self.DYNAMIC_TABLE_TITLES

        for name in all_table_names:
            new_blob = f"{folder_name}{file_base}_{name}.csv"
            candidate_names = self._expand_candidates(new_blob)
            candidate_names.extend(
                self._legacy_candidate_blobs(
                    name=name,
                    file_base=file_base,
                    existing_files=existing_files,
                )
            )

            # 후보 중 실제 존재하는 파일 찾기
            selected_blob = self._resolve_existing_blob(
                candidate_names,
                existing_files,
            )
            if not selected_blob:
                return None  # 하나라도 없으면 전체 캐시 무효

            # GCS에서 파일 읽기
            content = self.gcs.read_file(selected_blob)
            if content is None:
                return None

            # CSV 또는 JSON 파싱
            if selected_blob.endswith(".csv"):
                try:
                    frame = pd.read_csv(StringIO(content))
                except pd.errors.EmptyDataError:
                    frame = pd.DataFrame()
                cached_data[name] = frame.to_dict(orient="records")
            else:
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    return None
                if isinstance(payload, list):
                    cached_data[name] = payload
                else:
                    cached_data[name] = []

        return cached_data

    def upload_to_gcs(
        self,
        serialized_payloads: dict[str, str],
        *,
        folder_name: str,
        file_base: str,
        existing_files: dict[str, str] | None = None,
        overwrite: bool = True,
        legacy_folder: str | None = None,
    ) -> None:
        """
        CSV 페이로드를 GCS에 업로드

        Args:
            serialized_payloads: {테이블명: CSV 문자열} 딕셔너리
            folder_name: 업로드 폴더 경로
            file_base: 파일명 접두사 (종목 코드)
            existing_files: 기존 파일 목록
            overwrite: True일 경우 기존 파일 덮어쓰기
            legacy_folder: 레거시 폴더 경로
        """
        if legacy_folder is None:
            legacy_folder = self._legacy_folder_from_current(
                folder_name, stock=self.stock
            )

        if existing_files is None:
            alias_folder = self._partition_alias(folder_name) if not overwrite else None
            collect_legacy = legacy_folder if not overwrite else None
            existing_files = self._collect_existing_files(
                folder_name,
                alias_folder,
                collect_legacy,
            )

        # 폴더 생성 (플레이스홀더 파일)
        self.gcs.ensure_folder(folder_name)

        for name, payload in serialized_payloads.items():
            new_blob = f"{folder_name}{file_base}_{name}.csv"
            candidate_names = self._expand_candidates(new_blob)
            candidate_names.extend(
                self._legacy_candidate_blobs(
                    name=name,
                    file_base=file_base,
                    existing_files=existing_files,
                )
            )

            # overwrite=False이고 이미 파일이 있으면 스킵
            if not overwrite:
                if self._resolve_existing_blob(candidate_names, existing_files):
                    continue

            # GCS 업로드
            target_blob_name = new_blob.lstrip("/")
            uploaded = self.gcs.upload_file(
                source_file=payload,
                destination_blob_name=target_blob_name,
                encoding="utf-8",
                content_type="text/csv; charset=utf-8",
            )

            # 업로드 성공 시 파일 목록 갱신
            if uploaded and existing_files is not None:
                existing_files[target_blob_name] = target_blob_name
                normalized = target_blob_name.lstrip("/")
                existing_files.setdefault(normalized, target_blob_name)
                existing_files.setdefault(f"/{target_blob_name}", target_blob_name)

    def _collect_existing_files(
        self,
        primary_folder: str,
        *additional_folders: str | None,
    ) -> dict[str, str]:
        """
        GCS에서 기존 파일 목록 수집

        여러 폴더(현재 파티션, 오타 폴더, 레거시 폴더)에서 파일을 찾아
        정규화된 경로 매핑 생성

        Args:
            primary_folder: 주 폴더 경로
            *additional_folders: 추가 폴더 경로들

        Returns:
            dict[str, str]: {blob 이름 변형: 실제 blob 경로} 매핑
        """
        mapping: dict[str, str] = {}
        seen_folders: set[str] = set()

        for candidate_folder in (primary_folder, *additional_folders):
            if not candidate_folder or candidate_folder in seen_folders:
                continue
            seen_folders.add(candidate_folder)

            # GCS에서 폴더 내 파일 목록 가져오기
            for blob_name in self.gcs.list_files(folder_name=candidate_folder):
                mapping.setdefault(blob_name, blob_name)
                # 앞의 '/' 제거한 버전도 매핑에 추가
                normalized = blob_name.lstrip("/")
                mapping.setdefault(normalized, blob_name)

        return mapping

    def _expand_candidates(self, blob_name: str) -> list[str]:
        """
        Blob 이름 정규화 후보 생성

        앞에 '/'가 있는 경우와 없는 경우 모두 고려

        Args:
            blob_name: blob 이름

        Returns:
            list[str]: 후보 이름 리스트
        """
        normalized = blob_name.lstrip("/")
        if normalized and normalized != blob_name:
            return [blob_name, normalized]
        return [blob_name]

    def _legacy_candidate_blobs(
        self,
        *,
        name: str,
        file_base: str,
        existing_files: dict[str, str],
    ) -> list[str]:
        """
        레거시 폴더 구조의 후보 blob 탐색

        구 폴더 구조(/Fundamentals/FnGuide/{stock}/{year}-Q{quarter}/raw/)에서
        해당 테이블 파일이 있는지 확인

        Args:
            name: 테이블명
            file_base: 종목 코드
            existing_files: 기존 파일 목록

        Returns:
            list[str]: 레거시 후보 blob 경로 리스트
        """
        suffixes = (f"_{name}.json", f"_{name}.csv")
        matches: list[str] = []
        seen: set[str] = set()

        for key, actual in existing_files.items():
            if actual in seen:
                continue
            normalized_key = key.lstrip("/")

            # 종목 코드가 포함되어 있는지 확인
            if file_base not in normalized_key:
                continue

            # 테이블명 확장자로 끝나는지 확인
            if not normalized_key.endswith(suffixes):
                continue

            # 새 파티션 폴더는 제외 (레거시만)
            if normalized_key.startswith("Fundamentals/FnGuide/year="):
                continue

            seen.add(actual)
            matches.extend(self._expand_candidates(actual))

        return matches

    def _resolve_existing_blob(
        self,
        candidate_names: list[str],
        existing_files: dict[str, str],
    ) -> str | None:
        """
        후보 blob 중 실제 존재하는 blob 반환

        Args:
            candidate_names: 후보 blob 이름 리스트
            existing_files: 기존 파일 목록

        Returns:
            str | None: 실제 존재하는 blob 경로 또는 None
        """
        for candidate in candidate_names:
            if candidate in existing_files:
                return existing_files[candidate]
            normalized = candidate.lstrip("/")
            if normalized in existing_files:
                return existing_files[normalized]
        return None

    def _legacy_folder_from_current(
        self,
        folder_name: str,
        *,
        stock: str,
        year: int | None = None,
        quarter: int | None = None,
    ) -> str | None:
        """
        현재 파티션 폴더로부터 레거시 폴더 경로 생성

        새 구조: Fundamentals/FnGuide/year=2025/quarter=1/
        레거시: /Fundamentals/FnGuide/005930/2025-Q1/raw/

        Args:
            folder_name: 현재 폴더 경로
            stock: 종목 코드
            year: 연도 (None이면 폴더명에서 추출)
            quarter: 분기 (None이면 폴더명에서 추출)

        Returns:
            str | None: 레거시 폴더 경로 또는 None
        """
        parts = folder_name.rstrip("/").split("/")
        if len(parts) < 4:
            return None
        if parts[0] != "Fundamentals" or parts[1] != "FnGuide":
            return None

        year_part, quarter_part = parts[2], parts[3]

        # year=YYYY, quarter=Q 형식 확인
        if not year_part.startswith("year=") or not (
            quarter_part.startswith(QUARTER_PREFIX)
            or quarter_part.startswith("quater=")  # 오타 지원
        ):
            return None

        year_value = str(year if year is not None else year_part.split("=", 1)[1])
        quarter_value = str(quarter if quarter is not None else quarter_part.split("=", 1)[1])
        legacy_quarter = f"{year_value}-Q{quarter_value}"

        return f"/Fundamentals/FnGuide/{stock}/{legacy_quarter}/raw/"

    def _partition_alias(self, folder_name: str) -> str | None:
        """
        오타 폴더명 (quater → quarter) 처리

        초기 구현에서 "quarter" 대신 "quater"로 오타가 있었던 것을 지원

        Args:
            folder_name: 원본 폴더 경로

        Returns:
            str | None: 오타 버전 폴더 경로 또는 None
        """
        if QUARTER_PREFIX not in folder_name:
            return None
        return folder_name.replace(QUARTER_PREFIX, "quater=")


class _FnGuideTranslator:
    """
    FnGuide 한글 컬럼명을 영문으로 번역하는 헬퍼 클래스

    테이블의 한글 헤더를 미리 정의된 영문 이름으로 변환하여
    데이터 분석 시 일관성 있는 컬럼명 사용 가능
    """

    # 한글 → 영문 컬럼명 매핑 딕셔너리
    _COLUMN_MAP = {
        "잠정실적발표예정일": "tentative_results_announcement_date",
        "예상실적(영업이익, 억원)": "expected_operating_profit_billion_krw",
        "3개월전예상실적대비(%)": "expected_operating_profit_vs_3m_pct",
        "전년동기대비(%)": "year_over_year_pct",
        "운용사명": "asset_manager_name",
        "보유수량": "shares_held",
        "시가평가액": "market_value_krw",
        "상장주식수내비중": "share_of_outstanding_shares_pct",
        "운용사내비중": "manager_portfolio_ratio_pct",
        "항목": "item",
        "보통주": "common_shares",
        "지분율": "ownership_ratio_pct",
        "최종변동일": "last_change_date",
        "주주구분": "shareholder_category",
        "대표주주수": "major_shareholder_count",
        "투자의견": "investment_opinion",
        "목표주가": "target_price",
        "추정기관수": "estimate_institution_count",
        "구분": "category",
        "코스피 전기·전자": "kospi_electronics",
        "헤더": "header",
        "헤더.1": "header_1",
        "IFRS(연결)": "ifrs_consolidated",
        "IFRS(별도)": "ifrs_individual",
    }

    def translate_dataframe(
        self,
        frame: pd.DataFrame,
        *,
        stock_code: str | None = None,
    ) -> pd.DataFrame:
        """
        DataFrame의 한글 컬럼명을 영문으로 번역

        단일 인덱스와 멀티 인덱스 모두 지원

        Args:
            frame: 번역할 DataFrame
            stock_code: 종목 코드 (회사명을 "company"로 치환하기 위해 사용)

        Returns:
            pd.DataFrame: 컬럼명이 번역된 DataFrame
        """
        if frame.empty:
            return frame

        # 종목 코드로부터 회사명 조회
        company_name = None
        if stock_code:
            try:
                from utils.companydict import companydict
                company_name = companydict.get_company_by_code(stock_code)
                if company_name:
                    company_name = self._normalize(company_name)
            except ImportError:
                pass

        translated = frame.copy()

        # 멀티인덱스 처리
        if isinstance(translated.columns, pd.MultiIndex):
            new_columns = []
            for column in translated.columns:
                # 각 레벨별로 번역
                new_columns.append(
                    tuple(self._translate_token(level, company_name) for level in column)
                )
            translated.columns = pd.MultiIndex.from_tuples(
                new_columns, names=translated.columns.names
            )
        # 단일 인덱스 처리
        else:
            translated.rename(
                columns=lambda label: self._translate_token(label, company_name),
                inplace=True,
            )

        return translated

    def _translate_token(self, label: str, company_name: str | None) -> str:
        """
        개별 컬럼명 토큰 번역

        Args:
            label: 원본 컬럼명
            company_name: 회사명 (해당 컬럼을 "company"로 치환)

        Returns:
            str: 번역된 컬럼명
        """
        if not isinstance(label, str):
            return label

        normalized = self._normalize(label)

        # 회사명이면 "company"로 통일
        if company_name and normalized == company_name:
            return "company"

        # 매핑 딕셔너리에서 찾기 (없으면 원본 그대로)
        return self._COLUMN_MAP.get(normalized, normalized)

    @staticmethod
    def _normalize(value: str) -> str:
        """
        문자열 정규화 (공백 문자 제거 및 trim)

        Args:
            value: 원본 문자열

        Returns:
            str: 정규화된 문자열
        """
        return value.replace("\xa0", " ").strip()


# ==================== 하위 호환성 함수 ====================

def get_fnguide_fundamentals(company: str) -> dict[str, str | None]:
    """
    하위 호환성을 위한 래퍼 함수

    기존 코드에서 이 함수를 사용하는 경우를 위해 유지

    Args:
        company: 종목 코드 (6자리, 예: "005930")

    Returns:
        dict: {
            "ticker": str,
            "country": str,
            "balance_sheet": str | None,      # JSON 문자열
            "income_statement": str | None,   # JSON 문자열
            "cash_flow": str | None           # JSON 문자열
        }

    Example:
        >>> data = get_fnguide_fundamentals("005930")
        >>> print(data.keys())
        dict_keys(['ticker', 'country', 'balance_sheet', 'income_statement', 'cash_flow'])
    """
    crawler = FnGuideCrawler(stock=company)
    return crawler.get_all_fundamentals()


if __name__ == "__main__":
    # 삼성전자(005930) 데이터 수집 테스트
    get_fnguide_fundamentals("005930")
