# Marin OS — Master Plan
## A Tool-First AI Operating System by Bayazid & Marin

---

# PART 1: CURRENT STATE

## What Exists Today

### Core Infrastructure
- **Docker deployment** — Bridge networking, 4G/4CPU limits, supervisord process management
- **Authentication** — API key + Google OAuth, user roles (Owner/Trusted/Guest)
- **Database** — SQLite with users, chat_history, vault, todos tables
- **RAG Server** — PDF/document ingestion and retrieval
- **Moduleflow** — Multi-agent workflow engine
- **LangGraph Agent** — 4-node cognitive architecture (research → plan → execute → reflect)

### Tools (The Heart of Marin)

| Category | Tool | Status | Purpose |
|----------|------|--------|---------|
| **PDF** | `pdf.py` | ✅ Built | Merge, split, extract text, convert to images |
| **PDF** | `pdf_downloader.py` | ✅ Built | Download PDFs from URLs |
| **PDF** | `pdf_downloader_marin.py` | ✅ Built | Enhanced PDF downloader with search |
| **Office** | `office_tools.py` | ✅ Built | PDF↔Word, PDF↔Excel, PDF↔PPTX, CSV↔XLSX |
| **Office** | `doc_tools.py` | ✅ Built | Word→PDF (mammoth), PDF→Word (pdf2docx) |
| **YouTube** | `youtube_transcript.py` | ✅ Built | Extract transcripts from YouTube videos |
| **Knowledge** | `knowledge_hub.py` | ✅ Built | Weather, maps, flood data, web search, PDF search |
| **Student** | `student_tools.py` | ✅ Built | QR generator, unit converter, calculator, notes |
| **Finance** | `auto_trader.py` | ✅ Built | Binance API (balance, orders, market orders) |
| **Finance** | `stock_data.py` | ✅ Built | Yahoo Finance wrapper |
| **Finance** | `crypto_data.py` | ✅ Built | CoinGecko price data |
| **Finance** | `portfolio_tracker.py` | ✅ Built | Portfolio analysis |
| **News** | `news_harvester.py` | ✅ Built | 15 RSS sources, async fetch |
| **Docker** | `docker_orchestrator.py` | ✅ Built | Container management |
| **Utility** | `translate.py` | ✅ Built | Translation |
| **Utility** | `maps.py` | ✅ Built | Mapping |
| **Utility** | `bangla.py` | ✅ Built | Bangla language tools |

### SwordFish Interface (The Browser)
- **Location**: `/SwordFish/` directory
- **Main file**: `src/tools.html` — The tools dashboard
- **Features**: PDF tools, office converters, YouTube transcript, knowledge hub
- **Style**: `src/styles.py` — UI styling
- **Ad blocker**: `utils/adblocker.py`
- **Proxy tools**: `utils/proxy_tools.py`

---

# PART 2: THE VISION — TOOLS FIRST

## Philosophy
> "AI makes tools 10x better, but tools are the foundation."

Marin is NOT primarily an AI assistant. Marin is a **tool engine** that uses AI to make tools smarter, faster, and more accurate than manual use.

### What Makes Marin Special
1. **PDF Intelligence** — Not just download, but understand, extract, convert, search
2. **Dynamic Learning** — If user wants to learn Numerics, Marin downloads books and studies
3. **Document Conversion** — PDF↔Word, PDF↔Excel, PDF↔PPTX, all seamless
4. **YouTube Intelligence** — Download videos OR extract transcripts for learning
5. **Knowledge Hub** — Weather, maps, places, floods, routes — all integrated
6. **Student Tools** — Calculator, unit converter, QR generator, notes

### The 10x Multiplier
| Manual Task | Marin Tool | AI Enhancement |
|-------------|-----------|----------------|
| Download PDF | `pdf_downloader.py` | Auto-extract key info |
| Convert PDF to Excel | `office_tools.py` | AI identifies tables |
| Get YouTube transcript | `youtube_transcript.py` | AI summarizes content |
| Search for books | `knowledge_hub.py` | AI recommends based on level |
| Study a topic | Dynamic RAG | AI creates study plan |

---

# PART 3: TOOLS TO BUILD

## Priority 1: YouTube Tools (Week 1-2)

### 3.1 yt_dlp Video Downloader
**Location**: `tools/youtube_downloader.py`

