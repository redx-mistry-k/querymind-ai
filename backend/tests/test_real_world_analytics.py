from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from backend.app.services.sql.validator import SQLValidator

TOP_CUSTOMERS_SQL = """
SELECT c.id, c.name AS customer,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'completed'
GROUP BY c.id, c.name
ORDER BY revenue DESC, c.id
LIMIT 10
"""

ANALYTICS_QUERIES = {
    "monthly_revenue": """
        SELECT strftime('%Y-%m', o.order_date) AS month,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM orders o JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status = 'completed' GROUP BY month ORDER BY month
    """,
    "top_products": """
        SELECT p.name AS product, SUM(oi.quantity) AS units,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM products p JOIN order_items oi ON oi.product_id = p.id
        JOIN orders o ON o.id = oi.order_id WHERE o.status = 'completed'
        GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 10
    """,
    "revenue_by_region": """
        SELECT r.name AS region, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM regions r JOIN customers c ON c.region_id = r.id
        JOIN orders o ON o.customer_id = c.id JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status = 'completed' GROUP BY r.id, r.name ORDER BY revenue DESC
    """,
    "average_order_value": """
        WITH order_totals AS (
          SELECT o.id, SUM(oi.quantity * oi.unit_price) AS total
          FROM orders o JOIN order_items oi ON oi.order_id = o.id
          WHERE o.status = 'completed' GROUP BY o.id
        ) SELECT ROUND(AVG(total), 2) AS average_order_value FROM order_totals
    """,
    "cancelled_by_month": """
        SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) AS cancelled_orders
        FROM orders WHERE status = 'cancelled' GROUP BY month ORDER BY month
    """,
    "customer_trends": """
        SELECT c.name AS customer, COUNT(DISTINCT o.id) AS orders,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM customers c JOIN orders o ON o.customer_id = c.id
        JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'completed'
        GROUP BY c.id, c.name ORDER BY revenue DESC LIMIT 20
    """,
    "year_over_year": """
        SELECT substr(o.order_date, 1, 4) AS year,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM orders o JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status = 'completed' GROUP BY year ORDER BY year
    """,
    "category_join": """
        SELECT c.name AS category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM categories c JOIN products p ON p.category_id = c.id
        JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id
        WHERE o.status = 'completed' GROUP BY c.id, c.name ORDER BY revenue DESC
    """,
    "window_rank": """
        WITH product_revenue AS (
          SELECT c.name AS category, p.name AS product,
                 SUM(oi.quantity * oi.unit_price) AS revenue
          FROM categories c JOIN products p ON p.category_id = c.id
          JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id
          WHERE o.status = 'completed' GROUP BY c.id, c.name, p.id, p.name
        ) SELECT category, product, ROUND(revenue, 2) AS revenue,
                 DENSE_RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rank
          FROM product_revenue ORDER BY category, rank, product
    """,
}


def load_tables(connection):
    return {
        name: pd.read_sql_query(f"SELECT * FROM {name}", connection)
        for name in ("customers", "orders", "order_items", "products", "categories", "regions")
    }


def test_top_customers_matches_independent_pandas_calculation(demo_path):
    connection = sqlite3.connect(demo_path)
    try:
        actual = pd.read_sql_query(TOP_CUSTOMERS_SQL, connection)
        tables = load_tables(connection)
    finally:
        connection.close()
    completed = tables["orders"].loc[tables["orders"]["status"] == "completed"]
    joined = completed.merge(tables["order_items"], left_on="id", right_on="order_id")
    joined["revenue"] = joined["quantity"] * joined["unit_price"]
    expected = (
        joined.groupby("customer_id", as_index=False)["revenue"]
        .sum()
        .merge(tables["customers"][["id", "name"]], left_on="customer_id", right_on="id")
        .rename(columns={"name": "customer"})
        .sort_values(["revenue", "id"], ascending=[False, True])
        .head(10)[["id", "customer", "revenue"]]
        .reset_index(drop=True)
    )
    expected["revenue"] = expected["revenue"].round(2)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_core_analytics_match_independent_aggregations(demo_path):
    connection = sqlite3.connect(demo_path)
    try:
        tables = load_tables(connection)
        monthly = pd.read_sql_query(ANALYTICS_QUERIES["monthly_revenue"], connection)
        regions = pd.read_sql_query(ANALYTICS_QUERIES["revenue_by_region"], connection)
        average = pd.read_sql_query(ANALYTICS_QUERIES["average_order_value"], connection)
        yearly = pd.read_sql_query(ANALYTICS_QUERIES["year_over_year"], connection)
    finally:
        connection.close()
    completed = tables["orders"].loc[tables["orders"]["status"] == "completed"].copy()
    joined = completed.merge(tables["order_items"], left_on="id", right_on="order_id")
    joined["revenue"] = joined["quantity"] * joined["unit_price"]
    joined["month"] = joined["order_date"].str[:7]
    joined["year"] = joined["order_date"].str[:4]
    expected_monthly = joined.groupby("month")["revenue"].sum().round(2)
    assert monthly.set_index("month")["revenue"].to_dict() == pytest.approx(
        expected_monthly.to_dict()
    )
    customer_regions = tables["customers"][["id", "region_id"]].rename(
        columns={"id": "customer_id"}
    )
    region_names = tables["regions"][["id", "name"]].rename(
        columns={"id": "region_id", "name": "region"}
    )
    region_joined = joined.merge(customer_regions, on="customer_id").merge(
        region_names, on="region_id"
    )
    expected_regions = region_joined.groupby("region")["revenue"].sum().round(2)
    assert regions.set_index("region")["revenue"].to_dict() == pytest.approx(
        expected_regions.to_dict()
    )
    expected_average = joined.groupby("id_x")["revenue"].sum().mean()
    assert average.iloc[0]["average_order_value"] == pytest.approx(round(expected_average, 2))
    expected_yearly = joined.groupby("year")["revenue"].sum().round(2)
    assert yearly.set_index("year")["revenue"].to_dict() == pytest.approx(expected_yearly.to_dict())


@pytest.mark.parametrize("query_name", list(ANALYTICS_QUERIES))
def test_real_world_queries_validate_and_execute(demo_path, query_name):
    connection = sqlite3.connect(demo_path)
    try:
        columns = {
            table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for table in ("customers", "orders", "order_items", "products", "categories", "regions")
        }
        validation = SQLValidator(max_rows=1000).validate(
            ANALYTICS_QUERIES[query_name],
            "sqlite",
            set(columns),
            allowed_columns=columns,
        )
        assert validation.valid, validation.errors
        result = pd.read_sql_query(validation.normalized_sql, connection)
        assert not result.empty
    finally:
        connection.close()
