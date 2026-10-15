import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from llama_cpp import Llama
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from . import config
from .scenarios import TESTS, TextToSqlTest
from .sqlutil import (
    PROMPT_TEMPLATE,
    compare_rows,
    extract_sql,
    fetch_schema,
    jsonable,
    review_sql,
    run_readonly,
)

MAX_ROWS = 100

DESCRIPTION = """
**text2sql-postgres-gemma** turns a plain-language question into a PostgreSQL query with a
local CodeGemma model, over the **Northwind** sample database (14 tables: customers, orders,
order_details, products, categories, suppliers, employees, ...).

## Three steps, you stay in control

| Step | Endpoint | What happens |
|---|---|---|
| 1 | `POST /sql/generate` | Your question becomes SQL. **Nothing is executed**, and nothing is blocked: the response only carries `warnings` for anything that looks risky. |
| 2 | *you review the SQL* | Read it. Edit it if you want. |
| 3 | `POST /sql/execute` | Runs the SQL you approve. It refuses to run unless you set `approved` to `true`. |

## Preconfigured tests

Six endpoints under **Tests**. Each one asks a fixed question, lets the model write the SQL,
runs it, and compares the rows with the rows of a hand-written *reference SQL*. The response
shows the question, the generated SQL, the reference SQL, both result sets, any missing or
unexpected rows, and a pass/fail verdict, so you can verify the result yourself.
`GET /tests` lists them all without running the model.

## Safety notes

* Generated SQL is **not filtered**. Review it before executing.
* Execution happens in a read-only transaction with a statement timeout and a row cap, which
  stops accidental writes. It is a guard, **not a security boundary**: for real deployments
  connect with a database role that only has `SELECT`.
* The model can be wrong. A test failing is a legitimate result, not an API error.
* Inference runs one request at a time; expect seconds to minutes per generation on CPU.
"""

TAGS = [
    {
        "name": "Tests",
        "description": "Preconfigured questions with reference SQL and expected rows. "
        "Click *Try it out* -> *Execute*; no input needed.",
    },
    {
        "name": "Generate and execute",
        "description": "Produce a query from your own question, review it, then run it if "
        "you approve.",
    },
    {"name": "System", "description": "Service status and database schema."},
]


class ResultSet(BaseModel):
    columns: list[str] = Field(description="Column names, in order.")
    rows: list[list] = Field(description="Result rows (capped at 100).")
    row_count: int = Field(description="Number of rows returned.")
    truncated: bool = Field(False, description="True when more rows existed than the cap.")


class GenerateRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="Question in plain language about the Northwind database.",
        examples=["Which 5 products have the highest unit price?"],
    )
    max_tokens: int = Field(512, ge=16, le=2048, description="Maximum tokens for the SQL.")


class GenerateResponse(BaseModel):
    question: str
    sql: str = Field(description="The generated SQL. NOT executed.")
    warnings: list[str] = Field(
        description="Things to double-check before executing. Empty means no red flags "
        "were found, not that the SQL is correct."
    )
    next_step: str = Field(
        description="What to do next: review `sql`, then call POST /sql/execute with it."
    )


class ExecuteRequest(BaseModel):
    sql: str = Field(
        min_length=1,
        description="The SQL to run, typically copied from /sql/generate after reviewing it.",
        examples=["SELECT product_name, unit_price FROM products ORDER BY unit_price DESC LIMIT 5"],
    )
    approved: bool = Field(
        False,
        description="You must set this to true to confirm you reviewed the SQL and accept "
        "running it. Otherwise nothing runs.",
    )


class ExecuteResponse(BaseModel):
    sql: str
    warnings: list[str] = Field(description="Review warnings for the SQL that was run.")
    result: ResultSet


class TestCase(BaseModel):
    test: str
    title: str
    purpose: str = Field(description="What this test exercises and what to expect.")
    question: str = Field(description="The fixed question sent to the model.")
    reference_sql: str = Field(description="Hand-written SQL that defines the right answer.")
    rows_compared_in_order: bool = Field(
        description="If true, row order must match; otherwise rows are compared as a set."
    )


