import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from llama_cpp import Llama
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from . import config


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_tokens: int = 1024
    temperature: float = 0.2


class GenerateResponse(BaseModel):
    response: str


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1)


class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="Question in plain language about the database.",
        examples=["Which customers spent the most money?"],
    )
    execute: bool = Field(True, description="Run the generated SQL and return rows.")
    max_tokens: int = 512


class AskResponse(BaseModel):
    sql: str
    rows: list[dict] | None = None
    error: str | None = None


SCHEMA_SQL = """
SELECT c.table_name, c.column_name, c.data_type
FROM information_schema.columns c
JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position
"""

PROMPT_TEMPLATE = """You are a PostgreSQL expert. Given the schema below, write one \
valid PostgreSQL SELECT query that answers the question. Return only the SQL \
in a ```sql code block, with no explanation.

Schema:
{schema}

Question: {question}"""


async def fetch_schema(pool) -> str:
    async with pool.connection() as conn:
        rows = await (await conn.execute(SCHEMA_SQL)).fetchall()
    tables: dict[str, list[str]] = {}
    for r in rows:
        tables.setdefault(r["table_name"], []).append(f"{r['column_name']} {r['data_type']}")
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in tables.items())


def extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip()


async def run_readonly(pool, sql: str) -> list[dict]:
    async with pool.connection() as conn:
        # read-only transaction so generated SQL cannot modify data
        await conn.set_read_only(True)
        cur = await conn.execute(sql)
        return await cur.fetchall() if cur.description else []


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
    app.state.pool = AsyncConnectionPool(
        config.DATABASE_URL, open=False, kwargs={"row_factory": dict_row}
    )
    await app.state.pool.open()
    yield
    await app.state.pool.close()


app = FastAPI(title="text2sql", lifespan=lifespan)


@app.get("/health")
async def health(request: Request):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, request: Request):
    # sync endpoint: FastAPI runs it in a threadpool, keeping the loop free
    result = request.app.state.llm.create_chat_completion(
        messages=[{"role": "user", "content": req.prompt}],
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    return GenerateResponse(response=result["choices"][0]["message"]["content"].strip())


@app.post("/query")
async def query(req: QueryRequest, request: Request):
    try:
        rows = await run_readonly(request.app.state.pool, req.sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"rows": rows}


@app.get("/schema")
async def schema(request: Request):
    return {"schema": await fetch_schema(request.app.state.pool)}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request):
    """Ask in plain language: builds a prompt from the live schema, generates SQL, and optionally runs it."""
    prompt = PROMPT_TEMPLATE.format(
        schema=await fetch_schema(request.app.state.pool), question=req.question
    )
    result = await run_in_threadpool(
        request.app.state.llm.create_chat_completion,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=req.max_tokens,
        temperature=0.0,
    )
    sql = extract_sql(result["choices"][0]["message"]["content"])
    if not req.execute:
        return AskResponse(sql=sql)
    try:
        rows = await run_readonly(request.app.state.pool, sql)
    except Exception as exc:
        return AskResponse(sql=sql, error=str(exc))
    return AskResponse(sql=sql, rows=rows)
