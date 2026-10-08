import os
import subprocess
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, status

from services.generateMap import generate_gmt_script
from services.utilities import upload_to_gcs, insert_row, insert_analysis, fetch_from_db
from services.crag import MultimodalEarthquakeCRAG

router_upload = APIRouter()
quake_CRAG = MultimodalEarthquakeCRAG()

def analyze_blob(blob_name: str, signed_url: str, mime_type: str):
    import traceback
    print(f"\n🚀 [analyze_blob] Starting analysis for '{blob_name}' (mime: {mime_type})...")
    try:
        result = quake_CRAG.analyze_media_and_traverse_states(
            blob_name=blob_name,
            signed_url=signed_url,
            mime_type=mime_type
        )
        print(f"✅ [analyze_blob] CRAG graph completed successfully for '{blob_name}'")

        # save sample to see
        try:
            with open("sample_test.txt", 'w') as f:
                f.write(result.get("generation", ""))
        except Exception:
            pass

        final_analysis = result.get("final_analysis", {})
        location = final_analysis.get("location") or {}
        coords = location.get("coordinates") if isinstance(location, dict) else None

        # Extract coordinates safely if present
        lat, lon = None, None
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                lat = float(coords[0])
                lon = float(coords[1])
            except (ValueError, TypeError):
                lat, lon = None, None

        mmi = final_analysis.get("mmi_estimation", 5.0)

        # add point to map if valid non-zero coordinates
        map_url = None
        if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
            try:
                os.makedirs("./assets", exist_ok=True)
                with open("./assets/records.txt", "a") as f:
                    f.write(f"{lon} {lat} {mmi}\n")

                # run gmt again to generate map
                subprocess.run(["bash", "./assets/plot.sh"], check=False)
            except Exception as e:
                print("Notice: map plotting error:", e)

        try:
            bucket = os.environ.get("GCS_BUCKET", "quakemap-media-data")
            if os.path.exists("./assets/mmi_mandalay_map.png"):
                map_url = upload_to_gcs("./assets/mmi_mandalay_map.png", bucketname=bucket, blob_name="mmi_mandalay_map.png")
        except Exception as e:
            print("Notice: map upload error:", e)

        insert_analysis({
            "blob_name": blob_name,
            "mmi_estimation": final_analysis.get("mmi_estimation", 5.0),
            "confidence": final_analysis.get("confidence", 0.8),
            "map_url": map_url,
            "reasoning": final_analysis.get("reasoning", "")
        })

        print(f"✅ [analyze_blob] Successfully inserted analysis to BigQuery for '{blob_name}'")

    except Exception as e:
        print(f"❌ [analyze_blob] Analysis FAILED for '{blob_name}': {e}")
        traceback.print_exc()
        try:
            insert_analysis({
                "blob_name": blob_name,
                "mmi_estimation": 0.0,
                "confidence": 0.0,
                "map_url": "",
                "reasoning": f"Analysis encountered an error: {str(e)}"
            })
            print(f"Notice: Inserted error status row to BigQuery for '{blob_name}'")
        except Exception as bq_err:
            print(f"Could not record error to BigQuery: {bq_err}")

@router_upload.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file : UploadFile = File(description="jpeg, png, pdf, mp4")):
    """
        upload to GCS 
    """
    if file.content_type not in {"image/jpeg", "image/png", "application/pdf", "video/mp4"}:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    blob_name = f"{file.filename}"
    bucket = os.environ.get("GCS_BUCKET", "earthquake_bukt")
    
    signed_url = upload_to_gcs(file, bucketname=bucket, blob_name=blob_name)

    insert_row({
        "blob_name": blob_name,
        "signed_url": signed_url,
    })


    background_tasks.add_task(analyze_blob, blob_name, signed_url, file.content_type)

    return {
        "blob_name": blob_name,
        "signed_url": signed_url,
        "message": "Upload successful"
    }

@router_upload.get("/result/{blob_name}")
def get_analysis(blob_name : str):
    
    result = fetch_from_db(blob_name)  

    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not ready yet")

    return result
