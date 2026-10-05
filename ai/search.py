from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any
import numpy as np

from ai.clip_manager import get_model_manager
from ai.chroma_manager import get_chroma_manager
from ai.date_parser import parse_date_and_semantic_query, ParsedQuery

logger = logging.getLogger(__name__)


def is_path_in_folder(file_path: str, folder_path: str) -> bool:
    """Case-insensitive check whether file_path is inside folder_path."""
    try:
        norm_f = os.path.abspath(os.path.normcase(os.path.normpath(str(folder_path))))
        norm_p = os.path.abspath(os.path.normcase(os.path.normpath(str(file_path))))
        return norm_p == norm_f or norm_p.startswith(norm_f + os.sep) or norm_p.startswith(norm_f + "/")
    except Exception:
        return False


def matches_date_filter(meta: dict[str, Any], parsed: ParsedQuery) -> bool:
    """Checks if a record's metadata satisfies the parsed date filter."""
    if parsed.year is None and not parsed.start_date:
        return True

    m_year = meta.get("year")
    m_month = meta.get("month")
    m_day = meta.get("day")
    m_date = meta.get("date")

    # If metadata has no explicit date fields, derive from mtime
    if (m_year is None or m_date is None) and "mtime" in meta:
        from datetime import datetime
        try:
            dt = datetime.fromtimestamp(float(meta["mtime"]))
            if m_year is None:
                m_year = dt.year
            if m_month is None:
                m_month = dt.month
            if m_day is None:
                m_day = dt.day
            if m_date is None:
                m_date = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    if parsed.year is not None and m_year is not None and int(m_year) != parsed.year:
        return False
    if parsed.month is not None and m_month is not None and int(m_month) != parsed.month:
        return False
    if parsed.day is not None and m_day is not None and int(m_day) != parsed.day:
        return False

    if parsed.start_date and parsed.end_date and m_date:
        m_date_str = str(m_date)[:10]
        if not (parsed.start_date <= m_date_str <= parsed.end_date):
            return False

    # If date was queried but record has no date information
    if (parsed.year is not None or parsed.start_date is not None) and m_year is None and m_date is None:
        return False

    return True


def search_similar_images(
    query: str,
    n_results: int = 20,
    folder_filter: str | None = None,
    paths_filter: list[str] | set[str] | None = None,
    chroma_manager=None,
    clip_manager=None,
) -> list[dict[str, Any]]:
    """
    Performs natural language semantic search with date and metadata filtering.
    Searches ONLY inside the specified folder_filter / paths_filter (source folder).

    Supports:
        - Date-only search (e.g. "show me photos from 10 December 2025")
        - Semantic + Date search (e.g. "show me dog photos from 10 December 2025")
        - Pure Semantic search (e.g. "show me dogs")
    """
    if not query or not query.strip():
        return []

    clip = clip_manager or get_model_manager()
    chroma = chroma_manager or get_chroma_manager()

    if not chroma.ensure_ready():
        logger.warning("ChromaDB is not ready for search.")
        return []

    if chroma.count() == 0:
        logger.warning("ChromaDB has 0 indexed images.")
        return []

    parsed = parse_date_and_semantic_query(query)
    norm_paths_filter = {
        os.path.abspath(os.path.normcase(os.path.normpath(str(p)))) for p in paths_filter
    } if paths_filter else None

    # Step 1: Collect candidates that belong to source folder and pass date filter
    all_records = chroma.get_all_indexed_metadata()
    candidate_records: list[tuple[str, str, dict[str, Any]]] = []

    for doc_id, meta in all_records.items():
        meta = meta or {}
        file_path = meta.get("file_path", doc_id)
        norm_path = os.path.abspath(os.path.normpath(str(file_path)))
        norm_case_path = os.path.abspath(os.path.normcase(os.path.normpath(str(file_path))))

        # Folder scoping: search ONLY inside the currently selected Source Folder
        if folder_filter and not is_path_in_folder(norm_path, folder_filter):
            continue
        if norm_paths_filter and norm_case_path not in norm_paths_filter:
            continue

        # Date filtering
        if (parsed.year is not None or parsed.start_date is not None):
            if not matches_date_filter(meta, parsed):
                continue

        candidate_records.append((doc_id, norm_path, meta))

    if not candidate_records:
        return []

    # Case 1: Date-Only Search (e.g. "photos from 10 December 2025", "find photos from Dec 2025")
    if parsed.is_date_only:
        # Sort by mtime descending (most recent first)
        candidate_records.sort(key=lambda x: float(x[2].get("mtime", 0.0)), reverse=True)
        results = []
        for doc_id, norm_path, meta in candidate_records[:n_results]:
            results.append({
                "file_path": norm_path,
                "filename": meta.get("filename", Path(norm_path).name),
                "similarity_score": 1.0,
                "metadata": meta,
            })
        return results

    # Case 2: Semantic Search (with or without Date filter)
    search_text = parsed.clean_query if parsed.clean_query else query
    text_emb = clip.get_text_embedding(search_text)
    if text_emb is None:
        logger.error(f"Failed to generate text embedding for query: '{search_text}'")
        return []

    # Fetch candidate embeddings from ChromaDB
    candidate_ids = [c[0] for c in candidate_records]
    collection = chroma.get_collection()
    data = collection.get(ids=candidate_ids, include=["embeddings", "metadatas"])

    emb_list = data.get("embeddings", [])
    ids_list = data.get("ids", [])
    meta_list = data.get("metadatas", [])

    if emb_list is None or len(emb_list) == 0:
        return []

    text_vec = np.array(text_emb, dtype=np.float32)
    t_norm = np.linalg.norm(text_vec)
    if t_norm > 0:
        text_vec /= t_norm

    scored_results = []
    for c_id, c_emb, c_meta in zip(ids_list, emb_list, meta_list):
        c_meta = c_meta or {}
        f_path = c_meta.get("file_path", c_id)
        norm_path = os.path.abspath(os.path.normpath(str(f_path)))

        img_vec = np.array(c_emb, dtype=np.float32)
        i_norm = np.linalg.norm(img_vec)
        if i_norm > 0:
            img_vec /= i_norm

        # Cosine similarity dot product
        sim = float(np.dot(text_vec, img_vec))
        sim_score = round(max(0.0, min(1.0, sim)), 4)

        scored_results.append({
            "file_path": norm_path,
            "filename": c_meta.get("filename", Path(norm_path).name),
            "similarity_score": sim_score,
            "metadata": c_meta,
        })

    # Sort descending by semantic similarity score
    scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_results[:n_results]


