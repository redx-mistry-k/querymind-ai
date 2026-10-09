from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE regions (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE categories (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    region_id INTEGER NOT NULL REFERENCES regions(id), joined_date DATE NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(id),
    unit_price NUMERIC NOT NULL CHECK(unit_price > 0), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL, status TEXT NOT NULL CHECK(status IN ('completed','cancelled','refunded','pending'))
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price NUMERIC NOT NULL CHECK(unit_price > 0)
);
CREATE TABLE payments (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    amount NUMERIC NOT NULL, payment_method TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('paid','failed','refunded','pending')), paid_at DATETIME
);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
"""


def _valid_demo_database(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            required = {
                "regions",
                "categories",
                "customers",
                "products",
                "orders",
                "order_items",
                "payments",
            }
            return (
                required.issubset(tables)
                and connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] > 10_000
            )
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def create_demo_database(path: Path, force: bool = False) -> Path:
    if path.exists() and not force and _valid_demo_database(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    engine = create_engine(f"sqlite:///{path}")
    rng = random.Random(7429)
    regions = ["North", "South", "East", "West", "Central", "International"]
    categories = ["Electronics", "Home", "Office", "Sports", "Books", "Wellness"]
    product_roots = {
        "Electronics": [
            "Wireless Headphones",
            "Smart Speaker",
            "4K Monitor",
            "Webcam",
            "Power Bank",
        ],
        "Home": ["Desk Lamp", "Coffee Grinder", "Air Purifier", "Throw Blanket", "Storage Set"],
        "Office": [
            "Ergonomic Chair",
            "Standing Desk",
            "Notebook Set",
            "Mechanical Keyboard",
            "Mouse",
        ],
        "Sports": ["Yoga Mat", "Resistance Bands", "Water Bottle", "Running Belt", "Foam Roller"],
        "Books": [
            "Data Handbook",
            "Design Systems",
            "Leadership Guide",
            "SQL Workbook",
            "AI Primer",
        ],
        "Wellness": [
            "Sleep Mask",
            "Massage Pillow",
            "Diffuser",
            "Fitness Tracker",
            "Meditation Cushion",
        ],
    }
    with engine.begin() as conn:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
        conn.execute(
            text("INSERT INTO regions(id,name) VALUES (:id,:name)"),
            [{"id": i + 1, "name": name} for i, name in enumerate(regions)],
        )
        conn.execute(
            text("INSERT INTO categories(id,name) VALUES (:id,:name)"),
            [{"id": i + 1, "name": name} for i, name in enumerate(categories)],
        )
        products: list[dict[str, object]] = []
        product_id = 1
        for category_id, category in enumerate(categories, 1):
            for variant in range(4):
                for root in product_roots[category]:
                    products.append(
                        {
                            "id": product_id,
                            "name": f"{root} {chr(65 + variant)}",
                            "category_id": category_id,
                            "unit_price": round(
                                rng.uniform(12, 420) * (1.3 if category == "Electronics" else 1), 2
                            ),
                        }
                    )
                    product_id += 1
        conn.execute(
            text(
                "INSERT INTO products(id,name,category_id,unit_price) VALUES (:id,:name,:category_id,:unit_price)"
            ),
            products,
        )
        first_names = [
            "Aarav",
            "Maya",
            "Noah",
            "Emma",
            "Liam",
            "Olivia",
            "Ethan",
            "Zara",
            "Leo",
            "Sofia",
        ]
        last_names = [
            "Shah",
            "Chen",
            "Patel",
            "Garcia",
            "Kim",
            "Smith",
            "Martin",
            "Khan",
            "Brown",
            "Silva",
        ]
        customers = []
        start_join = date(2022, 1, 1)
        for customer_id in range(1, 801):
            name = f"{rng.choice(first_names)} {rng.choice(last_names)}"
            customers.append(
                {
                    "id": customer_id,
                    "name": name,
                    "email": f"customer{customer_id}@example.test",
                    "region_id": rng.randint(1, len(regions)),
                    "joined_date": start_join + timedelta(days=rng.randint(0, 1000)),
                }
            )
        conn.execute(
            text("INSERT INTO customers VALUES (:id,:name,:email,:region_id,:joined_date)"),
            customers,
        )
        orders, items, payments = [], [], []
        order_start = date(2024, 1, 1)
        item_id = 1
        for order_id in range(1, 5001):
            order_date = order_start + timedelta(days=rng.randint(0, 850))
            status = rng.choices(
                ["completed", "cancelled", "refunded", "pending"], weights=[87, 6, 3, 4]
            )[0]
            orders.append(
                {
                    "id": order_id,
                    "customer_id": rng.randint(1, 800),
                    "order_date": order_date,
                    "status": status,
                }
            )
            total = 0.0
            for _ in range(rng.randint(1, 4)):
                product = rng.choice(products)
                qty = rng.choices([1, 2, 3, 4], weights=[55, 28, 12, 5])[0]
                # Gradual growth and a modest Q4 lift create useful, non-random trends.
                seasonal = 1.08 if order_date.month in {10, 11, 12} else 1.0
                price = round(float(product["unit_price"]) * seasonal, 2)
                items.append(
                    {
                        "id": item_id,
                        "order_id": order_id,
                        "product_id": product["id"],
                        "quantity": qty,
                        "unit_price": price,
                    }
                )
                item_id += 1
                total += qty * price
            payment_status = {
                "completed": "paid",
                "cancelled": "failed",
                "refunded": "refunded",
                "pending": "pending",
            }[status]
            payments.append(
                {
                    "id": order_id,
                    "order_id": order_id,
                    "amount": round(total, 2),
                    "payment_method": rng.choice(["card", "bank_transfer", "wallet", "cash"]),
                    "status": payment_status,
                    "paid_at": order_date.isoformat()
                    if payment_status in {"paid", "refunded"}
                    else None,
                }
            )
        conn.execute(
            text("INSERT INTO orders VALUES (:id,:customer_id,:order_date,:status)"), orders
        )
        conn.execute(
            text(
                "INSERT INTO order_items VALUES (:id,:order_id,:product_id,:quantity,:unit_price)"
            ),
            items,
        )
        conn.execute(
            text(
                "INSERT INTO payments VALUES (:id,:order_id,:amount,:payment_method,:status,:paid_at)"
            ),
            payments,
        )
    engine.dispose()
    return path
