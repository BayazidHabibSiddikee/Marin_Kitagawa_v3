# ===== Kaggle Notebook: Marin Text-to-Animation Tagger =====
# Upload this notebook, marin_animation_dataset.jsonl, and marin_gesture_chunks.json to Kaggle.
# Turn on GPU (T4 is fine).
#
# DATASET STATS (as of results(1).zip merge):
#   marin_animation_dataset.jsonl  → 430 examples (350 original + 80 synthetic)
#   marin_gesture_chunks.json      → 1168 text/label pairs, 44 unique animations
#
# COVERAGE WARNING: static/animations/ holds 118 BVH files but the current
# dataset only labels 44 of them, so the trained model can never predict the
# other 74. tools/generate_animation_dataset.py now feeds the FULL sorted
# animation list to the LLM (it used to sample 10 random files per batch) —
# regenerate the dataset with it, re-chunk, and retrain to widen coverage.
# At inference, director_engine._safe_anim() guards against labels for
# animations that no longer exist on disk.

!pip install -q transformers datasets evaluate accelerate torch scikit-learn

import json
import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
KAGGLE_BASE  = "/kaggle/input/datasets/bayazidhs/marin-vibe"
ANIM_JSONL   = f"{KAGGLE_BASE}/marin_animation_dataset.jsonl"
GESTURE_JSON = f"{KAGGLE_BASE}/marin_gesture_chunks.json"

# ─── 1. LOAD GESTURE CHUNKS DATASET ──────────────────────────────────────────
# marin_gesture_chunks.json is pre-chunked (1168 samples, 44 labels) and is the
# richer training signal – use it as the primary source.
print("Loading gesture chunks dataset...")
with open(GESTURE_JSON, "r", encoding="utf-8") as f:
    gesture_data = json.load(f)

texts      = gesture_data["texts"]      # list[str]
labels_raw = gesture_data["labels"]     # list[str]  (bvh filenames)
all_labels = gesture_data["all_labels"] # list[str]  (44 unique animations)

label2id = {lbl: i for i, lbl in enumerate(all_labels)}
id2label  = {i: lbl for i, lbl in enumerate(all_labels)}
num_labels = len(all_labels)
print(f"  {len(texts)} samples | {num_labels} animation classes")

# ─── 2. AUGMENT WITH FULL ANIMATION JSONL ────────────────────────────────────
# Pull full-sentence examples from the merged 430-example JSONL to add variety.
print("Augmenting with marin_animation_dataset.jsonl ...")
extra_texts, extra_labels = [], []
try:
    with open(ANIM_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            full_text = item.get("text", "")
            seqs = item.get("sequence", [])
            if seqs and full_text:
                # Use the first animation in the sequence as the sentence-level label
                anim = seqs[0]["animation"]
                if anim in label2id:
                    extra_texts.append(full_text)
                    extra_labels.append(anim)
    texts      += extra_texts
    labels_raw += extra_labels
    print(f"  +{len(extra_texts)} augmented examples → total {len(texts)}")
except FileNotFoundError:
    print(f"  WARNING: {ANIM_JSONL} not found, skipping augmentation.")

label_ids = [label2id[lbl] for lbl in labels_raw]

# ─── 3. TOKENIZER & MODEL ─────────────────────────────────────────────────────
# DistilRoBERTa is tiny (82M) and fast on Kaggle T4.
model_name = "distilroberta-base"
print(f"\nLoading tokenizer and model: {model_name}")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(
    model_name,
    num_labels=num_labels,
    id2label=id2label,
    label2id=label2id,
)

# ─── 4. PREPARE DATASET ──────────────────────────────────────────────────────
print("Tokenizing dataset...")
def tokenize_fn(batch):
    return tokenizer(batch["text"], truncation=True, max_length=128, padding="max_length")

raw_ds = Dataset.from_dict({"text": texts, "label": label_ids})
raw_ds = raw_ds.train_test_split(test_size=0.1, seed=42)

train_ds = raw_ds["train"].map(tokenize_fn, batched=True)
eval_ds  = raw_ds["test"].map(tokenize_fn, batched=True)

train_ds = train_ds.remove_columns(["text"])
eval_ds  = eval_ds.remove_columns(["text"])
train_ds.set_format("torch")
eval_ds.set_format("torch")

print(f"  Train: {len(train_ds)} | Eval: {len(eval_ds)}")

# ─── 5. METRICS ──────────────────────────────────────────────────────────────
import numpy as np
from sklearn.metrics import accuracy_score, f1_score

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = accuracy_score(labels, preds)
    f1  = f1_score(labels, preds, average="weighted", zero_division=0)
    return {"accuracy": acc, "f1_weighted": f1}

# ─── 6. TRAINING ─────────────────────────────────────────────────────────────
print("\nStarting training...")
training_args = TrainingArguments(
    output_dir="./animation_model_output",
    learning_rate=3e-5,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=32,
    num_train_epochs=8,
    weight_decay=0.01,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1_weighted",
    logging_steps=20,
    warmup_ratio=0.1,
    fp16=torch.cuda.is_available(),
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    compute_metrics=compute_metrics,
)

trainer.train()

# ─── 7. SAVE & EXPORT ────────────────────────────────────────────────────────
print("\nSaving model...")
model.save_pretrained("marin_animation_model")
tokenizer.save_pretrained("marin_animation_model")

# Also save the label mapping for use in marin at inference time
with open("marin_animation_model/label_map.json", "w") as f:
    json.dump({"id2label": id2label, "label2id": label2id, "all_labels": all_labels}, f, indent=2)

# Lightweight .pt state dict for direct torch.load() if preferred
torch.save(model.state_dict(), "marin_animation_weights.pt")

print("Done! Download marin_animation_model/ (HF format) + marin_animation_weights.pt")
print(f"Model predicts one of {num_labels} animations per text chunk.")
