# rag/loader.py — one loader, both AI engines import from here
# SECURITY: Uses safe deserialization only — no pickle

import os, json, hashlib
import faiss
import numpy as np
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

DOC_DIR   = "doc"
FAISS_DIR = "storage/faiss_db"
MANIFEST  = os.path.join(FAISS_DIR, "manifest.json")

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Safety limits
MAX_FILE_SIZE_MB = 50
MAX_INDEX_SIZE_MB = 500
MAX_DOCUMENTS = 10000


def _hash(path):
    return hashlib.md5(open(path,"rb").read()).hexdigest()


def _safe_load_index(faiss_dir: str):
    """Load FAISS index using native faiss IO (no pickle)."""
    index_path = os.path.join(faiss_dir, "index.faiss")
    if not os.path.exists(index_path):
        return None, None, None

    # Load the FAISS index with native IO
    index = faiss.read_index(index_path)

    # Load metadata (docstore, id_map) from JSON instead of pickle
    docstore_path = os.path.join(faiss_dir, "docstore.json")
    idmap_path = os.path.join(faiss_dir, "id_map.json")

    docstore = {}
    id_map = []

    if os.path.exists(docstore_path):
        with open(docstore_path) as f:
            docstore = json.load(f)

    if os.path.exists(idmap_path):
        with open(idmap_path) as f:
            id_map = json.load(f)

    return index, docstore, id_map


def _safe_save_index(faiss_dir: str, index, docstore: dict, id_map: list):
    """Save FAISS index using native faiss IO (no pickle)."""
    os.makedirs(faiss_dir, exist_ok=True)

    # Save the FAISS index with native IO
    faiss.write_index(index, os.path.join(faiss_dir, "index.faiss"))

    # Save metadata as JSON
    with open(os.path.join(faiss_dir, "docstore.json"), "w") as f:
        json.dump(docstore, f, indent=2)

    with open(os.path.join(faiss_dir, "id_map.json"), "w") as f:
        json.dump(id_map, f, indent=2)


def _validate_file(path: str) -> bool:
    """Validate a file before indexing — size check, basic sanity."""
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        print(f"[RAG] SKIP {os.path.basename(path)}: too large ({size_mb:.0f}MB > {MAX_FILE_SIZE_MB}MB)")
        return False
    if size_mb == 0:
        return False
    return True


def load_or_build():
    os.makedirs(FAISS_DIR, exist_ok=True)
    manifest = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}

    pdfs = [f for f in os.listdir(DOC_DIR) if f.endswith(".pdf")] if os.path.exists(DOC_DIR) else []
    new_docs, updated = [], False

    for pdf in pdfs:
        path = os.path.join(DOC_DIR, pdf)
        h = _hash(path)

        # Validate file before indexing
        if not _validate_file(path):
            continue

        if manifest.get(pdf) == h:
            continue                        # already indexed

        try:
            pages = PyPDFLoader(path).load()
            chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(pages)
            new_docs.extend(chunks)
            manifest[pdf] = h
            updated = True
            print(f"[RAG] Indexed: {pdf}")
        except Exception as e:
            print(f"[RAG] Skipped {pdf}: {e}")

    if not new_docs and not os.path.exists(os.path.join(FAISS_DIR, "index.faiss")):
        return None

    # Load or create the vector store (safe deserialization only)
    index, docstore, id_map = _safe_load_index(FAISS_DIR)

    if index is not None and new_docs:
        # Add new documents
        from langchain_community.vectorstores import FAISS
        # We need to temporarily create a FAISS object to add documents
        # Then save using safe IO
        embeddings_list = [doc.metadata.get("embedding", None) for doc in new_docs]

        # Embed and add to index
        texts = [doc.page_content for doc in new_docs]
        metadatas = [doc.metadata for doc in new_docs]
        new_embeddings = embeddings.embed_documents(texts)

        if index.d == 0:
            # Empty index, create new
            index = faiss.IndexFlatL2(len(new_embeddings[0]))
            index.add(np.array(new_embeddings, dtype=np.float32))
        else:
            index.add(np.array(new_embeddings, dtype=np.float32))

        # Update docstore
        start_id = len(id_map)
        for i, (text, meta) in enumerate(zip(texts, metadatas)):
            doc_id = str(start_id + i)
            docstore[doc_id] = {"page_content": text, "metadata": meta}
            id_map.append(doc_id)

    elif index is None and new_docs:
        # Create new index
        texts = [doc.page_content for doc in new_docs]
        metadatas = [doc.metadata for doc in new_docs]
        new_embeddings = embeddings.embed_documents(texts)

        index = faiss.IndexFlatL2(len(new_embeddings[0]))
        index.add(np.array(new_embeddings, dtype=np.float32))

        docstore = {}
        id_map = []
        for i, (text, meta) in enumerate(zip(texts, metadatas)):
            doc_id = str(i)
            docstore[doc_id] = {"page_content": text, "metadata": meta}
            id_map.append(doc_id)

    # Check index size limit
    import os as _os
    estimated_mb = (index.ntotal * index.d * 4) / (1024 * 1024)  # float32
    if estimated_mb > MAX_INDEX_SIZE_MB:
        print(f"[RAG] WARNING: Index size {estimated_mb:.0f}MB exceeds limit {MAX_INDEX_SIZE_MB}MB")

    if updated or index is not None:
        _safe_save_index(FAISS_DIR, index, docstore, id_map)
        json.dump(manifest, open(MANIFEST, "w"), indent=2)

    return index


# Singleton — loaded once, shared by both Marin and
rag_db = load_or_build()
