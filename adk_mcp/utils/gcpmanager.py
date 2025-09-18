import logging
import os
from datetime import datetime
import pandas as pd
import requests
from google.cloud import storage, bigquery, exceptions, secretmanager


def get_gcp_project_id():
    """GCP 메타데이터 서버 또는 환경 변수에서 프로젝트 ID를 가져옵니다."""
    try:
        response = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
            timeout=2
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException:
        project_id = os.getenv("GCP_PROJECT_ID")
        if project_id:
            logging.info("GCP_PROJECT_ID 환경 변수에서 프로젝트 ID를 가져왔습니다.")
            return project_id
        else:
            logging.warning("GCP 메타데이터 서버에 연결할 수 없으며 GCP_PROJECT_ID 환경 변수가 설정되지 않았습니다.")
            return None

class SecretManager:
    """Google Secret Manager와 상호작용하기 위한 클라이언트"""
    def __init__(self, project_id: str | None = None):
        self.project_id = project_id or get_gcp_project_id()
        try:
            self.client = secretmanager.SecretManagerServiceClient()
            self._secret_manager_available = True
            logging.info("Secret Manager 클라이언트가 성공적으로 초기화되었습니다.")
        except Exception as e:
            logging.warning("Secret Manager 클라이언트 초기화 실패: %s", e)
            self.client = None
            self._secret_manager_available = False

    def access_secret_version(self, secret_id: str, version_id: str = "latest") -> str | None:
        """지정된 시크릿 버전의 페이로드를 가져옵니다."""
        if not self._secret_manager_available or not self.project_id:
            logging.error("Secret Manager를 사용할 수 없거나 프로젝트 ID가 없습니다.")
            return None
            
        name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version_id}"
        try:
            response = self.client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except exceptions.NotFound:
            logging.error(f"시크릿 '{secret_id}'의 버전 '{version_id}'를 찾을 수 없습니다.")
            return None
        except Exception as e:
            logging.error(f"시크릿 '{secret_id}'에 접근하는 중 오류 발생: {e}")
            return None

    def load_secrets_into_env(self, secrets_to_load: list[str]):
        """Secret Manager에서 시크릿 목록을 가져와 환경 변수로 로드합니다."""
        if not self._secret_manager_available:
            logging.error("Secret Manager를 사용할 수 없어 시크릿을 로드할 수 없습니다.")
            return

        logging.info(f"시크릿 로드 중: {secrets_to_load}")
        for secret_id in secrets_to_load:
            secret_value = self.access_secret_version(secret_id)
            if secret_value is not None:
                os.environ[secret_id] = secret_value
                logging.info(f"시크릿 '{secret_id}'를 환경 변수로 로드했습니다.")
            else:
                logging.warning(f"시크릿 '{secret_id}'를 로드하지 못했습니다.")

