import os
import logging
from pinecone import Pinecone, ServerlessSpec
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from dotenv import load_dotenv
from langchain.schema import Document

load_dotenv()

#logger setup
logger = logging.getLogger(__name__)

class MMIRetriever:
    """
    Retrieves MMI scale definitions from knowledge base, using LlamaIndex for RAG.
    """
    def __init__(self):
        self.EMBEDDING_MODEL_NAME = "gemini-embedding-001"
        self.DIMENSIONALITY = 1024
        self.spec = ServerlessSpec(cloud="aws", region="us-east-1")
        self.index_name = "mmi-idx"
        api_key = os.environ.get('PINECONE_API')
        if api_key:
            try:
                self.pc = Pinecone(api_key=api_key)
                self.index = self.pc.Index(self.index_name)
            except Exception as e:
                logger.warning(f"Pinecone client init notice: {e}")
                self.pc = None
                self.index = None
        else:
            self.pc = None
            self.index = None

    def createIndex(self) -> None:
        if not self.pc:
            logger.warning("Pinecone API key not configured")
            return
        existing_names = [idx.name for idx in self.pc.list_indexes()]
        if self.index_name not in existing_names:
            self.pc.create_index(self.index_name, dimension=self.DIMENSIONALITY, metric="cosine", spec=self.spec)
            logger.info("Indexing Completed.")
            self.index = self.pc.Index(self.index_name)
            return
        logger.info("Index Exists..")
        self.index = self.pc.Index(self.index_name)
        return
    
    def embed_text(self, texts: list[str], task: str) -> list[list[float]]:
        """Embeds texts with Embedding Model"""

        task = task
        model = TextEmbeddingModel.from_pretrained(self.EMBEDDING_MODEL_NAME)
        kwargs = dict(output_dimensionality=self.DIMENSIONALITY) if self.DIMENSIONALITY else {}

        embeddings = []

        for text in texts:
            text_input = TextEmbeddingInput(text, task)
            embedding = model.get_embeddings([text_input], **kwargs)
            embeddings.append(embedding[0].values)

        return embeddings
    
    def indexing(self, docsPath : str):
        """ Indexing to PineCone VectorStore """

        docsFromPath = self.load_texts_from_file(docsPath)
        embeddings = self.embed_text(docsFromPath, "RETRIEVAL_DOCUMENT")

        items_to_insert = [
            (f"mmi-{i+1}", embedding, {"text": text})
            for i, (embedding, text) in enumerate(zip(embeddings, docsFromPath))
        ]

        self.index.upsert(vectors=items_to_insert)

        return

    def load_texts_from_file(self, file_path: str) -> list[str]:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

        return logger.error("File Failed to Open..")

    def retrieve(self, query : str):
        if(not query):
            logger.error("Empty Query")

        embed_query = self.embed_text([query], task="RETRIEVAL_QUERY")[0]

        # search in PineCone VectorStore
        results = self.index.query(vector=embed_query, top_k=3, include_metadata=True)
        
        results = self.retrieve_mmi(results)
        return results
        
    def retrieveDocs(self, query : str):
        if(not query):
            logger.error("Empty Query")
            return []

        if not self.index:
            logger.warning("Pinecone index not available")
            return []

        try:
            embed_query = self.embed_text([query], task="RETRIEVAL_QUERY")[0]
            docs = self.index.query(vector=embed_query, top_k=3, include_metadata=True)
            results = []
            
            for record in docs.get('matches', []):
                if record.get('metadata') and 'text' in record['metadata']:
                    doc = Document(page_content=record['metadata']['text'])
                    results.append(doc)
            return results
        except Exception as e:
            logger.warning(f"Pinecone query notice: {e}")
            return []
    
    def retrieve_mmi(self, input):
        result = []
        for record in input['matches']:
            print(record['id'].split("-"))
            score = record['id'].split("-")[-1]
            result.append(int(score))
        
        # mmi_mean = round(sum(result)/len(result), 1)
        return result

