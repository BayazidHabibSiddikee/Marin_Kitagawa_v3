"""Download or analyze external resources (PDFs, web pages, etc.)."""


def resource_download_analyze(url: str) -> str:
    """Download or analyze any resource."""
    if url.endswith(".pdf"):
        from tools.pdf_downloader import download_pdf
        try:
            path = download_pdf(url, "downloaded_resource")
            return f"PDF downloaded to: {path}"
        except Exception as e:
            return f"Error downloading PDF: {e}"
    from tools.knowledge_hub import scrape_content
    return scrape_content(url)
