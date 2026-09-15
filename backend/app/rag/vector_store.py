import os
import math
import hashlib
import re
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from app.core.config import settings

STOP_WORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
    "with", "is", "are", "was", "were", "what", "our", "do", "we", "by",
    "be", "this", "that", "from", "as", "it", "its", "all", "can"
}

class FastLocalEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Offline, zero-network deterministic embedding function.
    Eliminates external model download and SSL certificate verification failures.
    Generates normalized 1024-dimensional dense semantic vectors using filtered content-word hashing.
    """
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def name(self) -> str:
        return "fast_local"

    def get_config(self) -> Dict[str, Any]:
        return {"dim": self.dim}

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        for text in input:
            vector = [0.0] * self.dim
            words = re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', text.lower())
            content_words = [w for w in words if w not in STOP_WORDS]
            
            if not content_words:
                content_words = words or ["empty"]

            for w in content_words:
                # Primary word hash
                h_val = int(hashlib.sha256(w.encode('utf-8')).hexdigest(), 16)
                idx = h_val % self.dim
                sign = 1.0 if ((h_val >> 16) & 1) else -1.0
                vector[idx] += sign * 1.5

                # Character n-grams for words longer than 4 chars
                if len(w) >= 5:
                    for i in range(len(w) - 3):
                        ngram = w[i:i+4]
                        h_ng = int(hashlib.md5(ngram.encode('utf-8')).hexdigest(), 16)
                        vector[h_ng % self.dim] += 0.5

            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0:
                vector = [v / norm for v in vector]
            else:
                vector[0] = 1.0
            embeddings.append(vector)
        return embeddings

class VectorStoreManager:
    _instance: Optional["VectorStoreManager"] = None
    _client: Optional[chromadb.PersistentClient] = None
    _collection: Optional[chromadb.Collection] = None
    _embedding_function: Any = None

    def __init__(self):
        persist_dir = settings.CHROMA_PERSIST_DIRECTORY
        os.makedirs(persist_dir, exist_ok=True)
        
        # Configure embedding function
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-"):
            try:
                import chromadb.utils.embedding_functions as ef
                self._embedding_function = ef.OpenAIEmbeddingFunction(
                    api_key=settings.OPENAI_API_KEY,
                    model_name=settings.OPENAI_EMBEDDING_MODEL
                )
            except Exception as e:
                print(f"[VectorStore] Falling back to local offline embedding function: {e}")
                self._embedding_function = FastLocalEmbeddingFunction()
        else:
            self._embedding_function = FastLocalEmbeddingFunction()

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        try:
            self._collection = self._client.get_or_create_collection(
                name="company_knowledge",
                metadata={"hnsw:space": "cosine"},
                embedding_function=self._embedding_function
            )
        except Exception:
            try:
                self._client.delete_collection("company_knowledge")
            except Exception:
                pass
            self._collection = self._client.get_or_create_collection(
                name="company_knowledge",
                metadata={"hnsw:space": "cosine"},
                embedding_function=self._embedding_function
            )

    @classmethod
    def get_instance(cls) -> "VectorStoreManager":
        if cls._instance is None:
            cls._instance = VectorStoreManager()
        return cls._instance

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            raise RuntimeError("Chroma collection is not initialized.")
        return self._collection

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None
    ):
        """Adds documents and metadata to the collection."""
        if embeddings:
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings
            )
        else:
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )

    def query(
        self,
        query_text: str,
        n_results: int = 4,
        query_embedding: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Queries the collection for matching documents."""
        count = self.collection.count()
        if count == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        actual_n = min(n_results, count)
        if query_embedding:
            return self.collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_n
            )
        else:
            return self.collection.query(
                query_texts=[query_text],
                n_results=actual_n
            )

    def count(self) -> int:
        return self.collection.count()

    def clear(self):
        """Resets the collection."""
        if self._client:
            try:
                self._client.delete_collection("company_knowledge")
            except Exception:
                pass
            self._collection = self._client.get_or_create_collection(
                name="company_knowledge",
                metadata={"hnsw:space": "cosine"},
                embedding_function=self._embedding_function
            )
