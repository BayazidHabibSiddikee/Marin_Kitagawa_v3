# Marin OS — Quick Roadmap
## What to Build Next

---

## 🔥 IMMEDIATE (This Week)

### 1. YouTube Downloader
```bash
pip install yt-dlp
```
Create `tools/youtube_downloader.py`:
- `download_video(url, quality)` → mp4
- `download_audio(url)` → mp3
- `get_video_info(url)` → metadata
- Integrate into SwordFish interface

### 2. Fix Existing Issues
- `authlib` not installed (Google OAuth broken)
- `docker` SDK missing from requirements.txt
- Weak API secret in `.env`

---

## 📚 NEXT WEEK

### 3. Book Downloader
- Search Project Gutenberg, Open Library
- Download PDF/EPUB
- Auto-index to RAG
- Create `tools/book_downloader.py`

### 4. Study Engine
- User says "learn Numerics" → auto-download books
- Create study plan
- Generate quizzes
- Create `tools/study_engine.py`

---

## 📄 WEEK 3

### 5. Smart PDF Analyzer
- AI-powered structure detection
- Table extraction with validation
- PDF → Markdown converter
- Create `tools/pdf_analyzer.py`

### 6. Document Q&A
- Chat with any PDF
- Compare documents
- Create `tools/document_qa.py`

---

## 💰 REVENUE MODEL

### Free Tier (SwordFish Basic)
- PDF merge/split/convert ✅
- YouTube transcript ✅
- Student tools ✅
- 5 downloads/day limit

### Pro Tier ($10/month)
- Unlimited downloads
- AI PDF analysis
- Dynamic learning
- Finance tools
- Priority support

---

## 🎯 KEY DIFFERENTIATORS

1. **Tools First** — Not AI chatbot, but powerful tools
2. **Dynamic Learning** — Auto-download books and study
3. **PDF Intelligence** — Not just download, but understand
4. **YouTube Smart** — Download OR learn from transcripts
5. **Offline Capable** — Works without internet (cached)

---

## 📊 SUCCESS METRICS

- 50 Pro subscribers in 6 months
- 1000+ tool usage/day
- 4.5+ user rating
- <2% churn rate

---

**Full plan**: `doc/MARIN_MASTER_PLAN.md`
