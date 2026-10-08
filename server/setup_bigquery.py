import os
import sys
from dotenv import load_dotenv

# Ensure server folder is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from services.utilities import lazy_clients

def main():
    load_dotenv()
    project_id = os.environ.get("GCS_PROJECT_ID") or os.environ.get("projectID")
    if not project_id:
        print("❌ Error: GCS_PROJECT_ID is not set in .env")
        sys.exit(1)

    dataset_id = os.environ.get("BQ_DATASET", "earthquake_dataset")
    table_id = os.environ.get("BQ_TABLE", "map_store")

    print(f"🚀 Connecting to BigQuery in project '{project_id}'...")
    try:
        storage_client, bq_client = lazy_clients()
    except Exception as e:
        print(f"❌ Failed to initialize GCP clients: {e}")
        print("Please check your GOOGLE_APPLICATION_CREDENTIALS in .env")
        sys.exit(1)

    # 1. Ensure Dataset Exists
    dataset_ref = f"{project_id}.{dataset_id}"
    try:
        bq_client.get_dataset(dataset_ref)
        print(f"✅ BigQuery dataset '{dataset_ref}' already exists.")
    except NotFound:
        print(f"📦 Creating BigQuery dataset '{dataset_ref}'...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = os.environ.get("GCS_REGION", "us-central1")
        bq_client.create_dataset(dataset)
        print(f"✅ Created BigQuery dataset '{dataset_ref}'.")

    # 2. Ensure Table Exists with exact schema
    table_ref = f"{dataset_ref}.{table_id}"
    schema = [
        bigquery.SchemaField("blob_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("mmi_estimation", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("confidence", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("map_url", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("reasoning", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("signed_url", "STRING", mode="NULLABLE"),
    ]

    try:
        bq_client.get_table(table_ref)
        print(f"✅ BigQuery table '{table_ref}' already exists.")
    except NotFound:
        print(f"📦 Creating BigQuery table '{table_ref}' with schema...")
        table = bigquery.Table(table_ref, schema=schema)
        bq_client.create_table(table)
        print(f"✅ Created BigQuery table '{table_ref}'.")

    # 3. Check GCS Bucket
    bucket_name = os.environ.get("GCS_BUCKET", "quakemap-media-data")
    print(f"\n🔍 Checking Cloud Storage bucket '{bucket_name}'...")
    
    bucket_ready = False
    # Check A: Metadata inspection
    try:
        bucket = storage_client.get_bucket(bucket_name)
        print(f"✅ Cloud Storage bucket '{bucket_name}' exists and metadata is accessible.")
        bucket_ready = True
    except Exception:
        # Check B: Test actual object upload/delete permission (Storage Object Admin)
        try:
            test_blob = storage_client.bucket(bucket_name).blob(".test_access")
            test_blob.upload_from_string(b"ok", content_type="text/plain")
            test_blob.delete()
            print(f"✅ Cloud Storage bucket '{bucket_name}' exists and object upload/delete is verified!")
            bucket_ready = True
        except Exception as obj_err:
            # If 404 / bucket doesn't exist, try creating it
            err_str = str(obj_err).lower()
            if "not found" in err_str or "404" in err_str:
                print(f"📦 Bucket '{bucket_name}' does not exist yet. Attempting to create it...")
                try:
                    storage_client.create_bucket(bucket_name, location=os.environ.get("GCS_REGION", "us-central1"))
                    print(f"✅ Successfully created Cloud Storage bucket '{bucket_name}' in {os.environ.get('GCS_REGION', 'us-central1')}!")
                    bucket_ready = True
                except Exception as create_err:
                    print(f"⚠️ Could not auto-create bucket: {create_err}")
            else:
                print(f"⚠️ Bucket check failed: {obj_err}")

    if not bucket_ready:
        print("\n------------------------------------------------------------")
        print(f"👉 ACTION REQUIRED IN GOOGLE CLOUD CONSOLE:")
        print(f"1. Go to: https://console.cloud.google.com/storage/browser?project={project_id}")
        print(f"2. Click '+ CREATE' to create bucket: '{bucket_name}' (Location: us-central1)")
        print(f"   (Note: If that name is already taken globally by another GCP user, choose a unique name like")
        print(f"   '{bucket_name}-<suffix>' and update GCS_BUCKET in your .env)")
        print(f"3. Grant your service account 'Storage Object Admin' (or 'Storage Admin') on the bucket.")
        print("------------------------------------------------------------")

    print("\n🎉 BigQuery setup complete! Ready to receive earthquake damage analysis.")

if __name__ == "__main__":
    main()
