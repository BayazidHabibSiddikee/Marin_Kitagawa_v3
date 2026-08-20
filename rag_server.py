# rag_server.py — Shared RAG server (port 5080)
#
# Supports two knowledge bases:
#   doc/   → books, documents  (PDF, DOCX, TXT, MD)
#   code/  → your source files (PY, C, CPP, H, MD)
#
# Both indexed into ONE FAISS index — source_type metadata lets you filter.
# File upload endpoints let Marin/ frontends accept files directly.
#
# pip install docx2txt   (for .docx support)

import asyncio
import ctypes
import gc
import json
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

try:
    import faiss
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ RAG dependencies not available")

try:
    import docx2txt
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("⚠️ docx2txt not installed — .docx skipped. Run: pip install docx2txt")


# ═══════════════════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════════════════
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DOC_DIR   = Path(BASE_DIR) / "doc"
CODE_DIR  = Path(BASE_DIR) / "code"
FAISS_DIR = Path(BASE_DIR) / "storage" / "faiss_db"

DOC_DIR.mkdir(exist_ok=True)
CODE_DIR.mkdir(exist_ok=True)
FAISS_DIR.mkdir(exist_ok=True)

DOC_EXTENSIONS  = {".pdf", ".docx", ".txt", ".md"}
CODE_EXTENSIONS = {".py", ".c", ".cpp", ".h", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE  —  persistent embeddings: loaded once, stay in memory
# ═══════════════════════════════════════════════════════════════════════════════
import contextlib
import hashlib

_LIBC = None
def _malloc_trim():
    """Release free memory from Python's allocator back to the OS."""
    global _LIBC
    if _LIBC is None:
        try:
            _LIBC = ctypes.CDLL("libc.so.6")
        except Exception:
            return
    with contextlib.suppress(Exception):
        _LIBC.malloc_trim(0)


def _compact(force=False):
    """gc.collect + malloc_trim to return memory to OS."""
    if force:
        gc.collect(2)
    else:
        gc.collect()
    _malloc_trim()


# Thread-count environment vars — limits PyTorch/NumPy thread pool overhead
os.environ.setdefault("OMP_NUM_THREADS",    "1")
os.environ.setdefault("MKL_NUM_THREADS",    "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


from config import EMBEDDING_MODEL


def _create_embedding_model():
    """Create embedding model — loaded once at startup, kept in memory."""
    from sentence_transformers import SentenceTransformer

    # TRULY OFFLINE: Use local cache path if in Docker
    LOCAL_CACHE = "/root/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    model_to_load = LOCAL_CACHE if os.path.exists(LOCAL_CACHE) else EMBEDDING_MODEL

    class DirectEmbedder:
        def __init__(self, model_name):
            print(f"🔄 Direct loading SentenceTransformer: {model_name}")
            # local_files_only prevents hanging on network requests if not cached
            is_local = os.path.exists(model_name)
            self.model = SentenceTransformer(model_name, device="cpu", local_files_only=not is_local)
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False)
            if hasattr(embeddings, "tolist"):
                return embeddings.tolist()
            return embeddings
        def embed_query(self, text: str) -> list[float]:
            embedding = self.model.encode([text], show_progress_bar=False)
            if len(embedding) > 0 and hasattr(embedding[0], "tolist"):
                return embedding[0].tolist()
            return embedding[0]

    class OllamaFallbackEmbedder:
        def __init__(self):
            print("🔄 Loading Ollama Fallback Embedder: nomic-embed-text")
            from langchain_ollama import OllamaEmbeddings

            import config
            self.model = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url=config.OLLAMA_BASE_URL
            )
            # Warm up to ensure it works
            self.model.embed_query("test")
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return self.model.embed_documents(texts)
        def embed_query(self, text: str) -> list[float]:
            return self.model.embed_query(text)

    try:
        return DirectEmbedder(model_to_load)
    except Exception as e:
        print(f"⚠️ Direct model load failed: {e}. Attempting fallback...")
        try:
            return DirectEmbedder(EMBEDDING_MODEL)
        except Exception as e2:
            print(f"⚠️ Critical: Direct embedding model load failed: {e2}. Attempting Ollama Fallback...")
            try:
                return OllamaFallbackEmbedder()
            except Exception as e3:
                print(f"❌ Critical: Ollama fallback also failed: {e3}")
                return None


