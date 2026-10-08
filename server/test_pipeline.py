import os
import sys
from dotenv import load_dotenv

# Ensure server folder is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from services.crag import MultimodalEarthquakeCRAG
from services.utilities import upload_to_gcs, insert_analysis, fetch_from_db

def test_file(file_path: str):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    filename = os.path.basename(file_path)
    if filename.endswith(".pdf"):
        mime_type = "application/pdf"
    elif filename.endswith((".png")):
        mime_type = "image/png"
    elif filename.endswith((".mp4")):
        mime_type = "video/mp4"
    else:
        mime_type = "image/jpeg"

    bucket = os.environ.get("GCS_BUCKET", "quakemap-media-data")

    print(f"🚀 [Step 1] Uploading '{filename}' to GCS bucket '{bucket}'...")
    signed_url = upload_to_gcs(file_path, bucketname=bucket, blob_name=filename)
    print(f"   Signed URL generated successfully.")

    print(f"\n🚀 [Step 2] Executing Multimodal CRAG workflow...")
    crag = MultimodalEarthquakeCRAG()
    result = crag.analyze_media_and_traverse_states(
        blob_name=filename,
        signed_url=signed_url,
        mime_type=mime_type
    )

    print("\n==================================================")
    print("📋 CRAG Output Generation:")
    print("==================================================")
    print(result.get("generation", "No generation produced"))
    print("==================================================")

    final = result.get("final_analysis", {})
    print(f"\n🎯 MMI Estimation: {final.get('mmi_estimation')}")
    print(f"🎯 Confidence: {final.get('confidence')}")

    print(f"\n🚀 [Step 3] Storing analysis in BigQuery table '{os.environ.get('BQ_TABLE', 'map_store')}'...")
    insert_analysis({
        "blob_name": filename,
        "mmi_estimation": final.get("mmi_estimation", 5.0),
        "confidence": final.get("confidence", 0.8),
        "map_url": "",
        "reasoning": final.get("reasoning", "")
    })
    print("✅ BigQuery insertion succeeded!")

    print(f"\n🚀 [Step 4] Querying BigQuery to verify fetch_from_db('{filename}')...")
    fetched = fetch_from_db(filename)
    print(f"✅ Fetched row: {fetched}")
    print("\n🎉 End-to-end pipeline test completed successfully!")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "test_page1.pdf"
    test_file(target)
