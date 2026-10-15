import os

DATABASE_URL = os.environ["DATABASE_URL"]
MODEL_PATH = os.environ.get("MODEL_PATH", "/models/codegemma-1.1-7b-it-f16.gguf")
N_GPU_LAYERS = int(os.environ.get("N_GPU_LAYERS", "0"))
N_CTX = int(os.environ.get("N_CTX", "4096"))
