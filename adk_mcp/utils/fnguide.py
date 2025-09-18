import requests
import pandas as pd
import json
from .gcpmanager import GCSManager
from datetime import date

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

    def fundamentals(self, stock: str | None = None):
        if stock:
            self.stock = stock
            self.url = f"https://comp.fnguide.com/SVO2/ASP/SVD_main.asp?pGB=1&gicode=A{stock}"

        today = date.today()
        current_quarter = f"{today.year}-Q{(today.month - 1) // 3 + 1}"
        folder_name = f"/Fundamentals/FnGuide/{self.stock}/{current_quarter}/raw/"
        file_prefix = f"{self.stock}_{today.year}_{today.month:02d}"

        existing_files = set(self.gcs.list_files(folder_name=folder_name))
        cached_data = self._load_from_gcs(folder_name, file_prefix, existing_files)
        if cached_data is not None:
            return cached_data

        response = requests.get(self.url)
        response.raise_for_status()
        tables = pd.read_html(response.text)

        datasets = {}
        for name, index in self.TABLE_MAP:
            if index < len(tables):
                datasets[name] = tables[index]
            else:
                print(f"경고: '{name}'에 해당하는 테이블(index {index})을 찾지 못해 빈 데이터로 저장합니다.")
                datasets[name] = pd.DataFrame()

        serialized_payloads = {
            name: frame.to_json(orient="records", force_ascii=False)
            for name, frame in datasets.items()
        }

        self.upload_to_gcs(
            serialized_payloads,
            folder_name=folder_name,
            file_prefix=file_prefix,
            existing_files=existing_files,
        )

        return {name: json.loads(payload) for name, payload in serialized_payloads.items()}

    def _load_from_gcs(
        self,
        folder_name: str,
        file_prefix: str,
        existing_files: set[str],
    ) -> dict[str, list[dict]] | None:
        expected_paths = {
            name: f"{folder_name}{file_prefix}_{name}.json"
            for name, _ in self.TABLE_MAP
        }

        if not set(expected_paths.values()).issubset(existing_files):
            return None

        cached_data: dict[str, list[dict]] = {}
        for name, blob_name in expected_paths.items():
            content = self.gcs.read_file(blob_name)
            if not content:
                return None
            cached_data[name] = json.loads(content)
        return cached_data

    def upload_to_gcs(
        self,
        serialized_payloads: dict[str, str],
        *,
        folder_name: str,
        file_prefix: str,
        existing_files: set[str] | None = None,
    ) -> None:
        if existing_files is None:
            existing_files = set(self.gcs.list_files(folder_name=folder_name))

        for name, payload in serialized_payloads.items():
            blob_name = f"{folder_name}{file_prefix}_{name}.json"
            if blob_name in existing_files:
                continue
            self.gcs.upload_file(
                source_file=payload,
                destination_blob_name=blob_name,
                encoding="utf-8",
                content_type="application/json; charset=utf-8",
            )
            existing_files.add(blob_name)
