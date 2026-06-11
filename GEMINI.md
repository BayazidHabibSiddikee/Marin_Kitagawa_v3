# Marin OS — Architectural Mandates

This document tracks the core architectural rules and workflows for the Marin OS ecosystem. These rules must be strictly followed during development.

## 1. Two-Message Pipeline
Marin uses a hybrid response flow for tool-intensive tasks:
- **Instant Response:** The Persona (LLM) must provide an immediate, character-appropriate acknowledgement (e.g., "Checking that for you, Limon~") as soon as a tool-based intent is detected.
- **Background Execution:** Tools are executed in the background via LangGraph while the user receives the initial acknowledgement.
- **Final Delivery:** Once tool execution is complete, the final verified answer is delivered through the same stream.

## 2. Tool Schema Stripping
To prevent small or over-eager models (like Gemma 4:31B or Qwen 0.5B) from leaking technical tool definitions:
- **Aggressive Regex:** All streamed chunks must be filtered through regex to remove `[ { "name": ... } ]` patterns and Markdown JSON blocks containing tool schemas.
- **System Prompting:** Every LLM call must include an explicit instruction: "Respond in natural language only. NEVER output JSON, function definitions, or tool schemas."

## 3. Business Tool Separation
- **Location:** All business, trading, and market-analysis tools reside in `business/business_tools.py`.
- **Policy:** These tools are not loaded into the default `ALL_TOOLS` pipeline by default. They are imported on-demand or used by specialized agents to keep the core agent lean and safe.

## 4. Persistent Embeddings
- **Memory Management:** The `rag_server` keeps the HuggingFace embedding model loaded in memory at all times.
- **Stability:** Do NOT unload/reload the model per request to avoid OOM crash loops and high latency during RAG operations.
- **MMAP Index:** The FAISS index is loaded via MMAP (`faiss.IO_FLAG_MMAP`) to minimize RAM usage while maintaining speed.