```python
# Features needed:
- Download video (mp4, mkv, webm)
- Download audio only (mp3, m4a, opus)
- Select quality (144p to 4K)
- Playlist support
- Subtitle download
- Thumbnail download
- Progress tracking
- Resume interrupted downloads
```

**Dependencies**: `yt-dlp` (Python package)

**API Design**:
```python
def download_video(url: str, quality: str = "best", output_dir: str = "downloads") -> dict
def download_audio(url: str, format: str = "mp3", output_dir: str = "downloads") -> dict
def get_video_info(url: str) -> dict  # title, duration, qualities available
def download_playlist(url: str, quality: str = "best") -> dict
```

### 3.2 YouTube Transcript Enhanced
**Location**: `tools/youtube_transcript.py` (enhance existing)

```python
# Features to add:
- Multi-language support
- Timestamp-based extraction
- Summary generation
- Key points extraction
- Quiz generation from transcript
- Study notes creation
```

### 3.3 YouTube + PDF Workflow
**Location**: `tools/youtube_workflow.py`

```python
# Workflow: Video → Transcript → Study Material
def video_to_notes(url: str) -> dict:
    """Download transcript, summarize, create study notes as PDF"""
    
def video_to_quiz(url: str) -> dict:
    """Extract transcript, generate quiz questions"""
    
def video_to_flashcards(url: str) -> dict:
    """Create flashcard PDF from video content"""
```

## Priority 2: Dynamic Learning RAG (Week 2-3)

### 3.4 Smart Book Downloader
**Location**: `tools/book_downloader.py`

```python
# Features:
- Search for books by topic
- Find free/public domain books (Project Gutenberg, Open Library)
- Download PDF/EPUB
- Auto-add to RAG index
- Track reading progress

def search_books(topic: str, level: str = "beginner") -> list
def download_book(book_url: str) -> str  # returns local path
def auto_index_book(book_path: str) -> bool  # add to RAG
```

### 3.5 Dynamic Study Engine
**Location**: `tools/study_engine.py`

```python
# When user says "I want to learn Numerics"
def create_study_plan(topic: str) -> dict:
    """1. Search for relevant books
       2. Download top 3
       3. Index in RAG
       4. Create chapter-by-chapter study plan
       5. Generate quiz from content
    """
    
def study_chapter(topic: str, chapter: int) -> dict:
    """Extract chapter content, explain with AI, create exercises"""
    
def test_knowledge(topic: str) -> dict:
    """Generate quiz from indexed books, grade answers"""
```

### 3.6 Book-to-Excel Converter
**Location**: `tools/book_converter.py`

```python
# Convert book content to structured Excel
def book_to_excel(book_path: str) -> str:
    """Extract chapters, sections, key terms → Excel with:
       Sheet 1: Table of Contents
       Sheet 2: Key Terms (term, definition, page)
       Sheet 3: Chapter Summaries
       Sheet 4: Quiz Questions
    """

def pdf_tables_to_excel(pdf_path: str) -> str:
    """Smart table extraction with AI validation"""
```

## Priority 3: Enhanced Office Tools (Week 3-4)

### 3.7 Smart PDF Analyzer
**Location**: `tools/pdf_analyzer.py`

```python
def analyze_pdf(pdf_path: str) -> dict:
    """AI-powered PDF analysis:
       - Detect if it's a textbook, paper, form, invoice
       - Extract structure (chapters, sections, headings)
       - Identify tables and figures
       - Generate summary
       - Create study guide if educational
    """

def extract_tables_smart(pdf_path: str) -> list:
    """AI-enhanced table extraction with validation"""

def pdf_to_markdown(pdf_path: str) -> str:
    """Convert PDF to clean Markdown preserving structure"""
```

### 3.8 Batch Converter
**Location**: `tools/batch_converter.py`

```python
def batch_convert(input_dir: str, from_format: str, to_format: str) -> list:
    """Convert all files in directory:
       PDF → Excel, Word → PDF, etc.
    """

def batch_compress(pdf_dir: str) -> list:
    """Compress all PDFs in directory"""
```

## Priority 4: Knowledge Hub Expansion (Week 4-5)

### 3.9 Research Paper Tool
**Location**: `tools/research_paper.py`

```python
def search_papers(topic: str) -> list:
    """Search arXiv, Google Scholar, Semantic Scholar"""
    
def download_paper(paper_url: str) -> str:
    """Download PDF, index in RAG"""
    
def summarize_paper(pdf_path: str) -> dict:
    """AI summary: abstract, methods, results, key findings"""
```

