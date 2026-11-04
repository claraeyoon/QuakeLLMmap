import os
import sys
import argparse
from dotenv import load_dotenv

# Ensure server folder is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from services.crag import MultimodalEarthquakeCRAG
from services.utilities import upload_to_gcs, insert_analysis, fetch_from_db, append_to_csv

def test_file(file_path: str, csv_output: str = None):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        mime_type = "application/pdf"
    elif lower_name.endswith(".png"):
        mime_type = "image/png"
    elif lower_name.endswith(".mp4"):
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
    loc = final.get("location", {})
    coords = loc.get("coordinates") if isinstance(loc, dict) else [0.0, 0.0]
    lat = float(coords[0]) if len(coords) >= 1 else 0.0
    lon = float(coords[1]) if len(coords) >= 2 else 0.0
    mmi = float(final.get("mmi_estimation", 5.0))
    conf = float(final.get("confidence", 0.8))

    print(f"\n🎯 MMI Estimation: {mmi}")
    print(f"🎯 Confidence: {conf}")
    print(f"📍 Location: {loc.get('address', 'Unknown')} (Coordinates: [latitude: {lat}, longitude: {lon}])")

    if csv_output:
        append_to_csv(csv_output, filename, lon, lat, mmi, conf)
        print(f"💾 Record appended to CSV: {csv_output}")

    print(f"\n🚀 [Step 3] Storing analysis in BigQuery table '{os.environ.get('BQ_TABLE', 'map_store')}'...")
    insert_analysis({
        "blob_name": filename,
        "mmi_estimation": mmi,
        "confidence": conf,
        "map_url": "",
        "reasoning": final.get("reasoning", "")
    })
    print("✅ BigQuery insertion succeeded!")

    print(f"\n🚀 [Step 4] Querying BigQuery to verify fetch_from_db('{filename}')...")
    fetched = fetch_from_db(filename)
    print(f"✅ Fetched row: {fetched}")
    print("\n🎉 End-to-end pipeline test completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run earthquake CRAG analysis on a media file.")
    parser.add_argument("file_path", nargs="?", default="test_page1.pdf", help="Input media file path")
    parser.add_argument("csv_output", nargs="?", default=None, help="Optional CSV file to output extracted records")
    parser.add_argument("--csv", dest="csv_flag", default=None, help="Optional CSV file to output extracted records")

    args = parser.parse_args()
    csv_file = args.csv_flag or args.csv_output or os.environ.get("CSV_OUT")
    test_file(args.file_path, csv_output=csv_file)