class GCSManager:
    def __init__(self, bucket_name="sayouzone-ai-stocks"):
        self.bucket_name = bucket_name
        try:
            self.storage_client = storage.Client(project='sayonzone-ai')
            self._storage_available = True
        except Exception as e:
            logging.warning("GCS client 초기화 실패: %s", e)
            self.storage_client = None
            self._storage_available = False

    def list_files(self, folder_name=None, sort_by_time=True):
        print(f"'{folder_name if folder_name else '전체'}' 구역의 파일 목록 조회를 시작합니다...")
        if not getattr(self, "_storage_available", False):
            print("GCS 클라이언트가 비활성화되어 목록을 가져올 수 없습니다.")
            return []
        try:
            blobs = self.storage_client.list_blobs(self.bucket_name, prefix=folder_name)
            
            blob_list = list(blobs)

            if sort_by_time and blob_list:
                blob_list.sort(key=lambda blob: blob.time_created, reverse=True)

            file_list = [blob.name for blob in blob_list]
            print(f"총 {len(file_list)}개의 파일을 찾았습니다.")
            return file_list
        except Exception as e:
            print(f"파일 목록 조회 중 심각한 에러 발생: {e}")
            return []

    def upload_file(self, source_file, destination_blob_name, *, encoding: str = "utf-8", content_type: str | None = None):
        print(f"파일 업로드 시작: '{destination_blob_name}'")
        if not getattr(self, "_storage_available", False):
            print("GCS 클라이언트가 비활성화되어 업로드를 수행할 수 없습니다.")
            return False
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(destination_blob_name)

            if isinstance(source_file, str):
                payload = source_file.encode(encoding)
            elif isinstance(source_file, (bytes, bytearray)):
                payload = bytes(source_file)
            elif hasattr(source_file, "read"):
                data = source_file.read()
                if isinstance(data, str):
                    payload = data.encode(encoding)
                elif isinstance(data, (bytes, bytearray)):
                    payload = bytes(data)
                else:
                    raise TypeError("Unsupported stream data type for upload")
            else:
                raise TypeError("source_file must be a str, bytes-like, or readable object")

            upload_kwargs = {"content_type": content_type} if content_type else {}
            blob.upload_from_string(payload, **upload_kwargs)

            print("파일 업로드 성공!")
            return True
        except FileNotFoundError:
            print("에러: 원본 파일을(를) 찾을 수 없습니다.")
            return False
        except Exception as e:
            print(f"파일 업로드 중 심각한 에러 발생: {e}")
            return False
    
    def read_file(self, blob_name):
        print(f"파일 읽기 시작: '{blob_name}'")
        if not getattr(self, "_storage_available", False):
            print("GCS 클라이언트가 비활성화되어 파일을 읽을 수 없습니다.")
            return None
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            content = blob.download_as_text()

            print("파일 읽기 성공!")
            return content
        except Exception as e:
            print(f"파일 읽기 중 심각한 에러 발생: {e}")
            return None

