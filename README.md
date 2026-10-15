# text2sql-postgres-gemma

An open-source Python engine that converts natural language into PostgreSQL queries using CodeGemma.

## About

**Text2sql-postgres-gemma** is a lightweight, privacy-focused Text-to-SQL engine designed to run fully local on Linux systems. By leveraging Google's **CodeGemma 1.1 7B Instruct** model via local GGUF inference, it translates plain natural language questions into valid, optimized PostgreSQL `SELECT` queries without transmitting database schemas or sensitive context to third-party cloud APIs.

## Model

* **Model Name:** CodeGemma 1.1 7B Instruct (`google/codegemma-1.1-7b-it-GGUF`)
* **Recommended File:** `codegemma-1.1-7b-it-f16.gguf` (~16.2 GB) or community quantized versions (e.g., `Q4_K_M` ~5.3 GB)
* **Execution Engine:** `llama-cpp-python` (CPU build) inside Docker
* **Licensing:** Subject to [Google Gemma Terms of Use](https://ai.google.dev/gemma/terms)

## Requirements

Everything else (Python, dependencies, llama.cpp, PostgreSQL) runs in Docker.

### Hardware Specs (minimum to run the model on CPU)
* **CPU:** any x86_64 CPU (4+ cores recommended; generating a query takes seconds to minutes)
* **RAM:** 20 GB available to Docker for the F16 weights (~16 GB) plus context buffers; a quantized `Q4_K_M` file needs far less
* **Disk:** ~17 GB for the F16 model file plus images and the database volume

### Software Dependencies
* **Docker** with Docker Compose v2
* **Internet** on first start, to download the Northwind sample data

### Python Dependencies (inside the image, `api/requirements.txt`)
- fastapi>=0.110
- uvicorn[standard]>=0.29
- psycopg[binary,pool]>=3.1
- pydantic>=2.0.0
- llama-cpp-python>=0.2.75

## Sample Database (Northwind)

`docker compose up` starts Postgres and a one-shot `bootstrap` service (`db/bootstrap.py`,
Python + `psycopg`) that loads the full **Northwind** sample database: 14 tables
(`customers`, `orders`, `order_details`, `products`, `categories`, `suppliers`, `employees`,
`shippers`, `territories`, ...). The API starts only after the load succeeds.

* No PyPI package ships Northwind, so the script downloads the Postgres version of the
  [pthom/northwind_psql](https://github.com/pthom/northwind_psql) dump, pinned to a commit
  for reproducibility. The first start therefore needs internet access.
* It is idempotent: if all 14 tables exist it does nothing, so restarts never wipe data.
* Upgrading from the previous 4-table sample schema: the loader replaces its `customers`,
  `orders` and `products` tables and removes `order_items`. To start clean instead, run
  `docker compose down -v` first (this deletes the database volume).

## Running and Using the API

```bash
cp .env.example .env        # set POSTGRES_* values
docker compose up --build   # model is mounted read-only from ./models
```

Open **http://localhost:8000/docs** (Swagger).

| Group | Endpoint | What it does |
|---|---|---|
| Tests | `POST /tests/{count-customers, customers-in-brazil, most-expensive-product, products-per-category, top-customers-by-orders, revenue-per-category}` | Fixed question: the model writes SQL, it runs, and the rows are compared with a hand-written reference SQL. The response shows both SQL statements, both result sets, missing/unexpected rows and PASS/FAIL |
| Tests | `GET /tests` | Lists the tests, questions and reference SQL without running the model |
| Generate and execute | `POST /sql/generate` | Your question becomes SQL. Nothing is executed or blocked; `warnings` flag risky SQL |
| Generate and execute | `POST /sql/execute` | Runs SQL you reviewed. Refuses unless `approved` is `true` |
| System | `GET /health`, `GET /schema` | Status; schema text given to the model |

The test material lives in `api/app/scenarios.py`. A FAIL is a legitimate result (the model
can be wrong), not an API error.

Generated SQL is **not** filtered; the human reviews it. Execution is limited to a read-only
transaction, a statement timeout (`STATEMENT_TIMEOUT_MS`, default 10 s) and 100 rows. This is a
guard against accidents, not a security boundary: use a database role with only `SELECT` for
anything beyond a demo.

## Acceptance Criteria

To ensure reliable, secure, and production-ready operation, the pipeline enforces the following criteria:

1. **Schema Context Integration:**
   * Automatically inspects PostgreSQL metadata (DDLs, table names, column types, foreign key relationships) and injects it into the LLM prompt context.
2. **Valid SQL Generation:**
   * Converts user requests (e.g., *"Show total sales by client last month"*) into executable PostgreSQL-compliant syntax.
3. **Human-Reviewed Execution:**
   * Generated SQL is returned with review `warnings` (non-SELECT, multiple statements, data-changing keywords) but is not blocked.
   * Execution requires explicit approval (`approved=true`) and runs in a read-only transaction with a statement timeout and a row cap.
   * Recommended hardening (not implemented): a dedicated PostgreSQL role with exclusive `SELECT` access.
4. **Resource Bounds & Performance:**
   * Enforces context bounds (`n_ctx=4096`) and a per-request token limit; inference is serialized.
5. **Licensing Isolation:**
   * Codebase distributed under the **BSD 2-Clause License**.
   * Model weights (`*.gguf`) are strictly excluded from Git tracking via `.gitignore`.

## Licensing & Dependencies

### Source Code License
This project's original source code is licensed under the **BSD 2-Clause License** (BSD Simplified). See the LICENSE file for the full legal text.

### Third-Party Dependencies Licenses
All direct dependencies used in this project are compatible with permissive open-source licensing:
* **`llama-cpp-python`**: MIT License
* **`fastapi`**: MIT License
* **`uvicorn`**: BSD 3-Clause License
* **`psycopg`** (psycopg 3): LGPL v3
* **`pydantic`**: MIT License
* **Northwind sample data**: originates from Microsoft and is distributed under the Microsoft Public License (Ms-PL), as stated by the upstream repository. It is downloaded at runtime, not bundled here.

### Model Weights Notice
* **CodeGemma**: Model weights, parameters, and architecture belong to Google LLC and are governed by the [Gemma Terms of Use](https://ai.google.dev/gemma/terms) and [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy).
* This repository **does not host, bundle, or re-distribute** model weights. Users must separately accept Google's terms and acquire `.gguf` files directly from official sources.