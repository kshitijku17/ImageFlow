from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any
from utils.constants import CHROMA_DB_PATH

logger = logging.getLogger(__name__)


class ChromaManager:
    """
    Manages local persistent vector storage using ChromaDB.
    - Stores 512-dim OpenCLIP image embeddings with cosine similarity.
    - Stores file metadata: file_path, filename, mtime, size, width, height.
    - Supports incremental indexing (upsert), sync, and pruning deleted files.
    """
    _instance: ChromaManager | None = None

    def __init__(self, persist_dir: Path | str | None = None, collection_name: str = "imageflow_images"):
        self.persist_dir = str(persist_dir or CHROMA_DB_PATH)
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._is_ready = False
        self._init_error: str | None = None

    @classmethod
    def get_instance(cls, persist_dir: Path | str | None = None, collection_name: str = "imageflow_images") -> ChromaManager:
        if cls._instance is None:
            cls._instance = cls(persist_dir=persist_dir, collection_name=collection_name)
        return cls._instance

    def initialize(self) -> bool:
        """Initializes persistent ChromaDB client and collection."""
        if self._is_ready and self._collection is not None:
            return True

        try:
            import chromadb
            from chromadb.config import Settings

            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False, is_persistent=True)
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self._is_ready = True
            self._init_error = None
            logger.info(f"ChromaDB initialized at: {self.persist_dir}, collection: {self.collection_name}")
            return True
        except Exception as e:
            self._is_ready = False
            self._init_error = str(e)
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            return False

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def ensure_ready(self) -> bool:
        if not self._is_ready or self._collection is None:
            return self.initialize()
        return True

    def get_collection(self):
        self.ensure_ready()
        return self._collection

    def count(self) -> int:
        """Returns the total number of indexed vectors in the collection."""
        if not self.ensure_ready():
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.error(f"Error getting collection count: {e}")
            return 0

    def get_all_indexed_metadata(self) -> dict[str, dict[str, Any]]:
        """
        Retrieves all currently stored document IDs and their metadata dicts.
        Returns mapping: {doc_id: metadata_dict}
        """
        if not self.ensure_ready():
            return {}
        try:
            results = self._collection.get(include=["metadatas"])
            mapping = {}
            ids = results.get("ids", [])
            metadatas = results.get("metadatas", [])
            for doc_id, meta in zip(ids, metadatas):
                mapping[doc_id] = meta or {}
            return mapping
        except Exception as e:
            logger.error(f"Error fetching indexed metadata: {e}")
            return {}

    def upsert_batch(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        documents: list[str] | None = None
    ) -> bool:
        """Upserts a batch of image vectors and metadata into ChromaDB."""
        if not self.ensure_ready() or not ids:
            return False
        try:
            kwargs = {
                "ids": ids,
                "embeddings": embeddings,
                "metadatas": metadatas,
            }
            if documents:
                kwargs["documents"] = documents
            self._collection.upsert(**kwargs)
            return True
        except Exception as e:
            logger.error(f"Error upserting batch into ChromaDB: {e}", exc_info=True)
            return False

    def delete_by_ids(self, ids: list[str]) -> bool:
        """Removes specified document IDs from the collection."""
        if not self.ensure_ready() or not ids:
            return False
        try:
            self._collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} records from ChromaDB.")
            return True
        except Exception as e:
            logger.error(f"Error deleting records from ChromaDB: {e}")
            return False

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 20,
        where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Queries nearest neighbors by cosine similarity."""
        if not self.ensure_ready():
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        try:
            kwargs = {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": ["metadatas", "distances"]
            }
            if where:
                kwargs["where"] = where
            return self._collection.query(**kwargs)
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    def clear(self) -> bool:
        """Deletes all items from the collection."""
        if not self.ensure_ready():
            return False
        try:
            if self._client:
                self._client.delete_collection(self.collection_name)
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            return True
        except Exception as e:
            logger.error(f"Error clearing collection: {e}")
            return False


def get_chroma_manager() -> ChromaManager:
    return ChromaManager.get_instance()
