"""Fixed, read-only queries used by the database browser, separate from the agent."""
import sqlite3
from contextlib import closing
from pathlib import Path
from .schemas import DatabaseView


# SQL identifiers come only from this allowlist, never directly from request data.
TABLE_COLUMNS = {
    "orders": ["order_id", "customer_id", "customer_name", "ordered_at", "delivered_at", "status",
               "shipping_region", "membership_at_purchase", "merchandise_total_vnd", "shipping_fee_vnd"],
    "customers": ["customer_id", "full_name", "email", "city"],
    "products": ["product_id", "name", "category", "list_price_vnd"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price_vnd",
                    "discount_vnd", "is_clearance"],
    "payments": ["payment_id", "order_id", "paid_at", "amount_vnd", "status", "method"],
    "returns": ["return_id", "order_item_id", "requested_at", "quantity", "reason", "item_condition",
                "status", "refunded_at", "refund_amount_vnd"],
}


def read_sales_database(path: Path, page=1, page_size=20, search="", table="orders") -> DatabaseView:
    if table not in TABLE_COLUMNS:
        raise ValueError("Unsupported sales table")
    columns = TABLE_COLUMNS[table]
    if table == "orders":
        source = (
            "(SELECT o.*, c.full_name AS customer_name, "
            "(SELECT SUM(i.quantity * i.unit_price_vnd - i.discount_vnd) "
            "FROM order_items i WHERE i.order_id = o.order_id) AS merchandise_total_vnd "
            "FROM orders o JOIN customers c ON c.customer_id = o.customer_id)"
        )
        ordering = "ordered_at DESC, order_id"
    else:
        source = table
        ordering = columns[0]
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        term = f"%{search}%"
        where = "WHERE " + " OR ".join(f"CAST({column} AS TEXT) LIKE ?" for column in columns)
        parameters = [term] * len(columns)
        total = connection.execute(
            f"SELECT COUNT(*) FROM {source} {where}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT {', '.join(columns)} FROM {source} {where} "
            f"ORDER BY {ordering} LIMIT ? OFFSET ?",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
        return DatabaseView(
            table=table, columns=columns,
            rows=[dict(row) for row in rows], total=total,
            total_customers=connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            total_products=connection.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            page=page, page_size=page_size,
        )