### 3.10 Document Q&A
**Location**: `tools/document_qa.py`

```python
def ask_document(pdf_path: str, question: str) -> str:
    """Chat with any PDF document"""
    
def compare_documents(pdf1: str, pdf2: str) -> dict:
    """Compare two documents, find similarities/differences"""
```

---

# PART 4: SWORDFISH INTERFACE

## Current State
- `src/tools.html` — Basic tools dashboard
- `src/styles.py` — UI styling

## Planned Interface

### Free Tier (SwordFish Basic)
```
┌─────────────────────────────────────────────────────────┐
│  SWORDFISH                              [Login] [Guest] │
├─────────────────────────────────────────────────────────┤
│  📚 PDF Tools                                           │
│  ├─ Download PDF    ─┐                                  │
│  ├─ Merge PDF       ─┼─ All Free                        │
│  ├─ Split PDF       ─┤                                  │
│  ├─ PDF → Excel     ─┘                                  │
│  │                                                       │
│  🎬 YouTube Tools                                       │
│  ├─ Get Transcript  ─┐                                  │
│  ├─ Download Video  ─┼─ 5/day free                      │
│  └─ Video → Notes   ─┘                                  │
│  │                                                       │
│  🔢 Student Tools                                        │
│  ├─ Calculator      ─┐                                  │
│  ├─ Unit Converter  ─┼─ All Free                        │
│  ├─ QR Generator    ─┤                                  │
│  └─ Notes           ─┘                                  │
│  │                                                       │
│  🌍 Knowledge Hub                                        │
│  ├─ Web Search      ─┐                                  │
│  ├─ Weather         ─┼─ 10/day free                     │
│  └─ Places          ─┘                                  │
└─────────────────────────────────────────────────────────┘
```

### Premium Tier (SwordFish Pro)
```
┌─────────────────────────────────────────────────────────┐
│  SWORDFISH PRO                          ⭐ $10/month    │
├─────────────────────────────────────────────────────────┤
│  📚 Advanced PDF Tools                                  │
│  ├─ Smart PDF Analyzer (AI-powered)                     │
│  ├─ Batch Conversion                                    │
│  ├─ PDF Q&A (Chat with any PDF)                         │
│  └─ Document Comparison                                 │
│  │                                                       │
│  🎬 YouTube Pro                                         │
│  ├─ Unlimited Downloads                                 │
│  ├─ Playlist Download                                   │
│  ├─ Video → Study Notes (AI)                            │
│  └─ Quiz Generation                                     │
│  │                                                       │
│  📖 Dynamic Learning                                     │
│  ├─ Auto Book Download                                  │
│  ├─ Smart Study Plans                                   │
│  ├─ Knowledge Testing                                   │
│  └─ Progress Tracking                                   │
│  │                                                       │
│  💰 Finance Tools                                        │
│  ├─ Portfolio Tracker                                   │
│  ├─ Market Analysis                                     │
│  └─ Trade Execution                                     │
│  │                                                       │
│  🔧 System Tools                                         │
│  ├─ Docker Management                                   │
│  ├─ File Management                                     │
│  └─ Automation Scripts                                  │
└─────────────────────────────────────────────────────────┘
```

---

# PART 5: BUSINESS MODEL

## Revenue Streams

### 1. SwordFish Pro Subscription
- **Price**: $10/month or $100/year
- **Includes**: Unlimited YouTube, AI PDF tools, Dynamic Learning, Finance tools
- **Target**: Students, researchers, freelancers

### 2. API Access
- **Price**: $0.01 per API call
- **For**: Developers integrating Marin tools into their apps
- **Includes**: All tool APIs (PDF, YouTube, etc.)

### 3. Enterprise License
- **Price**: Custom pricing
- **For**: Companies needing on-premise deployment
- **Includes**: Full source code, customization support

## Cost Structure
- **Infrastructure**: $50/month (VPS + Docker)
- **API Costs**: ~$20/month (OpenRouter free tier + local Ollama)
- **Domain/SSL**: $15/year
- **Total Fixed**: ~$75/month

## Break-Even Analysis
- Need 8 Pro subscribers to break even
- Target: 50 subscribers in 6 months = $500/month revenue
- Year 1 goal: 200 subscribers = $2,000/month

---

# PART 6: EXECUTION PLAN

