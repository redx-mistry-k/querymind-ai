from sqlalchemy import create_engine, inspect, text


def test_demo_database_has_realistic_volume(demo_path):
    engine = create_engine(f"sqlite:///{demo_path}")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "categories",
        "customers",
        "order_items",
        "orders",
        "payments",
        "products",
        "regions",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM orders")) == 5000
        assert connection.scalar(text("SELECT COUNT(*) FROM order_items")) > 10_000
        assert connection.scalar(text("SELECT COUNT(*) FROM customers")) == 800


def test_demo_generation_is_deterministic(tmp_path):
    from backend.app.services.database.demo import create_demo_database

    first = create_demo_database(tmp_path / "first.db")
    second = create_demo_database(tmp_path / "second.db")
    engine1 = create_engine(f"sqlite:///{first}")
    engine2 = create_engine(f"sqlite:///{second}")
    sql = text("SELECT ROUND(SUM(amount), 2) FROM payments")
    with engine1.connect() as c1, engine2.connect() as c2:
        assert c1.scalar(sql) == c2.scalar(sql)


def test_corrupt_demo_database_is_repaired(tmp_path):
    from backend.app.services.database.demo import create_demo_database

    path = tmp_path / "corrupt.db"
    path.write_bytes(b"not a sqlite database")
    create_demo_database(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM orders")) == 5000