def search_by_reference_image(
    reference_image_input: str | Path | Any,
    n_results: int = 20,
    folder_filter: str | None = None,
    paths_filter: list[str] | set[str] | None = None,
    exclude_reference: bool = True,
    parsed_date_query: ParsedQuery | None = None,
    chroma_manager=None,
    clip_manager=None,
) -> list[dict[str, Any]]:
    """
    Performs visual similarity search using a reference image.
    Scoped strictly to the folder_filter / paths_filter (Source Folder).
    """
    clip = clip_manager or get_model_manager()
    chroma = chroma_manager or get_chroma_manager()

    if not chroma.ensure_ready():
        logger.warning("ChromaDB is not ready for search.")
        return []

    if chroma.count() == 0:
        logger.warning("ChromaDB has 0 indexed images.")
        return []

    ref_emb = clip.get_image_embedding(reference_image_input)
    if ref_emb is None:
        logger.error(f"Failed to extract image embedding from reference: {reference_image_input}")
        return []

    norm_ref_path = None
    if isinstance(reference_image_input, (str, Path)):
        norm_ref_path = os.path.abspath(os.path.normcase(os.path.normpath(str(reference_image_input))))

    norm_paths_filter = {
        os.path.abspath(os.path.normcase(os.path.normpath(str(p)))) for p in paths_filter
    } if paths_filter else None

    all_records = chroma.get_all_indexed_metadata()
    candidate_records: list[tuple[str, str, dict[str, Any]]] = []

    for doc_id, meta in all_records.items():
        meta = meta or {}
        file_path = meta.get("file_path", doc_id)
        norm_path = os.path.abspath(os.path.normpath(str(file_path)))
        norm_case_path = os.path.abspath(os.path.normcase(os.path.normpath(str(file_path))))

        if exclude_reference and norm_ref_path and norm_case_path == norm_ref_path:
            continue
        if folder_filter and not is_path_in_folder(norm_path, folder_filter):
            continue
        if norm_paths_filter and norm_case_path not in norm_paths_filter:
            continue

        if parsed_date_query and (parsed_date_query.year is not None or parsed_date_query.start_date is not None):
            if not matches_date_filter(meta, parsed_date_query):
                continue

        candidate_records.append((doc_id, norm_path, meta))

    if not candidate_records:
        return []

    candidate_ids = [c[0] for c in candidate_records]
    collection = chroma.get_collection()
    data = collection.get(ids=candidate_ids, include=["embeddings", "metadatas"])

    emb_list = data.get("embeddings", [])
    ids_list = data.get("ids", [])
    meta_list = data.get("metadatas", [])

    if emb_list is None or len(emb_list) == 0:
        return []

    ref_vec = np.array(ref_emb, dtype=np.float32)
    r_norm = np.linalg.norm(ref_vec)
    if r_norm > 0:
        ref_vec /= r_norm

    scored_results = []
    for c_id, c_emb, c_meta in zip(ids_list, emb_list, meta_list):
        c_meta = c_meta or {}
        f_path = c_meta.get("file_path", c_id)
        norm_path = os.path.abspath(os.path.normpath(str(f_path)))

        img_vec = np.array(c_emb, dtype=np.float32)
        i_norm = np.linalg.norm(img_vec)
        if i_norm > 0:
            img_vec /= i_norm

        sim = float(np.dot(ref_vec, img_vec))
        sim_score = round(max(0.0, min(1.0, sim)), 4)

        scored_results.append({
            "file_path": norm_path,
            "filename": c_meta.get("filename", Path(norm_path).name),
            "similarity_score": sim_score,
            "metadata": c_meta,
        })

    scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_results[:n_results]


def search_images(
    paths: list[str],
    query: str,
    n_results: int = 20
) -> list[tuple[float, str]]:
    """
    High-level visual semantic search with fallback to lexical search.
    """
    semantic_results = search_similar_images(
        query=query,
        n_results=n_results,
        paths_filter=paths
    )

    if semantic_results:
        return [(r["similarity_score"], r["file_path"]) for r in semantic_results]

    q = query.lower()
    matches = []
    tokens = [x for x in q.replace(",", " ").split() if len(x) > 2]
    for p in paths:
        name = Path(p).stem.lower().replace("_", " ").replace("-", " ")
        score = sum(1 for token in tokens if token in name)
        if score:
            matches.append((float(score), str(p)))
    matches.sort(key=lambda x: (-x[0], x[1].lower()))
    return matches

