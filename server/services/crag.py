import os, base64, json
import vertexai
import json
from typing import List, Dict, Any
from typing_extensions import TypedDict
import subprocess

from vertexai.generative_models import Part
from services.MMIRetriever import MMIRetriever
from services.manage_model import get_response

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from langchain.schema import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import START, END, StateGraph

from services.utilities import load_credentials

load_dotenv()

projectID = os.environ.get('projectID') or os.environ.get('GCS_PROJECT_ID')
TRAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')

try:
    credentials = load_credentials()
    if projectID:
        vertexai.init(project=projectID, location=os.environ.get('GCS_REGION', 'us-central1'), credentials=credentials)
except Exception as e:
    print(f"Notice: vertexai init deferred: {e}")

class State(TypedDict):
    """
    State of our graph

    Attributes: 
        **blob_name : name of media file
        **signed_url
        **initial_analysis : first-pass analysis to LLM
        **context_summary : Summary of earthquake context
        **mmi_documents : Retrieved seismic reference documents
        **web_search : Whether to perform web search for additional context
        **final_analysis : final formatted response
    """
    blob_name : str
    signed_url : str
    mime_type : str
    initial_analysis : str
    context_summary : str
    mmi_documents : List[Document]
    web_search : str
    final_analysis : Dict[str, Any]
    generation : str

GRADE_DOCUMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "binary_score": {
            "type": "string",
            "description": "Documents are relevant to earthquake assessment, 'yes' or 'no'",
            "enum": ["yes", "no"]
        }
    },
    "required": ["binary_score"]
}

SEISMIC_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "blob_name": {"type": "string"},
        "description": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "coordinates": {"type": "array", "items": {"type": "number"}}
            }
        },
        "auditory_cues": {"type": "string"},
        "background_noise": {"type": "string"},
        "sounds_of_distress": {"type": "string"},
        "visual_observation": {"type": "string"},
        "video_evidence": {"type": "string"},
        "building_type": {"type": "string"},
        "building_materials": {"type": "string"},
        "evidence_analysis": {"type": "string"},
        "context_summary": {"type": "string"},
        "mmi_estimation": {"type": "number"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["blob_name", "description", "location", "mmi_estimation", "reasoning", "confidence"]
}


