import requests
import pandas as pd
import json
from io import StringIO
from datetime import date

from utils.companydict import companydict
from .gcpmanager import GCSManager

class Fundamentals:
    TABLE_MAP = [
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

    def __init__(self, stock: str = "005930"):
        self.stock = stock
        self.url = f"https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}"
        self.gcs = GCSManager(bucket_name="sayouzone-ai-stocks")
        self._translator = _FnGuideTranslator()

    def fundamentals(
        self,
        stock: str | None = None,
        *,
        use_cache: bool = False,
        overwrite: bool = True,
    ):
        if stock:
            self.stock = stock
            self.url = f"https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}"

        today = date.today()
        quarter = (today.month - 1) // 3 + 1
        year_partition = f"year={today.year}"
        quarter_partition = f"quarter={quarter}"
        folder_name = (
            f"Fundamentals/FnGuide/{year_partition}/"
            f"{quarter_partition}/"
        )
        file_base = self.stock

        misspelled_folder = self._partition_alias(folder_name)
        legacy_folder = self._legacy_folder_from_current(
            folder_name, stock=self.stock, year=today.year, quarter=quarter
        )
        existing_files: dict[str, str] | None = None
        cached_data: dict[str, list[dict]] | None = None

        if use_cache:
            existing_files = self._collect_existing_files(
                folder_name,
                misspelled_folder,
                legacy_folder,
            )
            cached_data = self._load_from_gcs(
                folder_name,
                file_base,
                existing_files,
                legacy_folder,
            )
            if cached_data is not None and not overwrite:
                return cached_data

        if existing_files is None and not overwrite:
            existing_files = self._collect_existing_files(
                folder_name,
                misspelled_folder,
                legacy_folder,
            )

        response = requests.get(self.url)
        response.raise_for_status()
        tables = pd.read_html(response.text)

        datasets = {}
        for name, index in self.TABLE_MAP:
            if index < len(tables):
                frame = tables[index]
                frame = self._translator.translate_dataframe(
                    frame,
                    stock_code=self.stock,
                )
                datasets[name] = frame
            else:
                print(f"경고: '{name}'에 해당하는 테이블(index {index})을 찾지 못해 빈 데이터로 저장합니다.")
                datasets[name] = pd.DataFrame()

        csv_payloads: dict[str, str] = {}
        record_payloads: dict[str, list[dict]] = {}
        for name, frame in datasets.items():
            csv_payloads[name] = frame.to_csv(index=False)
            record_payloads[name] = frame.to_dict(orient="records")

        self.upload_to_gcs(
            csv_payloads,
            folder_name=folder_name,
            file_base=file_base,
            existing_files=existing_files,
            overwrite=overwrite,
            legacy_folder=legacy_folder,
        )

        return record_payloads

    def _load_from_gcs(
        self,
        folder_name: str,
        file_base: str,
        existing_files: dict[str, str] | None,
        legacy_folder: str | None,
    ) -> dict[str, list[dict]] | None:
        if existing_files is None:
            alias_folder = self._partition_alias(folder_name)
            existing_files = self._collect_existing_files(
                folder_name,
                alias_folder,
                legacy_folder,
            )

        cached_data: dict[str, list[dict]] = {}
        for name, _ in self.TABLE_MAP:
            new_blob = f"{folder_name}{file_base}_{name}.csv"
            candidate_names = self._expand_candidates(new_blob)
            candidate_names.extend(
                self._legacy_candidate_blobs(
                    name=name,
                    file_base=file_base,
                    existing_files=existing_files,
                )
            )

            selected_blob = self._resolve_existing_blob(
                candidate_names,
                existing_files,
            )
            if not selected_blob:
                return None

            content = self.gcs.read_file(selected_blob)
            if content is None:
                return None

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

            if not overwrite:
                if self._resolve_existing_blob(candidate_names, existing_files):
                    continue

            target_blob_name = new_blob.lstrip("/")
            uploaded = self.gcs.upload_file(
                source_file=payload,
                destination_blob_name=target_blob_name,
                encoding="utf-8",
                content_type="text/csv; charset=utf-8",
            )
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
        mapping: dict[str, str] = {}
        seen_folders: set[str] = set()
        for candidate_folder in (primary_folder, *additional_folders):
            if not candidate_folder or candidate_folder in seen_folders:
                continue
            seen_folders.add(candidate_folder)
            for blob_name in self.gcs.list_files(folder_name=candidate_folder):
                mapping.setdefault(blob_name, blob_name)
                normalized = blob_name.lstrip("/")
                mapping.setdefault(normalized, blob_name)
        return mapping

    def _expand_candidates(self, blob_name: str) -> list[str]:
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
        suffixes = (f"_{name}.json", f"_{name}.csv")
        matches: list[str] = []
        seen: set[str] = set()
        for key, actual in existing_files.items():
            if actual in seen:
                continue
            normalized_key = key.lstrip("/")
            if file_base not in normalized_key:
                continue
            if not normalized_key.endswith(suffixes):
                continue
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
        parts = folder_name.rstrip("/").split("/")
        if len(parts) < 4:
            return None
        if parts[0] != "Fundamentals" or parts[1] != "FnGuide":
            return None
        year_part, quarter_part = parts[2], parts[3]
        if not year_part.startswith("year=") or not (
            quarter_part.startswith("quarter=")
            or quarter_part.startswith("quater=")
        ):
            return None
        year_value = str(year if year is not None else year_part.split("=", 1)[1])
        quarter_value = str(quarter if quarter is not None else quarter_part.split("=", 1)[1])
        legacy_quarter = f"{year_value}-Q{quarter_value}"
        return f"/Fundamentals/FnGuide/{stock}/{legacy_quarter}/raw/"

    def _partition_alias(self, folder_name: str) -> str | None:
        if "quarter=" not in folder_name:
            return None
        return folder_name.replace("quarter=", "quater=")


class _FnGuideTranslator:
    """Map known Korean column labels to English equivalents."""

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
        if frame.empty:
            return frame

        company_name = None
        if stock_code:
            company_name = companydict.get_company_by_code(stock_code)
            if company_name:
                company_name = self._normalize(company_name)

        translated = frame.copy()

        if isinstance(translated.columns, pd.MultiIndex):
            new_columns = []
            for column in translated.columns:
                new_columns.append(
                    tuple(self._translate_token(level, company_name) for level in column)
                )
            translated.columns = pd.MultiIndex.from_tuples(
                new_columns, names=translated.columns.names
            )
        else:
            translated.rename(
                columns=lambda label: self._translate_token(label, company_name),
                inplace=True,
            )

        return translated

    def _translate_token(self, label: str, company_name: str | None) -> str:
        if not isinstance(label, str):
            return label
        normalized = self._normalize(label)
        if company_name and normalized == company_name:
            return "company"
        return self._COLUMN_MAP.get(normalized, normalized)

    @staticmethod
    def _normalize(value: str) -> str:
        return value.replace("\xa0", " ").strip()
