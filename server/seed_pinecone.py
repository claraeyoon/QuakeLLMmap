import os
import sys
from dotenv import load_dotenv

# Ensure server folder is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.MMIRetriever import MMIRetriever

def main():
    load_dotenv()
    api_key = os.environ.get("PINECONE_API")
    if not api_key or api_key == "APIKEY":
        print("❌ Error: PINECONE_API is not set in .env. Please update your .env file with your Pinecone API key.")
        sys.exit(1)

    print("🚀 Initializing MMIRetriever...")
    retriever = MMIRetriever()

    print("📦 Creating or verifying Pinecone index 'mmi-idx'...")
    retriever.createIndex()

    defs_path = os.path.join(os.path.dirname(__file__), "assets", "mmi_definitions.txt")
    if not os.path.exists(defs_path):
        print(f"❌ Error: {defs_path} not found.")
        sys.exit(1)

    print(f"📝 Embedding and indexing MMI definitions from {defs_path}...")
    try:
        retriever.indexing(defs_path)
        print("✅ Successfully indexed MMI scale definitions into Pinecone!")
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        print("Tip: Make sure your Google Cloud credentials (for Vertex AI embedding model) are configured.")
        sys.exit(1)

    print("\n🔍 Running test query...")
    try:
        test_query = "severe building collapse and ground cracking"
        results = retriever.retrieveDocs(test_query)
        print(f"Test query: '{test_query}'")
        for i, doc in enumerate(results, 1):
            print(f"  [{i}] {doc.page_content[:90]}...")
        print("\n🎉 Pinecone vector store is ready for Quakemap!")
    except Exception as e:
        print(f"⚠️ Test query warning: {e}")

if __name__ == "__main__":
    main()
