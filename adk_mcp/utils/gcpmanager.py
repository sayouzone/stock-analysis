from google.cloud import storage, bigquery, exceptions
import os
from datetime import datetime
import pandas as pd

class GCSManager:
    def __init__(self, bucket_name="sayouzone-ai-stocks"):
        self.bucket_name = bucket_name
        self.storage_client = storage.Client(project='sayonzone-ai')

    def list_files(self, folder_name=None, sort_by_time=True):
        print(f"'{folder_name if folder_name else '전체'}' 구역의 파일 목록 조회를 시작합니다...")
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
        self.bq_client = bigquery.Client(project=project_id)
        if not BQManager._dataset_checked:
            self._ensure_dataset_exists()
            BQManager._dataset_checked = True

    def _ensure_dataset_exists(self):
        """Ensures that the default dataset exists, creating it if necessary."""
        try:
            self.bq_client.get_dataset(self.dataset_id)
            print(f"Dataset '{self.dataset_id}' already exists.")
        except exceptions.NotFound:
            print(f"Dataset '{self.dataset_id}' not found. Creating it...")
            try:
                self.bq_client.create_dataset(self.dataset_id, exists_ok=True)
                print(f"Dataset '{self.dataset_id}' created successfully.")
            except Exception as e:
                print(f"Failed to create dataset '{self.dataset_id}': {e}")
                raise

    def query_table(self, table_id: str, start_date: str | None = None, end_date: str | None = None, order_by_date: bool = True) -> pd.DataFrame | None:
        """
        Queries a table with optional date filtering and ordering.
        Returns a DataFrame or None if the table doesn't exist or an error occurs.
        """
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
