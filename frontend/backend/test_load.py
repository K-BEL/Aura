import sys
print(sys.executable)
import torch
from transformers import AutoModelForCausalLM
try:
    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained("SVECTOR-CORPORATION/Continue-TTS", device_map="auto", trust_remote_code=True, torch_dtype=torch.float16)
    print("Success! Devices:", model.hf_device_map)
except Exception as e:
    print("Error:", e)