class BQManager:
    _dataset_checked = False

    def __init__(self, project_id="sayouzone-ai"):
        self.project_id = project_id
        self.dataset_id = "stocks"
        try:
            self.bq_client = bigquery.Client(project=project_id)
        except Exception as e:
            logging.warning("BigQuery 클라이언트 초기화 실패: %s", e)
            self.bq_client = None
        if self.bq_client and not BQManager._dataset_checked:
            if self._ensure_dataset_exists():
                BQManager._dataset_checked = True

    def _ensure_dataset_exists(self):
        """Ensures that the default dataset exists, creating it if necessary."""
        if not self.bq_client:
            print("BigQuery 클라이언트가 비활성화되어 데이터세트를 확인하지 않습니다.")
            return False
        try:
            self.bq_client.get_dataset(self.dataset_id)
            print(f"Dataset '{self.dataset_id}' already exists.")
            return True
        except exceptions.NotFound:
            print(f"Dataset '{self.dataset_id}' not found. Creating it...")
            try:
                self.bq_client.create_dataset(self.dataset_id, exists_ok=True)
                print(f"Dataset '{self.dataset_id}' created successfully.")
                return True
            except Exception as e:
                print(f"Failed to create dataset '{self.dataset_id}': {e}")
                return False
        except Exception as e:
            print(f"Dataset 검사 중 오류 발생: {e}")
            return False

    def query_table(self, table_id: str, start_date: str | None = None, end_date: str | None = None, order_by_date: bool = True) -> pd.DataFrame | None:
        """
        Queries a table with optional date filtering and ordering.
        Returns a DataFrame or None if the table doesn't exist or an error occurs.
        """
        if not self.bq_client:
            print("BigQuery 클라이언트가 비활성화되어 쿼리를 수행할 수 없습니다.")
            return None
        if '.' not in table_id:
            full_table_id = f"{self.project_id}.{self.dataset_id}.{table_id}"
        else:
            full_table_id = table_id

        print(f"Querying BigQuery table: '{full_table_id}'...")

        try:
            self.bq_client.get_table(full_table_id)
        except exceptions.NotFound:
            print(f"Table '{full_table_id}' does not exist. Skipping query.")
            return None
        except Exception as e:
            print(f"Error checking table existence: {e}")
            return None

        query = f"SELECT * FROM `{full_table_id}`"
        
        where_clauses = []
        if start_date:
            where_clauses.append(f"date >= '{start_date}'")
        if end_date:
            where_clauses.append(f"date <= '{end_date}'")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        if order_by_date:
            query += " ORDER BY date DESC"

        print(f"Executing query: {query}")

        try:
            df = self.bq_client.query(query).to_dataframe()
            if df.empty:
                print("Query returned no data.")
                return None
            print(f"Successfully queried {len(df)} rows.")
            return df
        except Exception as e:
            print(f"Error querying BigQuery: {e}")
            return None
        
    def _full_table_id(self, table_id: str) -> str:
        return table_id if '.' in table_id else f"{self.project_id}.{self.dataset_id}.{table_id}"
    
    def _create_table_if_not_exists(self, full_table_id: str, schema: list[bigquery.SchemaField] | None = None):
        if not self.bq_client:
            print("BigQuery 클라이언트가 비활성화되어 테이블을 생성하지 않습니다.")
            return False
        try:
            self.bq_client.get_table(full_table_id)
            print(f"Table '{full_table_id}' already exists.")
            return True
        except exceptions.NotFound:
            print(f"Table '{full_table_id}' not found. Creating it...")
            try:
                table = bigquery.Table(full_table_id, schema=schema)
                self.bq_client.create_table(table)
                print(f"Table '{full_table_id}' created successfully.")
                return True
            except Exception as e:
                print(f"Failed to create table '{full_table_id}': {e}")
                return False
    
    def load_dataframe(self, 
                       df: pd.DataFrame, 
                       table_id: str,
                       if_exists: str = "append",
                       deduplicate_on: list | None = None
                       ):
        if not self.bq_client:
            print("BigQuery 클라이언트가 비활성화되어 DataFrame 적재를 수행하지 않습니다.")
            return False

        full_table_id = self._full_table_id(table_id)

        print(f"Loading dataframe into BigQuery table: '{full_table_id}'...")

        try:
            self.bq_client.get_table(full_table_id)
            table_exists = True
        except exceptions.NotFound:
            table_exists = False

        if table_exists and deduplicate_on and if_exists == "append":
            if df.empty:
                print("Dataframe is empty. Skipping load.")
                return True
            
            key_cols = ", ".join(deduplicate_on)
            duplication_query = f"SELECT DISTINCT {key_cols} FROM `{full_table_id}`"

            print("Querying existing data for deduplication...")
            try:
                query_job = self.bq_client.query(duplication_query)
                existing_data_keys = {tuple(row.values()) for row in query_job.result()}
                print(f"Found {len(existing_data_keys)} unique keys in existing data.")

                df_keys = df[deduplicate_on].apply(tuple, axis=1)
                fresh_data_mask = ~df_keys.isin(existing_data_keys)
                df_to_load = df[fresh_data_mask]

                if df_to_load.empty:
                    print("No new data to load after deduplication. Skipping load.")
                    return True
                
                print(f"{len(df_to_load)} new rows remaining after deduplication. Proceeding to load...")
                df = df_to_load
            except Exception as e:
                print(f"Error during deduplication query: {e}. Skipping deduplication.")

        try:
            job_config = bigquery.LoadJobConfig(
                autodetect=True,
                write_disposition=(
                    bigquery.WriteDisposition.WRITE_TRUNCATE if if_exists == "replace" 
                    else bigquery.WriteDisposition.WRITE_APPEND
                ),
                create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
                schema_update_options=[
                bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION,]
            )

            load_job = self.bq_client.load_table_from_dataframe(
                dataframe=df, destination=full_table_id, job_config=job_config
            )

            load_job.result()

            print(f"Dataframe loaded successfully into '{full_table_id}'.")
            return True
        except Exception as e:
            print(f"Failed to load dataframe: {e}")
            return False


if __name__ == "__main__":
    # GCSManager 사용 예시
    gcs_manager = GCSManager(bucket_name="sayouzone-ai-stocks")
    gcs_manager.upload_file("test.txt", "test/test.txt")
    files = gcs_manager.list_files("test/")
    print(files)
    content = gcs_manager.read_file("test/test.txt")
    print(content)

    # BQManager 사용 예시
    bq_manager = BQManager()
    
    # 샘플 데이터프레임 생성
    data = {'col1': [1, 2], 'col2': ['A', 'B']}
    df = pd.DataFrame(data)
    
    # 데이터프레임을 BigQuery에 로드
    bq_manager.load_dataframe(df, 'my_test_table', if_exists='replace')
    
    # BigQuery에서 테이블 쿼리
    queried_df = bq_manager.query_table('my_test_table')
    if queried_df is not None:
        print(queried_df)