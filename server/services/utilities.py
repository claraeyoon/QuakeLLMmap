import os, json, base64
from google.cloud import storage, bigquery
from fastapi import UploadFile
import datetime as dt
from dotenv import load_dotenv
from google.oauth2 import service_account
from typing import Union

load_dotenv() 

storage_client=None
bq_client=None

def load_credentials():
    creds_b64 = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_b64:
        try:
            creds_info = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
            return service_account.Credentials.from_service_account_info(
                creds_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        except Exception:
            try:
                creds_info = json.loads(creds_b64)
                return service_account.Credentials.from_service_account_info(
                    creds_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except Exception:
                pass

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.exists(creds_path):
        return service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

    import google.auth
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return credentials

def lazy_clients() -> tuple[storage.Client, bigquery.Client]:
    global storage_client, bq_client

    if storage_client is None or bq_client is None:
        project_id = os.environ.get("GCS_PROJECT_ID") or os.environ.get("projectID")
        credentials = load_credentials()

        if storage_client is None:
            storage_client = storage.Client(project=project_id, credentials=credentials)
        if bq_client is None:
            bq_client = bigquery.Client(project=project_id, credentials=credentials)
    return storage_client, bq_client

def upload_to_gcs(file: Union[str, UploadFile], bucketname: str = None, blob_name: str = "placeholder") -> str:
    """Upload bytes to GCS and return signed URL."""
    if not bucketname:
        bucketname = os.environ.get("GCS_BUCKET", "earthquake_bukt")
    
    storage_client, _ = lazy_clients()
    
    bucket = storage_client.bucket(bucketname)
    blob = bucket.blob(blob_name)

    # stream upload
    if isinstance(file, str):
        content_type = "image/png"
        if file.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif file.endswith(".pdf"):
            content_type = "application/pdf"
        elif file.endswith(".mp4"):
            content_type = "video/mp4"

        with open(file, "rb") as f:
            blob.upload_from_file(f, content_type=content_type)
    else:
        blob.upload_from_file(file.file, content_type=file.content_type)

    ttl = int(os.environ.get("SIGNED_URL_TTL", "36000"))
    url = blob.generate_signed_url(
        expiration=dt.timedelta(seconds=ttl),
        version="v4",
        method="GET",
    )
    return url

def insert_row(metadata: dict[str, str | float | None]):
    """Insert row into BigQuery table (non-blocking on schema mismatches)"""
    _, bq = lazy_clients()
    project_id = os.environ.get("GCS_PROJECT_ID") or os.environ.get("projectID")
    dataset = os.environ.get("BQ_DATASET", "earthquake_dataset")
    table = os.environ.get("BQ_TABLE", "map_store")

    table_ref = f"{project_id}.{dataset}.{table}"
    try:
        errors = bq.insert_rows_json(table_ref, [metadata])
        if errors:
            print(f"Notice: BigQuery insert_row skipped or warned: {errors}")
    except Exception as e:
        print(f"Notice: BigQuery insert_row could not insert initial record: {e}")

_analysis_cache: dict[str, dict] = {}

def insert_analysis(formData : dict):
    """Insert row into BigQuery table and update in-memory cache"""
    _, bq = lazy_clients()
    project_id = os.environ.get("GCS_PROJECT_ID") or os.environ.get("projectID")
    dataset = os.environ.get("BQ_DATASET", "earthquake_dataset")
    table = os.environ.get("BQ_TABLE", "map_store")

    table_ref = f"{project_id}.{dataset}.{table}"
    errors = bq.insert_rows_json(table_ref, [formData])
    if errors:
        raise RuntimeError(f"BigQuery insertion failed: {errors}")

    # Cache completed analysis in memory so subsequent GET requests don't hit BigQuery
    blob_name = formData.get("blob_name")
    if blob_name:
        _analysis_cache[blob_name] = formData

    return

def fetch_from_db(blob_name):
    # Check in-memory cache first to avoid BigQuery query costs
    if blob_name in _analysis_cache:
        return _analysis_cache[blob_name]

    project_id = os.environ.get("GCS_PROJECT_ID") or os.environ.get("projectID")
    dataset = os.environ.get("BQ_DATASET", "earthquake_dataset")
    table = os.environ.get("BQ_TABLE", "map_store")

    query = f"""
        SELECT blob_name, mmi_estimation, confidence, map_url, reasoning
        FROM `{project_id}.{dataset}.{table}`
        WHERE blob_name=@blob_name AND mmi_estimation IS NOT NULL
        LIMIT 1
    """
    _, bq = lazy_clients()  
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("blob_name", "STRING", blob_name)
        ]
    )

    result = bq.query(query, job_config=job_config).result()
    row = next(result, None)

    if row:
        data = {
            "blob_name": row.blob_name,
            "mmi_estimation": row.mmi_estimation,
            "confidence": row.confidence,
            "map_url": row.map_url,
            "reasoning": row.reasoning
        }
        _analysis_cache[blob_name] = data
        return data
    return None




   
