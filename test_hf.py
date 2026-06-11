import os
os.environ["HF_HUB_OFFLINE"] = "1"
from sentence_transformers import SentenceTransformer
print("Loading model...")
m = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
print("Success!")