## Phase 1: Foundation (Weeks 1-2)
### Week 1: YouTube Tools
- [ ] Install `yt-dlp` package
- [ ] Build `tools/youtube_downloader.py`
- [ ] Integrate with SwordFish interface
- [ ] Add to main.py API routes
- [ ] Test download quality options

### Week 2: Transcript Enhancement
- [ ] Enhance `youtube_transcript.py`
- [ ] Add multi-language support
- [ ] Build summary generation
- [ ] Create quiz generation
- [ ] Add to SwordFish interface

## Phase 2: Learning Engine (Weeks 3-4)
### Week 3: Book Downloader
- [ ] Build `tools/book_downloader.py`
- [ ] Integrate Project Gutenberg API
- [ ] Add Open Library search
- [ ] Auto-index to RAG
- [ ] Create reading tracker

### Week 4: Study Engine
- [ ] Build `tools/study_engine.py`
- [ ] Create study plan generator
- [ ] Build chapter extractor
- [ ] Add knowledge testing
- [ ] Integrate with AI summaries

## Phase 3: Smart Tools (Weeks 5-6)
### Week 5: PDF Analyzer
- [ ] Build `tools/pdf_analyzer.py`
- [ ] Add AI-powered structure detection
- [ ] Create table extraction
- [ ] Build PDF → Markdown converter
- [ ] Add batch processing

### Week 6: Document Q&A
- [ ] Build `tools/document_qa.py`
- [ ] Add document comparison
- [ ] Create citation finder
- [ ] Build research paper tools
- [ ] Integrate with RAG

## Phase 4: Interface & Launch (Weeks 7-8)
### Week 7: SwordFish Upgrade
- [ ] Redesign `src/tools.html`
- [ ] Add premium tier UI
- [ ] Build payment integration
- [ ] Create user dashboard
- [ ] Add usage tracking

### Week 8: Launch Prep
- [ ] Security audit
- [ ] Performance testing
- [ ] Documentation
- [ ] Beta testing
- [ ] Launch announcement

---

# PART 7: TECHNICAL ARCHITECTURE

## Directory Structure (Final)
```
marin/
├── tools/
│   ├── pdf.py                    # PDF merge, split, extract
│   ├── pdf_downloader.py         # Download PDFs from URLs
│   ├── pdf_downloader_marin.py   # Enhanced PDF downloader
│   ├── pdf_analyzer.py           # AI PDF analysis (NEW)
│   ├── office_tools.py           # Office format converters
│   ├── doc_tools.py              # Word↔PDF converters
│   ├── youtube_downloader.py     # yt-dlp wrapper (NEW)
│   ├── youtube_transcript.py     # Transcript extraction
│   ├── youtube_workflow.py       # Video→Notes/Quiz (NEW)
│   ├── book_downloader.py        # Book search/download (NEW)
│   ├── book_converter.py         # Book→Excel (NEW)
│   ├── study_engine.py           # Dynamic learning (NEW)
│   ├── document_qa.py            # Chat with PDFs (NEW)
│   ├── research_paper.py         # Paper search/download (NEW)
│   ├── batch_converter.py        # Batch file conversion (NEW)
│   ├── knowledge_hub.py          # Weather, maps, search
│   ├── student_tools.py          # Calculator, QR, notes
│   ├── auto_trader.py            # Binance trading
│   ├── stock_data.py             # Yahoo Finance
│   ├── crypto_data.py            # CoinGecko
│   ├── portfolio_tracker.py      # Portfolio analysis
│   ├── news_harvester.py         # RSS news fetcher
│   └── docker_orchestrator.py    # Docker management
│
├── SwordFish/
│   ├── src/
│   │   ├── tools.html            # Main tools dashboard
│   │   ├── tools_pro.html        # Premium dashboard (NEW)
│   │   └── styles.py             # UI styling
│   ├── tools/
│   │   ├── pdf.py                # PDF tools
│   │   ├── office_tools.py       # Office converters
│   │   └── youtube_transcript.py # Transcript tool
│   └── utils/
│       ├── adblocker.py          # Ad blocking
│       └── proxy_tools.py        # Proxy support
│
├── main.py                       # FastAPI app
├── marin.py                      # AI engine
├── langgraph_agent.py            # Agent workflow
├── config.py                     # Model routing
├── database.py                   # SQLite schema
├── rag_server.py                 # RAG engine
├── docker-compose.yml            # Docker config
├── Dockerfile                    # Container build
└── requirements.txt              # Dependencies
```

## API Endpoints (New)

