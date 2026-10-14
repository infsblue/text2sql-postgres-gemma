# text2sql-postgres-gemma

An open-source Python engine that converts natural language into PostgreSQL queries using CodeGemma.

## About

**Text2sql-postgres-gemma** is a lightweight, privacy-focused Text-to-SQL engine designed to run fully local on Linux systems. By leveraging Google's **CodeGemma 1.1 7B Instruct** model via local GGUF inference, it translates plain natural language questions into valid, optimized PostgreSQL `SELECT` queries without transmitting database schemas or sensitive context to third-party cloud APIs.

## Model

* **Model Name:** CodeGemma 1.1 7B Instruct (`google/codegemma-1.1-7b-it-GGUF`)
* **Recommended File:** `codegemma-1.1-7b-it-f16.gguf` (~16.2 GB) or community quantized versions (e.g., `Q4_K_M` ~5.3 GB)
* **Execution Engine:** Local execution via `llama-cpp-python` with hybrid GPU/CPU offloading
* **Licensing:** Subject to [Google Gemma Terms of Use](https://ai.google.dev/gemma/terms)

## Requirements

### Hardware Specs
* **CPU:** 6-core x86_64 Processor (e.g., Intel Core i7-10750H)
* **RAM:** 16 GB minimum (64 GB recommended for full F16 weight loading)
* **GPU:** NVIDIA Dedicated GPU with 6 GB VRAM (e.g., GeForce RTX 2060) or higher

### Software Dependencies
* **OS:** Linux (Debian 13 / Ubuntu 22.04+ recommended)
* **Python Version:** Python 3.10+
* **Database:** PostgreSQL 12+
* **Drivers:** NVIDIA Proprietary Drivers + CUDA Toolkit (`nvidia-smi` operational)

### Python Dependencies (`requirements.txt`)
- llama-cpp-python>=0.2.75
- psycopg2-binary>=2.9.9
- sqlglot>=23.0.0
- python-dotenv>=1.0.1
- pydantic>=2.0.0

## Acceptance Criteria

To ensure reliable, secure, and production-ready operation, the pipeline enforces the following criteria:

1. **Schema Context Integration:**
   * Automatically inspects PostgreSQL metadata (DDLs, table names, column types, foreign key relationships) and injects it into the LLM prompt context.
2. **Valid SQL Generation:**
   * Converts user requests (e.g., *"Show total sales by client last month"*) into executable PostgreSQL-compliant syntax.
3. **Read-Only Security Guardrails:**
   * **AST Parsing:** Parses generated queries using `sqlglot` to verify that only read-only `SELECT` statements are emitted.
   * **Keyword Enforcement:** Automatically blocks execution if query strings contain destructive or data-modifying commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`).
   * **Low-Privilege Execution:** Executes database calls under a restricted PostgreSQL user role with exclusive `SELECT` access.
4. **Resource Bounds & Performance:**
   * Implements layer offloading to GPU VRAM without throwing Out-Of-Memory (OOM) exceptions.
   * Enforces strict context bounds (`n_ctx=4096`) and query termination triggers (`stop=[";", "\n\n"]`).
5. **Licensing Isolation:**
   * Codebase distributed under the **BSD 2-Clause License**.
   * Model weights (`*.gguf`) are strictly excluded from Git tracking via `.gitignore`.

## Licensing & Dependencies

### Source Code License
This project's original source code is licensed under the **BSD 2-Clause License** (BSD Simplified). See the LICENSE file for the full legal text.

### Third-Party Dependencies Licenses
All direct dependencies used in this project are compatible with permissive open-source licensing:
* **`llama-cpp-python`**: MIT License
* **`psycopg2-binary`**: LGPL v3 with exception (or BSD-like)
* **`sqlglot`**: MIT License
* **`pydantic`**: MIT License
* **`python-dotenv`**: BSD 3-Clause License

### Model Weights Notice
* **CodeGemma**: Model weights, parameters, and architecture belong to Google LLC and are governed by the [Gemma Terms of Use](https://ai.google.dev/gemma/terms) and [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy).
* This repository **does not host, bundle, or re-distribute** model weights. Users must separately accept Google's terms and acquire `.gguf` files directly from official sources.