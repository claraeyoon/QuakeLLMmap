# 🌍 Quakemap - Technical Implementation Guide

> 🚀 Architecture and implementation details of the AI-powered earthquake assessment platform.

## 🏗️ Core System Architecture

### State Management Implementation

Self-Corrective RAG (Retrieval Augmented Generation) workflow uses a TypedDict to manage processing state throughout the analysis pipeline [1](#1-0) :

```python
class State(TypedDict):
    """State of our graph"""
    blob_name: str           # Media file identifier
    signed_url: str          # GCS access URL
    mime_type: str           # File type detection
    initial_analysis: str    # First-pass AI analysis
    context_summary: str     # Earthquake context summary
    mmi_documents: List[Document]  # Retrieved reference docs
    web_search: str          # Web search trigger flag
    final_analysis: Dict[str, Any]  # Structured results
    generation: str          # Final formatted report
```

## 🤖 AI Processing Pipeline Implementation

### Document Retrieval System

The MMI document retrieval uses Pinecone vector search [3](#1-2) :

### Document Grading Logic

The system evaluates document relevance before proceeding [4](#1-3) :

### Web Search Fallback

When document retrieval is insufficient, the system performs web search [5](#1-4) :

### Final Analysis Generation

The system produces structured earthquake assessments [6](#1-5) :

### Shake Map Generation

It will generate a shake map with latest data for you.

## ☁️ Cloud Services Integration

### Google Cloud Authentication

The system uses service account credentials for GCP access [7](#1-6) :

## 📦 Dependencies and Requirements

The system relies on multiple Python packages for AI, cloud, and workflow orchestration [8](#1-7) :

## 🔧 Environment Configuration

Create a `.env` file inside `server/` (copy from `server/.env.example`):

```bash
# Google Cloud Platform
# Your Google Cloud Project ID
GCS_PROJECT_ID="your-gcp-project-id"
projectID="your-gcp-project-id"
GCS_REGION="us-central1"

# Service Account Credentials:
# Option A (Recommended): Path to your downloaded service account JSON key file
GOOGLE_APPLICATION_CREDENTIALS="./service_account.json"

# Option B: Base64-encoded one-line string of the service account JSON key file
# Generate with: base64 -i service_account.json | tr -d '\n'
# GOOGLE_APPLICATION_CREDENTIALS_JSON="ewogICJ0..."

# Cloud Storage Bucket Name (globally unique across GCP)
GCS_BUCKET="your-earthquake-bucket"

# Signed URL expiration in seconds (default: 36000 = 10 hours)
SIGNED_URL_TTL="36000"

# BigQuery Dataset & Table
BQ_DATASET="earthquake_dataset"
BQ_TABLE="map_store"

# ── Vector Search (Pinecone) ──
# API key from https://app.pinecone.io
PINECONE_API="your-pinecone-api-key"

# ── Web Search Tool (Tavily) ──
# API key from https://tavily.com
TAVILY_API_KEY="your-tavily-api-key"

# ── Server Config ──
PORT=8000
```

## 🚀 Step-by-Step Setup from Scratch

### 1. Google Cloud Platform (GCP)
1. **Create or select a GCP Project**:
   - Note your `Project ID` (e.g. `quakemap-123456`). Set this as `GCS_PROJECT_ID` and `projectID` in `.env`.
2. **Enable Required APIs**:
   - Cloud Storage API (`storage.googleapis.com`)
   - BigQuery API (`bigquery.googleapis.com`)
   - Vertex AI API (`aiplatform.googleapis.com`)
3. **Create Cloud Storage Bucket**:
   - Create a bucket (e.g. `quakemap-media-bucket`). Bucket names must be globally unique across GCP.
   - Set `GCS_BUCKET` in `.env`.
4. **Create a Service Account & Download Key**:
   - Go to **IAM & Admin > Service Accounts > Create Service Account**.
   - Grant the following roles:
     - `Storage Object Admin`
     - `Storage Admin`
     - `BigQuery Data Editor`
     - `BigQuery Job User`
     - `Vertex AI User`
   - Go to the **Keys** tab > **Add Key > Create new key > JSON**.
   - Download the file as `service_account.json` into the `server/` directory.
   - Set `GOOGLE_APPLICATION_CREDENTIALS="./service_account.json"` in `server/.env`.
5. **Initialize BigQuery Table**:
   - Run `python setup_bigquery.py` inside `server/` to automatically create the `earthquake_dataset` dataset and `map_store` table with the required schema.

### 2. Pinecone Vector Database
1. Sign up for a free account at [Pinecone](https://app.pinecone.io).
2. Create an API Key in the Pinecone console. Set `PINECONE_API` in `server/.env`.
3. Run `python seed_pinecone.py` inside `server/` to automatically create the `mmi-idx` index (dimension 1024, metric cosine) and populate it with USGS MMI I–X definitions.

### 3. Tavily Search API
1. Sign up for a free API key at [Tavily](https://tavily.com).
2. Set `TAVILY_API_KEY` in `server/.env`.

---

## 💻 Local Development

### 1. Backend (FastAPI)
```bash
# Navigate to server directory
cd server

# Create and activate Python virtual environment. Use uv package manager: install at https://docs.astral.sh/uv/
uv venv --python 3.11
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Initialize BigQuery and Pinecone resources
python setup_bigquery.py
python seed_pinecone.py

# Test the MMI estimation workflow
python test_pipeline.py test_page1.pdf 

# Start FastAPI development server
uvicorn main:app --reload --port 8000

# In browser, open:
http://127.0.0.1:8000/
```

### 2. Frontend (React / Vite)
```bash
# In a new terminal, navigate to client directory
cd src/client

# Install Node.js dependencies
npm install

# Start Vite development server
npm run dev

# In browser, open:
http://localhost:5173/

# Upload photos of shaking/damage and test it out!
```

### Project Structure

```
QuakemapMyanmar/
├── server/
│   ├── main.py                    # 🚀 FastAPI application entry
│   ├── app.py                     # FastAPI app & routes setup
│   ├── setup_bigquery.py          # 🛠️ BigQuery automated setup
│   ├── seed_pinecone.py           # 🎯 Pinecone indexing script
│   ├── services/
│   │   ├── crag.py               # 🤖 LangGraph CRAG workflow
│   │   ├── utilities.py          # ☁️ GCS/BigQuery utilities
│   │   ├── manage_model.py       # 🧠 Gemini model interface
│   │   └── MMIRetriever.py       # 🔍 Pinecone vector retrieval
│   ├── routes/
│   │   ├── userUpload.py         # 📤 Media upload & analysis trigger
│   │   └── analyzeMedia.py       # 📊 Direct analysis endpoint
│   ├── assets/
│   │   ├── mmi_definitions.txt   # 📖 USGS MMI I-X definitions
│   │   └── plot.sh               # 🗺️ GMT mapping script
│   └── requirements.txt          # 📦 Python dependencies
└── src/
    └── client/                   # 💻 React / Vite frontend
```
