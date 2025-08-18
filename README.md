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

```bash
# Google Cloud Platform
projectID="client-id"
PINECONE_API="APIKEY"
TAVILY_API_KEY="APIKEY"

GOOGLE_APPLICATION_CREDENTIALS_JSON=base64encrypted-one-line-stringHERE

GCS_PROJECT_ID="client-id"
GCS_BUCKET="earthquake_bukt"
SIGNED_URL_TTL="36000"
BQ_DATASET="earthquake_dataset"
BQ_TABLE="map_store"
PORT=8000
```

## 🚀 Development Setup

```
1. Set up Google Cloud Storage Bucket
    - must strictly follow variable names. 
    - bucket: earthquake_bukt
2. Set up Big Query Table
    - must have exact same name and fields
    - Dataset name : earthquake_dataset
    - table name : map_store
    - Fields (str, nullable): blob_name, mmi_estimation, confidence, map_url, reasoning

API Generation:
    Go to APIs & Services > Create APIKEY

For Service Account: 
    Go to IAM and admin > Service Accounts > Create Service Account

Important Notes:
    serviceaccount.json must be encoded in base64

    - run base64 your_file.json in terminal
    - use this as key

```


### Local Development

```bash
# Clone and setup
git clone https://github.com/khantnhl/Quakemap.git
cd Quakemap/server

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Edit .env with your credentials

# Run development server
uvicorn main:app --reload
```

### Project Structure

```
server/
├── main.py                    # 🚀 FastAPI application entry
├── services/
│   ├── crag.py               # 🤖 CRAG workflow implementation
│   ├── utilities.py          # ☁️ GCS/BigQuery utilities  
│   └── MMIRetriever.py       # 🎯 Pinecone vector retrieval
├── routes/
│   └── userUpload.py         # 📤 Upload/result endpoints
└── requirements.txt          # 📦 Python dependencies
```

# Run frontend
```bash
# Navigate to client directory  
cd client  
  
# Install Node.js dependencies  
npm install  
  
# Start development server  
npm run dev
```