class MultimodalEarthquakeCRAG:
    def __init__(self):
        self.mmi_retriever = MMIRetriever()
        tavily_key = os.environ.get('TAVILY_API_KEY')
        if tavily_key:
            self.web_search_tool = TavilySearchResults(k=3, tavily_api_key=tavily_key)
        else:
            self.web_search_tool = None
        self.setup_graph()

    def setup_graph(self):
        workflow = StateGraph(State)
        workflow.add_node("initial_analysis", self.initial_analysis)
        workflow.add_node("retrieve_docs", self.retrieve_docs)
        workflow.add_node("grade_documents", self.grade_documents)
        workflow.add_node("web_search", self.web_search)
        workflow.add_node("transform_query", self.transform_query)
        workflow.add_node("final_analysis", self.final_analysis)

        workflow.add_edge(START, "initial_analysis")
        workflow.add_edge("initial_analysis", "retrieve_docs")
        workflow.add_edge("retrieve_docs", "grade_documents")
        workflow.add_conditional_edges(
                    "grade_documents",
                    self.decide_to_analyze,
                    {
                        "transform_query": "transform_query",
                        "final_analysis": "final_analysis",
                    },
                )
        workflow.add_edge("transform_query", "web_search")
        workflow.add_edge("web_search", "final_analysis")
        workflow.add_edge("final_analysis", END)

        self.app = workflow.compile()

    
    def analyze_media_and_traverse_states(self, blob_name : str, signed_url : str, mime_type : str = None):
        url_lower = signed_url.lower()
        if mime_type and mime_type in {"image/jpeg", "image/png", "image/webp", "video/mp4", "application/pdf"}:
            pass
        elif any(ext in url_lower for ext in [".jpg", ".jpeg"]):
            mime_type = "image/jpeg"
        elif ".png" in url_lower:
            mime_type = "image/png"
        elif ".webp" in url_lower:
            mime_type = "image/webp"
        elif ".mp4" in url_lower:
            mime_type = "video/mp4"
        elif ".pdf" in url_lower:
            mime_type = "application/pdf"
        elif mime_type:
            pass
        else:
            mime_type = "image/jpeg"
        
        # initial state
        inputs = {
            "blob_name": blob_name,
            "signed_url": signed_url,
            "mime_type": mime_type
        }
        
        for output in self.app.stream(inputs):
            for key, value in output.items():
                # Node
                print(f"Node '{key}':")
                # Optional: print full state at each node
                print(value)
            print("\n---\n")
       
        return value
    
    def get_structured_response(self, contents : list, response_schema):
        """Get structured response from Gemini using JSON schema."""
        
        # Add schema instructions to the content
        schema_prompt = f"""
        Please respond with a valid JSON object that matches this exact schema:
        {json.dumps(response_schema, indent=2)}
        
        Ensure all required fields are included and data types match the schema.
        """
        
        # Combine schema prompt with original contents
        full_contents = [Part.from_text(schema_prompt)] + contents
        
        response = get_response(full_contents)
        
        # Parse JSON response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                raise ValueError(f"Could not parse JSON from response: {response}")

    def decide_to_analyze(self, state):
        """Decide whether to proceed with analysis or search for more documents."""
        print("---ASSESS GRADED DOCUMENTS---")
        web_search = state["web_search"]
        
        if web_search == "Yes":
            print("---DECISION: INSUFFICIENT RELEVANT DOCUMENTS, SEARCH FOR MORE---")
            return "transform_query"
        else:
            print("---DECISION: SUFFICIENT DOCUMENTS, PROCEED TO ANALYSIS---")
            return "final_analysis"
    
    def get_media_part(self, blob_name: str, signed_url: str, mime_type: str) -> Part:
        """
        Builds a Part object for Vertex AI Gemini.
        Vertex AI requires 'gs://bucket/blob' format or raw bytes via Part.from_data.
        HTTPS signed URLs are NOT supported by Part.from_uri.
        """
        bucket = os.environ.get("GCS_BUCKET", "quakemap-media-data")

        # Method 1: Direct bytes via GCS storage client (most reliable)
        try:
            from services.utilities import lazy_clients
            storage_client, _ = lazy_clients()
            blob = storage_client.bucket(bucket).blob(blob_name)
            data = blob.download_as_bytes()
            print(f"✅ Loaded {len(data)} bytes directly from GCS blob '{blob_name}'")
            return Part.from_data(data=data, mime_type=mime_type)
        except Exception as e:
            print(f"Notice: Direct GCS download notice: {e}")

        # Method 2: Download bytes via HTTP signed URL
        if signed_url and signed_url.startswith("http"):
            try:
                import requests
                resp = requests.get(signed_url, timeout=30)
                if resp.ok and resp.content:
                    print(f"✅ Downloaded {len(resp.content)} bytes via signed URL")
                    return Part.from_data(data=resp.content, mime_type=mime_type)
            except Exception as e:
                print(f"Notice: HTTP signed_url download notice: {e}")

        # Method 3: Native gs:// URI
        if bucket and blob_name:
            gcs_uri = f"gs://{bucket}/{blob_name}"
            print(f"Trying native GCS URI: {gcs_uri}")
            return Part.from_uri(gcs_uri, mime_type=mime_type)

        raise RuntimeError(f"Could not load media part for blob: {blob_name}")

    def initial_analysis(self, state):
        blob_name = state["blob_name"]
        signed_url = state["signed_url"]
        mime_type = state["mime_type"]

        Description_Prompt = f"""
            <System Prompt>
            You are an expert seismologist, studying earthquake impact using the Modified Mercalli Intensity Scale (MMI). 
            Your task is to carefully analyze image or video evidence to identify visual and auditory indicators of seismic shaking.
            Avoid making assumptions or what is not visible or audible in the media. 
            Carefully analyze and describe the contents of the image or video in detail.
            </System Prompt>

            For images 
                - Look for visible surface damage, collapsed buildings, cracks, dust clouds, displaced infrastructure.
                - If it's a satellite or aerial view, analyze top-down damage: roof collapses, ruptured roads, debris zones, or displaced land features.
            For videos
                - Detect dynamic events such as shaking lights, falling debris, swaying structures, ground rupture, or displacement.
                - Audio may be absent but it does not mean there is no earthquake
                - If audio is present, analyze for screams, panic, structural sounds (crashing, creaking), or silence after impact.
        """
        
        media_part = self.get_media_part(blob_name, signed_url, mime_type)
        contents = [
            Part.from_text(Description_Prompt),
            media_part
        ]
        analysis = get_response(contents, json_mode=False)

        return {
            "blob_name": blob_name,
            "signed_url": signed_url,
            "mime_type": mime_type,
            "initial_analysis": analysis,
            "context_summary": analysis # for retrieval
        }

    def retrieve_docs(self, state):
        print("---RETRIEVE MMI DOCUMENTS---")
        context = state["context_summary"]
        
        # retrieve from PineCone
        retrieved_docs = self.mmi_retriever.retrieveDocs(context)
        print("retrieved from PC: ", retrieved_docs)

        return {
            **state, 
            "mmi_documents": retrieved_docs
        }
    
    def grade_documents(self, state):
        print("---GRADE RETRIEVED DOCUMENTS---")

        context = state["context_summary"]
        documents = state.get("mmi_documents", [])
        filtered_docs = []
        web_search = "No"

        if not documents:
            return {
                **state,
                "mmi_documents": [],
                "web_search": "Yes"
            }

        import time
        for i, doc in enumerate(documents, 1):
            grader_prompt = f"""
                You are a grader assessing relevance of seismic/earthquake documents to earthquake damage assessment.
                If the document contains information about earthquake intensity scales (like MMI), building damage patterns,
                seismic indicators, or earthquake impact assessment, grade it as relevant.
                Retrieved document: {doc.page_content}
            Analysis context: {context}
            """

            try:
                contents = [Part.from_text(grader_prompt)]
                score = self.get_structured_response(contents, GRADE_DOCUMENTS_SCHEMA)

                if score.get("binary_score") == "yes":
                    print(f"---GRADE: DOCUMENT {i} RELEVANT---")
                    filtered_docs.append(doc)
                else:
                    print(f"---GRADE: DOCUMENT {i} NOT RELEVANT---")
                    web_search = "Yes"
            except Exception as e:
                print(f"Notice: Document {i} grading encountered rate limit/error ({e}). Defaulting to RELEVANT.")
                filtered_docs.append(doc)

            # Pacing delay between grading calls to avoid Vertex AI burst quota
            time.sleep(1.0)
        
        if not filtered_docs:
            web_search = "Yes"

        return {
            **state, 
            "mmi_documents" : filtered_docs,
            "web_search" : web_search
        }

    def web_search(self, state):
        """Search web for additional seismic information."""
        print("---WEB SEARCH FOR SEISMIC INFO---")
        query = state["context_summary"]
        documents = list(state.get("mmi_documents", []))
        
        # Perform web search
        if self.web_search_tool:
            try:
                search_results = self.web_search_tool.invoke({"query": f"earthquake intensity scale MMI damage assessment {query}"})
                web_content = "\n".join([result.get("content", "") for result in search_results if isinstance(result, dict)])
                web_doc = Document(page_content=web_content)
                documents.append(web_doc)
            except Exception as e:
                print(f"Notice: Tavily search error: {e}")
        
        return {
            **state,
            "mmi_documents": documents
        }

    def transform_query(self, state):
        """Transform query for better web search results using custom Gemini."""
        print("---TRANSFORM QUERY---")
        context = state["context_summary"]
        
        query_prompt = f"""
        You are a query optimizer for seismic information retrieval.
        Improve the earthquake assessment query to better find relevant seismic reference materials.
        
        Original context: {context}
        
        Provide an improved query for finding relevant earthquake intensity and damage assessment information.
        """
        
        contents = [Part.from_text(query_prompt)]
        better_query = get_response(contents, json_mode=False)
        
        return {
            **state,
            "context_summary": better_query
        }
    
    def final_analysis(self, state):
        """Generate final seismic analysis with MMI estimation using custom Gemini."""
        print("---GENERATE FINAL SEISMIC ANALYSIS---")
        initial_analysis = state["initial_analysis"]
        documents = state["mmi_documents"]
        blob_name = state["blob_name"]
        
        # Format documents for analysis
        doc_context = "\n\n".join([doc.page_content for doc in documents])
        
        # Create final analysis prompt
        final_prompt = f"""
        You are an expert seismologist providing MMI assessment.
        Using the initial analysis and retrieved seismic reference documents, provide a complete assessment
        including MMI estimation with reasoning and confidence score.
        
        Initial Analysis: {initial_analysis}
        
        Reference Documents: {doc_context}
        
        Provide complete seismic analysis for {blob_name} including:
        - Detailed description of damages and observations
        - Must extract Location information [latitude, longitude] from the image (use "Unknown" if not determinable)  
        - Auditory and visual evidence summary
        - Building type and materials assessment
        - MMI estimation (as float) with detailed reasoning
        - Confidence score (0.0 to 1.0)
        """
        
        contents = [Part.from_text(final_prompt)]
        
        # Generate structured analysis using custom function
        analysis = self.get_structured_response(contents, SEISMIC_ANALYSIS_SCHEMA)
        
        # Format final 
        generation = f"""
        EARTHQUAKE ASSESSMENT REPORT
        ============================
        File: {analysis.get('blob_name', blob_name)}
        MMI Estimation: {analysis.get('mmi_estimation', 'N/A')}
        Confidence: {analysis.get('confidence', 'N/A')}
        
        Description: {analysis.get('description', '')}
        Location: {analysis.get('location', '')}
        Building Type: {analysis.get('building_type', '')}
        Evidence Analysis: {analysis.get('evidence_analysis', '')}
        Reasoning: {analysis.get('reasoning', '')}
        """
        
        return {
            **state,
            "final_analysis": analysis,
            "generation": generation
        }

    
