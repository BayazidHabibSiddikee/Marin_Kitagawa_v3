# ===== Kaggle Notebook: Marin Tool Caller SLM Training (Unsloth) =====
# Upload this notebook to Kaggle along with your marin_tool_dataset.jsonl
# Turn on GPU T4 x2 or P100

# !pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# !pip install -q --no-deps "trl<0.9.0" peft accelerate bitsandbytes

import torch
from unsloth import FastLanguageModel
from datasets import load_dataset

# 1. Configuration
max_seq_length = 2048 # Good enough for tool schemas + short query
dtype = None # Auto detection
load_in_4bit = True # Use 4bit quantization to reduce memory usage

# We recommend Qwen2.5 1.5B or 3B for local CPU/RAM inference (16GB RAM)
# 1.5B is much faster on CPU, 3B is smarter. Let's try 1.5B Instruct first.
model_name = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# 2. Add LoRA Adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, # Choose any number > 0 ! Suggested 8, 16, 32, 64, 128
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 16,
    lora_dropout = 0, # Supports any, but = 0 is optimized
    bias = "none",    # Supports any, but = "none" is optimized
    use_gradient_checkpointing = "unsloth", 
    random_state = 3407,
)

# 3. Format Dataset (ChatML)
# The dataset we generated is already in {"messages": [...]} format.
# Unsloth/Transformers standardizes this via apply_chat_template.

from unsloth.chat_templates import get_chat_template
tokenizer = get_chat_template(
    tokenizer,
    chat_template = "chatml", # We use standard ChatML
    mapping = {"role": "role", "content": "content", "user": "user", "assistant": "assistant"}, 
)

def formatting_prompts_func(examples):
    convos = examples["messages"]
    texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
    return {"text": texts}

dataset = load_dataset("json", data_files="/kaggle/input/datasets/bayazidhs/marin-vibe/marin_tool_dataset.jsonl", split="train")
dataset = dataset.map(formatting_prompts_func, batched = True)

# 4. Training
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False, # Can make training 5x faster for short sequences
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 200, # Set to num_train_epochs = 1 for full run
        # num_train_epochs = 2, # Use this instead of max_steps for full training
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

trainer_stats = trainer.train()

# 5. Export to GGUF (for local Ollama CPU inference)
print("Exporting model to GGUF format...")
# Save to 4-bit Q4_K_M GGUF (Perfect balance of size and accuracy for 16GB RAM)
model.save_pretrained_gguf("marin_tool_caller", tokenizer, quantization_method = "q4_k_m")

print("Done! Download the .gguf file from the 'marin_tool_caller' folder and use it in Ollama.")