### YouTube Tools
```
POST /api/youtube/download
POST /api/youtube/audio
GET  /api/youtube/info
POST /api/youtube/transcript
POST /api/youtube/playlist
```

### Learning Tools
```
POST /api/learn/books
POST /api/learn/plan
POST /api/learn/chapter
POST /api/learn/quiz
```

### PDF Tools (Enhanced)
```
POST /api/pdf/analyze
POST /api/pdf/tables
POST /api/pdf/markdown
POST /api/pdf/chat
POST /api/pdf/compare
```

---

# PART 8: IMPROVEMENTS & ENHANCEMENTS

## Tool Improvements

### 1. Smart Caching
- Cache downloaded PDFs locally
- Cache YouTube transcripts
- Cache book content
- Reduces API calls and download time

### 2. Offline Mode
- Download books/videos for offline access
- Local RAG index works without internet
- Sync when connection restored

### 3. Batch Operations
- Download entire playlists
- Convert multiple PDFs at once
- Process folders of documents

### 4. AI-Powered Features
- Auto-summarize downloaded content
- Generate quiz from any document
- Create study plans based on user level
- Smart recommendations

### 5. Integration Features
- Export to Google Drive
- Sync with Notion
- Integration with Anki (flashcards)
- Calendar integration for study schedules

## Technical Improvements

### 1. Performance
- Async downloads for YouTube
- Parallel PDF processing
- Background RAG indexing
- CDN for static assets

### 2. Reliability
- Retry failed downloads
- Resume interrupted transfers
- Graceful degradation
- Error recovery

### 3. Security
- Rate limiting per user
- Input validation
- Sandboxed execution
- Encrypted storage

---

# PART 9: SUCCESS METRICS

## Tool Usage Metrics
- PDF downloads per day
- YouTube transcripts generated
- Books downloaded and indexed
- Conversions performed (PDF↔Excel, etc.)

## User Metrics
- Daily active users
- Pro subscription conversion rate
- User retention (7-day, 30-day)
- Feature adoption rate

## Business Metrics
- Monthly recurring revenue (MRR)
- Customer acquisition cost (CAC)
- Lifetime value (LTV)
- Churn rate

---

# PART 10: RISKS & MITIGATION

## Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| yt-dlp breaks | YouTube tools fail | Monitor updates, fallback to API |
| PDF library bugs | Conversion fails | Multiple fallback libraries |
| RAG index corruption | Learning tools fail | Regular backups, checksums |
| API rate limits | Tool unavailability | Caching, multiple providers |

## Business Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Low adoption | No revenue | Free tier, word of mouth |
| Competition | Lost users | Focus on tools, not AI |
| Cost overrun | Negative margin | Local models, free APIs |
| Security breach | Trust loss | Regular audits, encryption |

---

# APPENDIX A: DEPENDENCIES

## New Packages Needed
```txt
yt-dlp>=2024.1.1        # YouTube downloader
youtube-transcript-api  # Transcript extraction (already in SwordFish)
pymupdf>=1.23           # PDF processing (already have)
pdfplumber              # Table extraction
pdf2docx                # PDF to Word
mammoth                 # Word to PDF
openpyxl                # Excel handling
python-pptx             # PowerPoint handling
img2pdf                 # Image to PDF
fpdf2                   # PDF generation
pikepdf                 # PDF manipulation
```

## API Keys (Free Tiers)
- CoinGecko (crypto prices) — Free
- Yahoo Finance (stock data) — Free
- DuckDuckGo (web search) — Free
- Open-Meteo (weather) — Free
- Open Library (books) — Free
- Project Gutenberg (books) — Free
- arXiv (papers) — Free

---

# APPENDIX B: COMMANDS

## Install Dependencies
```bash
pip install yt-dlp youtube-transcript-api pymupdf pdfplumber pdf2docx mammoth openpyxl python-pptx img2pdf fpdf2 pikepdf
```

## Test YouTube Download
```bash
python -c "from tools.youtube_downloader import download_video; print(download_video('https://youtu.be/dQw4w9WgXcQ', quality='360p'))"
```

## Test PDF Conversion
```bash
python -c "from tools.office_tools import pdf_to_xlsx; print(pdf_to_xlsx('test.pdf'))"
```

## Run SwordFish
```bash
cd SwordFish && python src/main.py
```

---

**Document Version**: 1.0
**Author**: Bayazid & Marin
**Date**: June 2025
**Status**: Active Development