from google.cloud import bigquery
projectID = os.environ['projectID']

if __name__ == "__main__":
    
    client = bigquery.Client(project=projectID)

    query = """
        SELECT *
        FROM `gen-lang-client-0175492774.earthquake_dataset.url_table`
    """

    rows = client.query_and_wait(query)  # Make an API request.

    signed_urls = []
    video_urls = []
    image_without_location = []

    for row in rows:
        if("pdf" in row["signed_url"]):
            signed_urls.append((row["blob_name"], row["signed_url"]))
        elif("jpg" in row["signed_url"] or "jpeg" in row["signed_url"]):
            image_without_location.append((row["blob_name"], row["signed_url"]))
        elif("mp4" in row["signed_url"]):
            video_urls.append((row["blob_name"], row["signed_url"]))

    # print("size: ", len(signed_urls))
    # print("size: ", len(image_without_location))
    # print("size: ", len(video_urls))

    # tuple (blob, signed_url)
    quake_CRAG = MultimodalEarthquakeCRAG()

    result = quake_CRAG.analyze_media_and_traverse_states(
        blob_name=signed_urls[0][0],
        signed_url=signed_urls[0][1],
        mime_type="application/pdf")
    
    print(result["generation"])

    with open("sample_test.txt", 'w') as f:
        f.write(result["generation"])

    lat = result["final_analysis"]["location"]["coordinates"][0]
    lon = result["final_analysis"]["location"]["coordinates"][1]
    mmi = result["final_analysis"]["mmi_estimation"]

    # add point to map
    with open("./assets/records.txt", "w") as f:
        f.write(f"{lon} {lat} {mmi}\n")

    # run gmt again to generate map
    try:
        subprocess.run(["plot.bat"])
    except subprocess.CalledProcessError as e:
        print("gmt failed: ", e)

