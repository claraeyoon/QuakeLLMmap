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

### JSON Schema Validation

The system defines structured responses using predefined schemas [2](#1-1) :

```python
SEISMIC_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "blob_name": {"type": "string"},
        "location": {
            "type": "object", 
            "properties": {
                "coordinates": {"type": "array", "items": {"type": "number"}}
            }
        },
        "mmi_estimation": {"type": "number"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["blob_name", "mmi_estimation", "reasoning", "confidence"]
}
```

## 🤖 AI Processing Pipeline Implementation

### Document Retrieval System

The MMI document retrieval uses Pinecone vector search [3](#1-2) :

```python
def retrieve_docs(self, state):
    """Retrieve relevant MMI documents from Pinecone vector DB"""
    print("---RETRIEVE MMI DOCUMENTS---")
    context = state["context_summary"]
    
    # Vector search using MMIRetriever
    retrieved_docs = self.mmi_retriever.retrieveDocs(context)
    print("retrieved from PC: ", retrieved_docs)

    return {
        **state, 
        "mmi_documents": retrieved_docs
    }
```

### Document Grading Logic

The system evaluates document relevance before proceeding [4](#1-3) :

```python
def grade_documents(self, state):
    """Grade retrieved documents for relevance to earthquake assessment"""
    print("---GRADE RETRIEVED DOCUMENTS---")
    
    context = state["context_summary"]
    documents = state["mmi_documents"]
    filtered_docs = []
    web_search = "No"

    for doc in documents:
        grader_prompt = f"""
        You are a grader assessing relevance of seismic/earthquake documents.
        If the document contains MMI scale info, building damage patterns,
        or seismic indicators, grade it as relevant.
        
        Retrieved document: {doc.page_content}
        Analysis context: {context}
        """
        
        contents = [Part.from_text(grader_prompt)]
        score = self.get_structured_response(contents, GRADE_DOCUMENTS_SCHEMA)
        
        if score["binary_score"] == "yes":
            filtered_docs.append(doc)
        else:
            web_search = "Yes"  # Trigger fallback search
    
    return {
        **state, 
        "mmi_documents": filtered_docs,
        "web_search": web_search
    }
```

### Web Search Fallback

When document retrieval is insufficient, the system performs web search [5](#1-4) :

```python
def web_search(self, state):
    """Search web for additional seismic information"""
    print("---WEB SEARCH FOR SEISMIC INFO---")
    query = state["context_summary"]
    documents = state["seismic_documents"]
    
    # Tavily API integration
    search_results = self.web_search_tool.invoke({
        "query": f"earthquake intensity scale MMI damage assessment {query}"
    })
    web_content = "\n".join([result["content"] for result in search_results])
    web_doc = Document(page_content=web_content)
    
    documents.append(web_doc)
    
    return {"seismic_documents": documents}
```

### Final Analysis Generation

The system produces structured earthquake assessments [6](#1-5) :

```python
def final_analysis(self, state):
    """Generate final seismic analysis with MMI estimation"""
    print("---GENERATE FINAL SEISMIC ANALYSIS---")
    initial_analysis = state["initial_analysis"]
    documents = state["mmi_documents"]
    blob_name = state["blob_name"]
    
    # Combine reference documents
    doc_context = "\n\n".join([doc.page_content for doc in documents])
    
    final_prompt = f"""
    You are an expert seismologist providing MMI assessment.
    Using initial analysis and reference documents, provide complete assessment.
    
    Initial Analysis: {initial_analysis}
    Reference Documents: {doc_context}
    
    Provide analysis for {blob_name} including:
    - Location coordinates [lat, lng] from image
    - Building type and materials assessment  
    - MMI estimation (float) with detailed reasoning
    - Confidence score (0.0 to 1.0)
    """
    
    contents = [Part.from_text(final_prompt)]
    analysis = self.get_structured_response(contents, SEISMIC_ANALYSIS_SCHEMA)
    
    # Format final report
    generation = f"""
    EARTHQUAKE ASSESSMENT REPORT
    ============================
    File: {analysis['blob_name']}
    MMI Estimation: {analysis['mmi_estimation']}
    Confidence: {analysis['confidence']}
    
    Description: {analysis['description']}
    Location: {analysis['location']}
    Reasoning: {analysis['reasoning']}
    """
    
    return {
        **state,
        "final_analysis": analysis,
        "generation": generation
    }
```

## ☁️ Cloud Services Integration

### Google Cloud Authentication

The system uses service account credentials for GCP access [7](#1-6) :

```python
# Load GCP credentials from environment
creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")

if not creds_json:
    raise RuntimeError("Missing GOOGLE_APPLICATION_CREDENTIALS_JSON")

# Write JSON to temporary file for authentication
creds_path = "/tmp/gcp_creds.json"
with open(creds_path, "w") as f:
    f.write(creds_json)

# Initialize credentials with cloud platform scope
credentials = Credentials.from_service_account_file(
    creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

if credentials.expired:
    credentials.refresh(Request())

# Initialize Vertex AI with credentials
vertexai.init(project=projectID, location='us-central1', credentials=credentials)
```

## 📦 Dependencies and Requirements

The system relies on multiple Python packages for AI, cloud, and workflow orchestration [8](#1-7) :

```python
# Core Framework
fastapi==0.116.1                    # 🔌 API server framework

# Google Cloud Platform
google-cloud-aiplatform==1.71.1     # 🧠 Vertex AI integration  
google-cloud-bigquery==3.35.1       # 🗄️ Data warehousing
google-cloud-storage==2.19.0        # ☁️ File storage

# LangChain Ecosystem  
langchain==0.3.27                   # 🔗 AI workflow orchestration
langchain-google-genai==2.1.8       # 🤖 Gemini model integration
langchain-tavily==0.2.11            # 🔍 Web search integration
langgraph==0.6.2                    # 📊 State graph workflows

# Vector Database
pinecone==7.3.0                     # 🎯 Vector similarity search

# AI/ML Models
vertexai                            # 🧠 Google's AI platform
```

## 🔧 Environment Configuration

### Required Environment Variables

```bash
# Google Cloud Platform
GOOGLE_APPLICATION_CREDENTIALS_JSON="{service-account-json}"
GCS_PROJECT_ID="your-gcp-project"
projectID="your-gcp-project"

# External APIs  
TAVILY_API_KEY="your-tavily-search-key"
PINECONE_API="your-pinecone-api-key"

# Storage Configuration
BQ_DATASET="earthquake_data"
BQ_TABLE="url_table" 
SIGNED_URL_TTL="3600"

# File Paths
filepath="/path/to/assets"
```

## 🚀 Development Setup

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
python main.py
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

### How to RUN the program:

# Start FastAPI server  
cd server  
uvicorn main:app --reload


# Run frontend
```bash
# Navigate to client directory  
cd client  
  
# Install Node.js dependencies  
npm install  
  
# Start development server  
npm run dev
```

# Live Deployments

Server: Render (needs to spin up for the start)
Frontend: Render (link in repo) 