def _file_checksum(path: Path) -> str:
    """SHA256 of file content for change detection."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return ""


class KnowledgeBase:
    """
    Unified FAISS index over doc/ and code/.
    Embeddings loaded once at startup and kept in memory.
    File changes detected via checksums — only changed files re-indexed.
    """

    MANIFEST_PATH   = FAISS_DIR / "manifest.json"
    CHECKSUMS_PATH  = FAISS_DIR / "checksums.json"
    DOC_CHUNK_SIZE  = 450
    DOC_OVERLAP     = 30
    CODE_CHUNK_SIZE = 300
    CODE_OVERLAP    = 40

    def __init__(self):
        self._raw_index = None
        self._docstore  = None
        self._id_map    = None
        self.manifest: dict[str, Any] = {"indexed": [], "failed": []}
        self.checksums: dict[str, str] = {}   # filename → checksum
        self._lc_vectorstore = None
        self._embeddings = None
        self._boot()

    # ── Startup ───────────────────────────────────────────────────────────────
    def _boot(self):
        if not FAISS_AVAILABLE:
            print("⚠️ FAISS not available — RAG disabled")
            return

        # Load embeddings ONCE — they stay in memory for all searches
        print("🔄 Loading embedding model...")
        self._embeddings = _create_embedding_model()
        if self._embeddings is None:
            print("❌ KB boot failed: Embedding model not available")
            return
        print("✅ Embedding model loaded and ready")

        self._load_manifest()
        self._load_checksums()
        index_file = FAISS_DIR / "index.faiss"
        pkl_file   = FAISS_DIR / "index.pkl"
        docstore_json = FAISS_DIR / "docstore.json"
        idmap_json    = FAISS_DIR / "id_map.json"

        # SECURITY: Prefer JSON-based safe loading over pickle
        if index_file.exists() and docstore_json.exists():
            try:
                self._raw_index = faiss.read_index(
                    str(index_file), faiss.IO_FLAG_MMAP
                )
                with open(docstore_json) as f:
                    self._docstore = json.load(f)
                with open(idmap_json) as f:
                    self._id_map = json.load(f)
                n = len(self.manifest["indexed"])
                print(f"✅ KB loaded (safe JSON): {n} files, {self._raw_index.ntotal} vectors")

                # Dimension check
                test_dim = len(self._embeddings.embed_query("test"))
                if test_dim != self._raw_index.d:
                    print(f"⚠️ Embedding dimension mismatch ({test_dim} != {self._raw_index.d}). Rebuilding index...")
                    raise ValueError("Dimension mismatch")
            except Exception as e:
                print(f"⚠️ safe load failed ({e}) — falling back to rebuild")
                self._raw_index = None
                self._docstore  = None
                self._id_map    = None
        elif index_file.exists() and pkl_file.exists():
            print("⚠️ Legacy pickle index found but loading is disabled for security.")
            print("⚠️ Please delete index.pkl and run /reindex to rebuild.")
            self._raw_index = None
            self._docstore  = None
            self._id_map    = None
        else:
            # First boot — build from scratch
            self._index_new_files()
            _compact(force=True)
            return

        # Index any new/changed files (embeddings already loaded)
        self._index_changed_files()
        _compact(force=True)

    def _unload_embeddings(self):
        """Release the embedding model to free PyTorch RAM."""
        if self._embeddings is not None:
            with contextlib.suppress(Exception):
                del self._embeddings
            self._embeddings = None
        _compact(force=True)

    # ── Manifest ──────────────────────────────────────────────────────────────
    def _load_manifest(self):
        if self.MANIFEST_PATH.exists():
            try:
                with open(self.MANIFEST_PATH) as f:
                    self.manifest = json.load(f)
                self.manifest.setdefault("indexed", [])
                self.manifest.setdefault("failed",  [])
            except Exception:
                self.manifest = {"indexed": [], "failed": []}

    def _save_manifest(self):
        with open(self.MANIFEST_PATH, "w") as f:
            json.dump(self.manifest, f, indent=2)

    # ── Checksums ────────────────────────────────────────────────────────────
    def _load_checksums(self):
        if self.CHECKSUMS_PATH.exists():
            try:
                with open(self.CHECKSUMS_PATH) as f:
                    self.checksums = json.load(f)
            except Exception:
                self.checksums = {}

    def _save_checksums(self):
        with open(self.CHECKSUMS_PATH, "w") as f:
            json.dump(self.checksums, f, indent=2)

    # ── File discovery ────────────────────────────────────────────────────────
    def _all_files(self) -> list[Path]:
        files = []
        # Recursive glob search for all documents and code
        for ext in DOC_EXTENSIONS:
            files.extend(DOC_DIR.rglob(f"*{ext}"))
        for ext in CODE_EXTENSIONS:
            files.extend(CODE_DIR.rglob(f"*{ext}"))
        return sorted(set(files))

    def _index_new_files(self):
        already_indexed = set(self.manifest["indexed"])
        already_failed  = {e["file"] for e in self.manifest["failed"]}
        new_files = [
            f for f in self._all_files()
            if f.name not in already_indexed and f.name not in already_failed
        ]
        if not new_files:
            return
        print(f"📚 Indexing {len(new_files)} new file(s)...")
        for path in new_files:
            self._index_single_file(path)
            self.checksums[path.name] = _file_checksum(path)
        self._save_faiss()
        self._save_manifest()
        self._save_checksums()
        _compact()
        print(f"✅ Done: {len(self.manifest['indexed'])} total indexed")

    def _index_changed_files(self):
        """Check for new or modified files and re-index only those."""
        all_files = self._all_files()
        new_files = []
        changed_files = []

        for path in all_files:
            name = path.name
            current_sum = _file_checksum(path)
            old_sum = self.checksums.get(name, "")

            if name not in self.manifest["indexed"] and name not in {e["file"] for e in self.manifest["failed"]}:
                new_files.append(path)
            elif current_sum != old_sum and current_sum:
                changed_files.append(path)

        if not new_files and not changed_files:
            print("✅ No new or changed files to index")
            return

        if new_files:
            print(f"📚 Indexing {len(new_files)} new file(s)...")
        if changed_files:
            print(f"🔄 Re-indexing {len(changed_files)} changed file(s)...")

        for path in new_files + changed_files:
            name = path.name
            # Remove old entries if re-indexing changed file
            if name in self.manifest["indexed"]:
                self.manifest["indexed"].remove(name)
            self.manifest["failed"] = [e for e in self.manifest["failed"] if e["file"] != name]
            self._index_single_file(path)
            self.checksums[name] = _file_checksum(path)

        self._save_faiss()
        self._save_manifest()
        self._save_checksums()
        _compact()
        print(f"✅ Index updated: {len(self.manifest['indexed'])} total indexed")

    def _save_faiss(self):
        """Save the raw FAISS index + docstore to disk, then reload mmap."""
        if self._lc_vectorstore is None:
            return

        # Write the raw index directly (LC save_local fails on mmap'd indexes)
        index_file = FAISS_DIR / "index.faiss"
        live_index = self._lc_vectorstore.index
        # Clone to a writable (non-mmap) index before writing
        try:
            writable = faiss.deserialize_index(faiss.serialize_index(live_index))
            faiss.write_index(writable, str(index_file))
        except Exception as e:
            print(f"⚠️ FAISS write failed: {e}")
            return

        # Sync raw pointers from LC wrapper
        self._raw_index = live_index
        self._docstore  = self._lc_vectorstore.docstore
        self._id_map    = self._lc_vectorstore.index_to_docstore_id

        # SECURITY: Save docstore as JSON instead of pickle
        docstore_json = FAISS_DIR / "docstore.json"
        idmap_json    = FAISS_DIR / "id_map.json"
        try:
            # Convert docstore to JSON-serializable format
            docstore_data = {}
            for k, v in self._docstore.items():
                if hasattr(v, "page_content"):
                    docstore_data[k] = {
                        "page_content": v.page_content,
                        "metadata": v.metadata,
                    }
                else:
                    docstore_data[k] = v
            with open(docstore_json, "w") as f:
                json.dump(docstore_data, f, indent=2)

            # Convert id_map to JSON
            id_map_data = list(self._id_map) if hasattr(self._id_map, '__iter__') else self._id_map
            with open(idmap_json, "w") as f:
                json.dump(id_map_data, f, indent=2)
        except Exception as e:
            print(f"⚠️ JSON save failed: {e}")

        # Reload raw index with mmap (discards LC wrapper's in-RAM copy)
        index_file = FAISS_DIR / "index.faiss"
        if index_file.exists():
            try:
                self._raw_index = faiss.read_index(str(index_file), faiss.IO_FLAG_MMAP)
                # Load from JSON (safe)
                if docstore_json.exists():
                    with open(docstore_json) as f:
                        self._docstore = json.load(f)
                if idmap_json.exists():
                    with open(idmap_json) as f:
                        self._id_map = json.load(f)
            except Exception as e:
                print(f"⚠️ mmap reload failed: {e}")

    # ── Build index using LangChain wrapper (easiest path for chunk→embed) ───
    def _ensure_lc_store(self):
        if self._lc_vectorstore is not None:
            return
        if self._raw_index is not None and self._docstore is not None and self._id_map is not None:
            from langchain_community.vectorstores import FAISS as LC_FAISS
            self._lc_vectorstore = LC_FAISS(
                self._raw_index,
                self._docstore,
                self._id_map,
                self._embeddings,
            )
        else:
            self._lc_vectorstore = None

    # ── Loaders ───────────────────────────────────────────────────────────────
    def _load_file(self, path: Path) -> list[Document]:
        ext         = path.suffix.lower()
        name        = path.name
        source_type = "code" if path.parent.resolve() == CODE_DIR.resolve() else "doc"

        if ext == ".pdf":
            docs = PyPDFLoader(str(path)).load()
            for d in docs:
                d.metadata.update({"source_file": name, "source_type": "doc", "language": "text"})
            return docs

        if ext == ".docx":
            if not DOCX_AVAILABLE:
                raise ImportError("docx2txt not installed — run: pip install docx2txt")
            text = docx2txt.process(str(path))
            return [Document(page_content=text,
                             metadata={"source_file": name, "source_type": "doc",
                                       "language": "text", "page": 0})]

        if ext == ".txt":
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [Document(page_content=text,
                             metadata={"source_file": name, "source_type": source_type,
                                       "language": "text", "page": 0})]

        if ext == ".md":
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [Document(page_content=text,
                             metadata={"source_file": name, "source_type": source_type,
                                       "language": "markdown", "page": 0})]

        if ext == ".py":
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [Document(page_content=text,
                             metadata={"source_file": name, "source_type": "code",
                                       "language": "python", "page": 0})]

        if ext in {".c", ".cpp", ".h"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            lang = {"c": "c", ".cpp": "cpp", ".h": "c"}.get(ext, "c")
            return [Document(page_content=text,
                             metadata={"source_file": name, "source_type": "code",
                                       "language": lang, "page": 0})]

        raise ValueError(f"Unsupported extension: {ext}")

    def _get_splitter(self, path: Path) -> RecursiveCharacterTextSplitter:
        if path.suffix.lower() in {".py", ".c", ".cpp", ".h"}:
            return RecursiveCharacterTextSplitter(
                chunk_size=self.CODE_CHUNK_SIZE,
                chunk_overlap=self.CODE_OVERLAP,
                separators=["\n\nclass ", "\n\ndef ", "\n\n", "\n", " ", ""],
            )
        return RecursiveCharacterTextSplitter(
            chunk_size=self.DOC_CHUNK_SIZE,
            chunk_overlap=self.DOC_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ── Core indexer ──────────────────────────────────────────────────────────
    def _index_single_file(self, path: Path):
        name = path.name
        try:
            documents = self._load_file(path)
            if not documents:
                raise ValueError("File produced zero content")

            splitter = self._get_splitter(path)
            chunks   = splitter.split_documents(documents)

            valid = []
            for c in chunks:
                if not isinstance(c.page_content, str):
                    continue
                clean = c.page_content.strip()
                if len(clean) > 10 and any(ch.isalnum() for ch in clean):
                    c.page_content = clean
                    valid.append(c)

            if not valid:
                raise ValueError("No valid chunks after filtering")

            if self._lc_vectorstore is None:
                from langchain_community.vectorstores import FAISS as LC_FAISS
                self._lc_vectorstore = LC_FAISS.from_documents(valid, self._embeddings)
            else:
                try:
                    self._lc_vectorstore.add_documents(valid)
                except Exception as e:
                    print(f"  [!] Partial embed error for {name}: {e}")

            self.manifest["indexed"].append(name)
            src = path.parent.name
            print(f"  ✓ [{src}] {name}: {len(valid)} chunks")

        except Exception as e:
            self.manifest["failed"].append({"file": name, "reason": str(e)})
            print(f"  ✗ {name}: SKIPPED — {e}")

        finally:
            with contextlib.suppress(Exception):
                del documents, chunks, valid
            _compact()

    # ── Public API ────────────────────────────────────────────────────────────
    def search(self, query: str, k: int = 10,
               source_type: str | None = None) -> list[dict[str, Any]]:
        if self._raw_index is None or self._embeddings is None:
            return []
        try:
            # Embed the query
            q_vec = self._embeddings.embed_query(query)
            import numpy as np
            q_np = np.array([q_vec], dtype=np.float32)
            # Search using raw FAISS index (mmap'd, no RAM load)
            scores, idxs = self._raw_index.search(q_np, k * 3 if source_type else k)
            results = []
            for _score, idx in zip(scores[0], idxs[0], strict=False):
                if idx < 0:
                    continue
                doc_id  = self._id_map.get(int(idx))
                if doc_id is None:
                    continue
                doc = self._docstore.get(doc_id) if isinstance(self._docstore, dict) else self._docstore.search(doc_id)
                if doc is None:
                    continue
                if isinstance(doc, dict):
                    page_content = doc.get("page_content", "")
                    meta = doc.get("metadata", {})
                else:
                    page_content = doc.page_content
                    meta = doc.metadata
                if source_type and meta.get("source_type") != source_type:
                    continue
                results.append({
                    "content":     page_content,
                    "source":      meta.get("source_file") or meta.get("source", "Unknown"),
                    "source_type": meta.get("source_type", "doc"),
                    "language":    meta.get("language",    "text"),
                    "page":        meta.get("page",        0),
                })
                if len(results) >= k:
                    break
            return results
        except Exception as e:
            print(f"⚠️ Search error: {e}")
            return []

    def get_context(self, query: str, k: int = 10,
                    source_type: str | None = None) -> str:
        results = self.search(query, k=k, source_type=source_type)
        if not results:
            return ""

        by_source: dict[str, list[dict]] = {}
        for r in results:
            by_source.setdefault(r["source"], []).append(r)

        parts = ["[KNOWLEDGE FROM YOUR BOOKS & CODE]\n"]
        for source, chunks in list(by_source.items())[:5]:
            stype = chunks[0]["source_type"]
            lang  = chunks[0]["language"]
            icon  = "💻" if stype == "code" else "📖"
            parts.append(f"\n{icon} From {source}:")
            for chunk in chunks[:3]:
                if stype == "code":
                    parts.append(f"```{lang}\n{chunk['content'][:600]}\n```")
                else:
                    parts.append(chunk["content"][:600])
        return "\n".join(parts)

    def add_file(self, path: Path) -> dict[str, Any]:
        name = path.name
        if name in self.manifest["indexed"]:
            self.manifest["indexed"].remove(name)
        self.manifest["failed"] = [e for e in self.manifest["failed"] if e["file"] != name]

        self._ensure_lc_store()
        self._index_single_file(path)
        self._save_faiss()
        self._save_manifest()
        self.checksums[name] = _file_checksum(path)
        self._save_checksums()

        success = name in self.manifest["indexed"]
        return {
            "ok":      success,
            "message": f"Indexed {name}" if success else "Failed: see /report",
        }

    def get_report(self) -> dict[str, Any]:
        return {
            "total":   len(self.manifest["indexed"]),
            "indexed": self.manifest["indexed"],
            "failed":  self.manifest["failed"],
        }


# Global instance
kb = KnowledgeBase()


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI
# ═══════════════════════════════════════════════════════════════════════════════
app = FastAPI(title="RAG Server", version="2.0")




class EmbedRequest(BaseModel):
    texts: list[str]

@app.post("/embed")
async def embed_texts(req: EmbedRequest):
    if kb._embeddings is None:
        raise HTTPException(503, "Embeddings not loaded")

    def _embed():
        return kb._embeddings.embed_documents(req.texts)

    vecs = await asyncio.to_thread(_embed)
    return {"embeddings": vecs}


class SearchRequest(BaseModel):
    query:       str
    k:           int = 10
    source_type: str | None = None  # "doc" | "code" | None = search everything


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search")
async def search(req: SearchRequest):
    results = await asyncio.to_thread(kb.search, req.query, min(req.k, 20), req.source_type)
    return {"results": results, "count": len(results)}


@app.post("/context")
async def context(req: SearchRequest):
    ctx = await asyncio.to_thread(kb.get_context, req.query, min(req.k, 20), req.source_type)
    return {"context": ctx}


# ── Upload ────────────────────────────────────────────────────────────────────

@app.post("/upload/doc")
async def upload_doc(file: UploadFile = File(...)):
    """Upload PDF, DOCX, TXT, or MD into doc/ and index immediately."""
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    ext = Path(file.filename).suffix.lower()
    if ext not in DOC_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type '{ext}'. Allowed: {DOC_EXTENSIONS}")
    dest = DOC_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    result = await asyncio.to_thread(kb.add_file, dest)
    return {"filename": file.filename, **result}


@app.post("/upload/code")
async def upload_code(file: UploadFile = File(...)):
    """Upload PY, C, CPP, H, or MD into code/ and index immediately."""
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    ext = Path(file.filename).suffix.lower()
    if ext not in CODE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type '{ext}'. Allowed: {CODE_EXTENSIONS}")
    dest = CODE_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    result = await asyncio.to_thread(kb.add_file, dest)
    return {"filename": file.filename, **result}


@app.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """Upload image into static/uploads/ for vision tasks. Not RAG-indexed."""
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type '{ext}'. Allowed: {IMAGE_EXTENSIONS}")
    upload_dir = Path(BASE_DIR) / "static" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "filename": file.filename, "url": f"/static/uploads/{file.filename}"}


# ── Info ──────────────────────────────────────────────────────────────────────


@app.get("/debug_kb")
async def debug_kb():
    return {
        "kb_is_none": kb is None,
        "embeddings_is_none": kb._embeddings is None if kb else True
    }

@app.get("/report")
async def report():
    return kb.get_report()


@app.get("/health")
async def health():
    index_loaded = kb._raw_index is not None
    embeddings_loaded = kb._embeddings is not None
    return {
        "status":            "operational",
        "port":              5080,
        "total":             len(kb.manifest["indexed"]),
        "ready":             index_loaded,
        "index_loaded":      index_loaded,
        "embeddings_loaded": embeddings_loaded,
        "doc_dir":           str(DOC_DIR),
        "code_dir":          str(CODE_DIR),
    }


@app.post("/reindex")
async def reindex():
    """Manually trigger re-indexing of all files (new + changed)."""
    await asyncio.to_thread(kb._index_changed_files)
    return {
        "ok":      True,
        "total":   len(kb.manifest["indexed"]),
        "indexed": kb.manifest["indexed"],
    }


@app.get("/unload")
async def unload_embeddings():
    """Release embedding model from memory to free RAM."""
    kb._unload_embeddings()
    return {"ok": True, "message": "Embeddings unloaded from memory"}


@app.get("/reload")
async def reload_embeddings():
    """Reload embedding model into memory."""
    if kb._embeddings is None:
        kb._embeddings = _create_embedding_model()
        return {"ok": True, "message": "Embeddings reloaded"}
    return {"ok": True, "message": "Embeddings already loaded"}


if __name__ == "__main__":
    import argparse
    import resource
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5080)
    parser.add_argument("--max-memory-mb", type=int, default=0,
                        help="Hard RSS limit in MB (0 to disable)")
    args = parser.parse_args()

    if args.max_memory_mb > 0:
        limit = args.max_memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            print(f"🧠 Memory limit set to {args.max_memory_mb} MB (RLIMIT_AS)")
        except Exception as e:
            print(f"⚠️ Could not set memory limit: {e}")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port, reload=False)
