"""Load the Northwind sample database into Postgres (all 14 tables).

Runs once as a one-shot compose service. It is idempotent: if Northwind is already
present it does nothing, so restarting the stack never wipes data.
"""

import os
import sys
import time
import urllib.request

import psycopg

# Pinned to a commit so the dataset is reproducible.
NORTHWIND_COMMIT = "4aa7967a33b84e693db56d4c23ada410a3ff04a6"
NORTHWIND_URL = (
    "https://raw.githubusercontent.com/pthom/northwind_psql/"
    f"{NORTHWIND_COMMIT}/northwind.sql"
)
EXPECTED_TABLES = {
    "categories",
    "customer_customer_demo",
    "customer_demographics",
    "customers",
    "employee_territories",
    "employees",
    "order_details",
    "orders",
    "products",
    "region",
    "shippers",
    "suppliers",
    "territories",
    "us_states",
}


def log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def existing_tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    ).fetchall()
    return {row[0] for row in rows}


def download_sql(attempts: int = 5) -> str:
    for attempt in range(1, attempts + 1):
        try:
            log(f"downloading {NORTHWIND_URL}")
            with urllib.request.urlopen(NORTHWIND_URL, timeout=60) as response:
                return response.read().decode("utf-8")
        except OSError as exc:
            log(f"download failed ({exc}); attempt {attempt}/{attempts}")
            time.sleep(3 * attempt)
    raise SystemExit("could not download the Northwind script")


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        present = existing_tables(conn)
        if EXPECTED_TABLES <= present:
            log("Northwind already loaded; nothing to do")
            return

        # The upstream script starts with DROP TABLE IF EXISTS for its own tables,
        # which also replaces same-named tables from the previous sample schema.
        # That schema's order_items table references orders and is not part of
        # Northwind, so it must go first or the DROP of orders would fail.
        # The transaction is atomic: a failure leaves the database untouched.
        if "order_items" in present:
            log("removing legacy order_items table from the previous sample schema")
            conn.execute("DROP TABLE order_items")
        conn.execute(download_sql())
        missing = EXPECTED_TABLES - existing_tables(conn)
        if missing:
            raise SystemExit(f"Northwind load incomplete, missing: {sorted(missing)}")

        counts = {
            table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in sorted(EXPECTED_TABLES)
        }
    log("loaded Northwind: " + ", ".join(f"{t}={n}" for t, n in counts.items()))


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        print(f"[bootstrap] database error: {exc}", file=sys.stderr)
        raise SystemExit(1)
