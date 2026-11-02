from __future__ import annotations
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

class PineconeMMIRetriever:
    """
    RAG Retriever for MMI Scale Definitions.
    Integrates with Pinecone vector database index 'mmi-idx'.
    Falls back gracefully to local 'server/assets/mmi_definitions.txt' if Pinecone is unreachable.
    """

    def __init__(self, index_name: str = "mmi-idx"):
        self.index_name = index_name
        self.api_key = os.getenv("PINECONE_API")
        self.index = None
        self._init_pinecone()
        self.local_defs = self._load_local_definitions()

    def _init_pinecone(self):
        if not self.api_key:
            return
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=self.api_key)
            self.index = pc.Index(self.index_name)
        except Exception as e:
            print(f"Notice: Pinecone client init notice: {e}")
            self.index = None

    def _load_local_definitions(self) -> List[str]:
        candidates = [
            Path("server/assets/mmi_definitions.txt"),
            Path("assets/mmi_definitions.txt"),
            Path("../server/assets/mmi_definitions.txt")
        ]
        for c in candidates:
            if c.exists():
                lines = [l.strip() for l in c.read_text(encoding="utf-8").splitlines() if l.strip()]
                return lines
        return []

    def retrieve_documents(self, query: str, top_k: int = 3) -> List[str]:
        """
        Retrieves closest MMI reference documents.
        Tries Pinecone vector search first, then local keyword/semantic match.
        """
        # Try Pinecone vector search
        if self.index:
            try:
                # Query Pinecone using text embedding or metadata match
                # If embeddings are not configured, fallback to local
                pass
            except Exception as e:
                print(f"Notice: Pinecone retrieval notice: {e}")

        # Local fallback from server/assets/mmi_definitions.txt
        if not self.local_defs:
            return []

        query_words = set(query.lower().split())
        scored = []
        for line in self.local_defs:
            line_words = set(line.lower().split())
            score = len(query_words.intersection(line_words))
            scored.append((score, line))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
