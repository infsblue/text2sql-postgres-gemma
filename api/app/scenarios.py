"""Preconfigured tests for the text-to-SQL endpoints (Northwind sample database).

Each test has a plain-language question and a hand-written *reference SQL*. At run time the
reference SQL is executed too, and the rows produced by the model's SQL are compared with
the reference rows. The user sees both, so the verdict can be checked by eye.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextToSqlTest:
    slug: str
    title: str
    purpose: str
    question: str
    reference_sql: str
    ordered: bool = False


TESTS: dict[str, TextToSqlTest] = {t.slug: t for t in [
    TextToSqlTest(
        slug="count-customers",
        title="Simple aggregate: how many customers?",
        purpose="Smallest possible test: one table, one COUNT. Expected result is a single "
        "row with a single number.",
        question="How many customers are there?",
        reference_sql="SELECT count(*) FROM customers",
    ),
    TextToSqlTest(
        slug="customers-in-brazil",
        title="Filter: customers located in Brazil",
        purpose="One table with a WHERE filter on a text column. Expected result is the list "
        "of company names (row order does not matter).",
        question="List the company names of customers located in Brazil.",
        reference_sql="SELECT company_name FROM customers WHERE country = 'Brazil'",
    ),
    TextToSqlTest(
        slug="most-expensive-product",
        title="Sorting and LIMIT: the most expensive product",
        purpose="ORDER BY ... DESC with LIMIT 1. Expected result is a single product name.",
        question="What is the name of the product with the highest unit price?",
        reference_sql="SELECT product_name FROM products ORDER BY unit_price DESC LIMIT 1",
        ordered=True,
    ),
    TextToSqlTest(
        slug="products-per-category",
        title="JOIN + GROUP BY: products in each category",
        purpose="Needs the products -> categories foreign key. Expected result is one row "
        "per category with its product count (row order does not matter).",
        question="How many products are in each category? Show the category name and the count.",
        reference_sql=(
            "SELECT c.category_name, count(*) FROM products p "
            "JOIN categories c ON c.category_id = p.category_id GROUP BY c.category_name"
        ),
    ),
    TextToSqlTest(
        slug="top-customers-by-orders",
        title="JOIN + GROUP BY + ORDER BY + LIMIT: top 3 customers by number of orders",
        purpose="Ranking. Expected result is exactly 3 rows, highest order count first, so "
        "row order IS checked.",
        question="Which 3 customers placed the most orders? Show the company name and the "
        "number of orders, highest first.",
        reference_sql=(
            "SELECT c.company_name, count(*) FROM orders o "
            "JOIN customers c ON c.customer_id = o.customer_id "
            "GROUP BY c.company_name ORDER BY count(*) DESC LIMIT 3"
        ),
        ordered=True,
    ),
    TextToSqlTest(
        slug="revenue-per-category",
        title="Three-table JOIN with arithmetic: revenue per category",
        purpose="The hardest test: order_details -> products -> categories, with a revenue "
        "formula. Numbers are compared rounded to 2 decimals (row order does not matter).",
        question=(
            "What is the total revenue for each product category? Revenue is "
            "unit_price * quantity * (1 - discount) summed over order_details. "
            "Show the category name and the revenue."
        ),
        reference_sql=(
            "SELECT c.category_name, sum(od.unit_price * od.quantity * (1 - od.discount)) "
            "FROM order_details od "
            "JOIN products p ON p.product_id = od.product_id "
            "JOIN categories c ON c.category_id = p.category_id GROUP BY c.category_name"
        ),
    ),
]}