class TestReport(BaseModel):
    test: str
    title: str
    purpose: str
    question: str = Field(description="The fixed question sent to the model.")
    generated_sql: str = Field(description="The SQL the model wrote.")
    warnings: list[str] = Field(description="Review warnings for the generated SQL.")
    reference_sql: str = Field(description="Hand-written SQL that defines the right answer.")
    expected: ResultSet = Field(description="Rows produced by the reference SQL.")
    actual: ResultSet | None = Field(
        None, description="Rows produced by the generated SQL (null if it failed to run)."
    )
    execution_error: str | None = Field(
        None, description="Database error if the generated SQL could not run."
    )
    rows_compared_in_order: bool
    missing_rows: list[list] = Field(
        description="Expected rows the generated SQL did not return."
    )
    unexpected_rows: list[list] = Field(
        description="Rows the generated SQL returned that were not expected."
    )
    passed: bool = Field(description="True when actual rows equal expected rows.")
    verdict: str = Field(description="One-sentence summary of the outcome.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_path = Path(config.MODEL_PATH)
    if not model_path.is_file():
        raise RuntimeError(f"model not found: {model_path}")
    app.state.llm = Llama(
        model_path=str(model_path),
        n_gpu_layers=config.N_GPU_LAYERS,
        n_ctx=config.N_CTX,
        verbose=False,
    )
    app.state.llm_lock = threading.Lock()
    app.state.pool = AsyncConnectionPool(
        config.DATABASE_URL,
        open=False,
        kwargs={
            "row_factory": dict_row,
            # every transaction is read-only and time-limited, even after COMMIT tricks
            "options": "-c default_transaction_read_only=on "
            f"-c statement_timeout={config.STATEMENT_TIMEOUT_MS}",
        },
    )
    await app.state.pool.open()
    yield
    await app.state.pool.close()


app = FastAPI(
    title="text2sql-postgres-gemma",
    summary="Local text-to-SQL over the Northwind database, with review before execution.",
    description=DESCRIPTION,
    version="2.0.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)


def _generate_sql(request: Request, question: str, schema: str, max_tokens: int) -> str:
    prompt = PROMPT_TEMPLATE.format(schema=schema, question=question)
    # llama.cpp contexts are not thread-safe: serialize inference
    with request.app.state.llm_lock:
        result = request.app.state.llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
    return extract_sql(result["choices"][0]["message"]["content"])


async def _execute(request: Request, sql: str) -> ResultSet:
    columns, rows, truncated = await run_readonly(request.app.state.pool, sql, MAX_ROWS)
    rows = [[jsonable(v) for v in row] for row in rows]
    return ResultSet(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)


async def _run_test(test: TextToSqlTest, request: Request) -> TestReport:
    pool = request.app.state.pool
    schema = await fetch_schema(pool)
    try:
        expected = await _execute(request, test.reference_sql)
    except Exception as exc:
        raise HTTPException(500, f"reference SQL for '{test.slug}' failed: {exc}")

    generated_sql = await run_in_threadpool(_generate_sql, request, test.question, schema, 512)
    warnings = review_sql(generated_sql)

    actual: ResultSet | None = None
    error: str | None = None
    try:
        actual = await _execute(request, generated_sql)
    except Exception as exc:
        error = str(exc).strip()

    missing: list[list] = []
    unexpected: list[list] = []
    passed = False
    if actual is not None:
        passed, missing, unexpected = compare_rows(expected.rows, actual.rows, test.ordered)

    if error:
        verdict = f"FAIL: the generated SQL could not run ({error.splitlines()[0]})."
    elif passed:
        verdict = (
            f"PASS: the generated SQL returned the same {expected.row_count} row(s) as the "
            "reference SQL."
        )
    elif not missing and not unexpected:
        verdict = "FAIL: same rows as the reference, but in a different order."
    else:
        verdict = (
            f"FAIL: {len(missing)} expected row(s) missing and {len(unexpected)} unexpected "
            "row(s). The model can be wrong; compare the two SQL statements."
        )
    return TestReport(
        test=test.slug,
        title=test.title,
        purpose=test.purpose,
        question=test.question,
        generated_sql=generated_sql,
        warnings=warnings,
        reference_sql=test.reference_sql,
        expected=expected,
        actual=actual,
        execution_error=error,
        rows_compared_in_order=test.ordered,
        missing_rows=[[jsonable(v) for v in r] for r in missing],
        unexpected_rows=[[jsonable(v) for v in r] for r in unexpected],
        passed=passed,
        verdict=verdict,
    )


def _register_test(test: TextToSqlTest) -> None:
    async def endpoint(request: Request) -> TestReport:
        return await _run_test(test, request)

    endpoint.__name__ = "test_" + test.slug.replace("-", "_")
    app.post(
        f"/tests/{test.slug}",
        response_model=TestReport,
        tags=["Tests"],
        summary=test.title,
        description=(
            f"{test.purpose}\n\n"
            f"**Preconfigured question:** `{test.question}`\n\n"
            f"**Reference SQL (defines the expected result):**\n\n```sql\n"
            f"{test.reference_sql}\n```\n\n"
            "Click *Execute*: the model writes SQL, it is run, and its rows are compared "
            "with the reference rows. Row order is "
            + ("checked." if test.ordered else "ignored.")
        ),
    )(endpoint)


for _test in TESTS.values():
    _register_test(_test)


@app.get(
    "/tests",
    response_model=list[TestCase],
    tags=["Tests"],
    summary="List all preconfigured tests (does not run the model)",
)
def list_tests() -> list[TestCase]:
    return [
        TestCase(
            test=t.slug,
            title=t.title,
            purpose=t.purpose,
            question=t.question,
            reference_sql=t.reference_sql,
            rows_compared_in_order=t.ordered,
        )
        for t in TESTS.values()
    ]


@app.post(
    "/sql/generate",
    response_model=GenerateResponse,
    tags=["Generate and execute"],
    summary="Step 1: turn your question into SQL (nothing is executed)",
    description="Generates SQL for your question from the live database schema. The SQL is "
    "**not executed and not filtered**; `warnings` lists anything that looks risky. Review "
    "it, then send it to `POST /sql/execute`.",
)
async def generate(req: GenerateRequest, request: Request) -> GenerateResponse:
    schema = await fetch_schema(request.app.state.pool)
    sql = await run_in_threadpool(_generate_sql, request, req.question, schema, req.max_tokens)
    return GenerateResponse(
        question=req.question,
        sql=sql,
        warnings=review_sql(sql),
        next_step="Review the SQL, then call POST /sql/execute with it and approved=true.",
    )


@app.post(
    "/sql/execute",
    response_model=ExecuteResponse,
    tags=["Generate and execute"],
    summary="Step 3: run SQL you reviewed and approved",
    description="Runs the SQL only if `approved` is `true`. Warnings are returned but do not "
    "block execution: you decide. The query runs in a read-only transaction with a "
    "statement timeout, and at most 100 rows are returned.",
)
async def execute(req: ExecuteRequest, request: Request) -> ExecuteResponse:
    warnings = review_sql(req.sql)
    if not req.approved:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Not executed: set approved=true to confirm you reviewed this SQL.",
                "warnings": warnings,
            },
        )
    try:
        result = await _execute(request, req.sql)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail={"message": str(exc).strip(), "warnings": warnings}
        )
    return ExecuteResponse(sql=req.sql, warnings=warnings, result=result)


@app.get("/health", tags=["System"], summary="Service, model and database status")
async def health(request: Request) -> dict[str, str]:
    async with request.app.state.pool.connection() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok", "model": Path(config.MODEL_PATH).name}


@app.get("/schema", tags=["System"], summary="Schema description given to the model")
async def schema(request: Request) -> dict[str, str]:
    return {"schema": await fetch_schema(request.app.state.pool)}
