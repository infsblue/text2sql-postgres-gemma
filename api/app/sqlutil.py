"""SQL helpers: schema description, review warnings, read-only execution, result comparison."""

import re
from datetime import date, datetime
from decimal import Decimal

SCHEMA_SQL = """
SELECT c.table_name, c.column_name, c.data_type
FROM information_schema.columns c
JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
  AND c.data_type <> 'bytea'
ORDER BY c.table_name, c.ordinal_position
"""

CONSTRAINTS_SQL = """
SELECT conrelid::regclass::text AS table_name, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace AND contype IN ('p', 'f')
ORDER BY 1, contype DESC, 2
"""

PROMPT_TEMPLATE = """You are a PostgreSQL expert. Given the schema below, write one \
valid PostgreSQL SELECT query that answers the question. Return only the SQL \
in a ```sql code block, with no explanation.

Schema:
{schema}

Question: {question}"""

MUTATION_WORDS = (
    "insert|update|delete|drop|truncate|alter|create|grant|revoke|copy|merge|"
    "vacuum|call|do|set|commit|rollback"
)
MUTATION_PATTERN = re.compile(rf"\b({MUTATION_WORDS})\b", re.IGNORECASE)


async def fetch_schema(pool) -> str:
    async with pool.connection() as conn:
        columns = await (await conn.execute(SCHEMA_SQL)).fetchall()
        constraints = await (await conn.execute(CONSTRAINTS_SQL)).fetchall()
    tables: dict[str, list[str]] = {}
    for r in columns:
        tables.setdefault(r["table_name"], []).append(f"{r['column_name']} {r['data_type']}")
    keys: dict[str, list[str]] = {}
    for r in constraints:
        keys.setdefault(r["table_name"], []).append(r["definition"])
    lines = []
    for table, cols in tables.items():
        lines.append(f"{table}({', '.join(cols)})")
        lines.extend(f"  {definition}" for definition in keys.get(table, []))
    return "\n".join(lines)


def extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip()


def _strip_comments_and_strings(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def review_sql(sql: str) -> list[str]:
    """Return human-readable warnings. Nothing is blocked: the user decides."""
    warnings: list[str] = []
    cleaned = _strip_comments_and_strings(sql).strip()
    if not cleaned:
        return ["The SQL is empty."]
    statements = [s for s in cleaned.split(";") if s.strip()]
    if len(statements) > 1:
        warnings.append(f"Contains {len(statements)} statements; only a single SELECT is expected.")
    first_word = re.match(r"\w+", cleaned)
    if not first_word or first_word.group(0).lower() not in {"select", "with"}:
        warnings.append("Does not start with SELECT or WITH, so it may not be a read-only query.")
    found = sorted({m.group(1).upper() for m in MUTATION_PATTERN.finditer(cleaned)})
    if found:
        warnings.append(
            "Contains keywords that can change data or session state: " + ", ".join(found) + "."
        )
    return warnings


async def run_readonly(pool, sql: str, max_rows: int) -> tuple[list[str], list[list], bool]:
    """Run SQL in a read-only transaction. Returns (columns, rows, truncated)."""
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            cur = await conn.execute(sql)
            if not cur.description:
                return [], [], False
            columns = [c.name for c in cur.description]
            fetched = await cur.fetchmany(max_rows + 1)
    truncated = len(fetched) > max_rows
    rows = [[row[c] for c in columns] for row in fetched[:max_rows]]
    return columns, rows, truncated


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return "<binary>"
    return value


def _normalize(value):
    value = jsonable(value)
    if isinstance(value, float):
        return round(value, 2)
    return value


def compare_rows(
    expected: list[list], actual: list[list], ordered: bool
) -> tuple[bool, list[list], list[list]]:
    """Compare rows ignoring column names. Floats are rounded to 2 decimals.

    Returns (equal, missing_rows, unexpected_rows).
    """
    exp = [tuple(_normalize(v) for v in row) for row in expected]
    act = [tuple(_normalize(v) for v in row) for row in actual]
    remaining = list(act)
    missing = []
    for row in exp:
        if row in remaining:
            remaining.remove(row)
        else:
            missing.append(list(row))
    unexpected = [list(row) for row in remaining]
    equal = not missing and not unexpected and (not ordered or exp == act)
    return equal, missing, unexpected
