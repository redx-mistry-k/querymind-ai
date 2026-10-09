import pytest

from backend.app.services.sql.validator import SQLValidator


@pytest.fixture
def validator():
    return SQLValidator(max_rows=100)


@pytest.fixture
def tables():
    return {"orders", "customers", "order_items", "products"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "WITH totals AS (SELECT customer_id, COUNT(*) n FROM orders GROUP BY customer_id) SELECT * FROM totals",
        "SELECT customer_id, ROW_NUMBER() OVER (ORDER BY id) AS rn FROM orders",
        "SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers)",
    ],
)
def test_allows_read_only_analytics(validator, tables, sql):
    result = validator.validate(sql, "sqlite", tables)
    assert result.valid, result.errors
    assert "LIMIT 101" in result.normalized_sql


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders(id) VALUES (1)",
        "UPDATE orders SET customer_id = 2",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "CREATE TABLE bad(id int)",
        "ALTER TABLE orders ADD COLUMN bad text",
    ],
)
def test_rejects_unsafe_statements(validator, tables, sql):
    assert not validator.validate(sql, "sqlite", tables).valid


def test_rejects_writable_cte(validator, tables):
    sql = "WITH changed AS (DELETE FROM orders RETURNING id) SELECT * FROM changed"
    assert not validator.validate(sql, "postgres", tables).valid


def test_rejects_multiple_statements(validator, tables):
    result = validator.validate("SELECT * FROM orders; DROP TABLE orders", "sqlite", tables)
    assert not result.valid
    assert "Exactly one" in result.errors[0]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT load_extension('evil')",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_sleep(10)",
    ],
)
def test_rejects_dangerous_functions(validator, tables, sql):
    dialect = "postgres" if "pg_" in sql else "sqlite"
    assert not validator.validate(sql, dialect, tables).valid


def test_rejects_unauthorized_tables_and_schemas(validator, tables):
    assert not validator.validate("SELECT * FROM secrets", "sqlite", tables).valid
    assert not validator.validate(
        "SELECT * FROM private.orders", "postgres", tables, {"public"}
    ).valid
    assert not validator.validate(
        "SELECT * FROM pg_catalog.pg_user", "postgres", {"pg_user"}, {"public"}
    ).valid


def test_rejects_select_into(validator, tables):
    assert not validator.validate("SELECT * INTO backup FROM orders", "postgres", tables).valid


def test_rejects_row_locks_and_unknown_qualified_columns(validator, tables):
    assert not validator.validate("SELECT * FROM orders FOR UPDATE", "postgres", tables).valid
    result = validator.validate(
        "SELECT o.made_up FROM orders o",
        "sqlite",
        tables,
        allowed_columns={"orders": {"id", "customer_id"}},
    )
    assert not result.valid


def test_comments_cannot_hide_additional_or_nested_mutations(validator, tables):
    multi = "SELECT * FROM orders /* harmless */; -- bypass\nDELETE FROM orders"
    assert not validator.validate(multi, "sqlite", tables).valid
    nested = "SELECT * FROM (DELETE FROM orders RETURNING id) AS removed"
    assert not validator.validate(nested, "postgres", tables).valid


def test_comment_text_is_not_treated_as_an_operation(validator, tables):
    result = validator.validate("SELECT * FROM orders /* DROP TABLE orders */", "sqlite", tables)
    assert result.valid
