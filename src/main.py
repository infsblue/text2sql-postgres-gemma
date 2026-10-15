import argparse
import sys
from pathlib import Path

from llama_cpp import Llama

DEFAULT_MODEL = (
    Path(__file__).resolve().parent.parent / "models" / "codegemma-1.1-7b-it-f16.gguf"
)


def load_model(model_path: Path, n_gpu_layers: int, n_ctx: int) -> Llama:
    return Llama(
        model_path=str(model_path),
        n_gpu_layers=n_gpu_layers,
        n_ctx=n_ctx,
        verbose=False,
    )


def generate_code(llm: Llama, prompt: str, max_tokens: int, temperature: float) -> str:
    response = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response["choices"][0]["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate code from a prompt with CodeGemma.")
    parser.add_argument("prompt", nargs="?", help="Prompt text (reads stdin if omitted)")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to GGUF model")
    parser.add_argument("--n-gpu-layers", type=int, default=0, help="Layers to offload to GPU")
    parser.add_argument("--n-ctx", type=int, default=4096, help="Context window size")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.2)
    args = parser.parse_args()

    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        parser.error("empty prompt")
    if not args.model.is_file():
        parser.error(f"model not found: {args.model}")

    llm = load_model(args.model, args.n_gpu_layers, args.n_ctx)
    print(generate_code(llm, prompt, args.max_tokens, args.temperature))
    return 0


if __name__ == "__main__":
    sys.exit(main())
