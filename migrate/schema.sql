-- Synthetic sales benchmark v1. Money is integer VND; dates are ISO YYYY-MM-DD.
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL
);
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('apparel', 'electronics', 'home')),
    list_price_vnd INTEGER NOT NULL CHECK (list_price_vnd > 0)
);
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    ordered_at TEXT NOT NULL,
    delivered_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('delivered', 'cancelled', 'pending')),
    shipping_region TEXT NOT NULL CHECK (shipping_region IN ('standard', 'remote')),
    membership_at_purchase TEXT NOT NULL CHECK (membership_at_purchase IN ('regular', 'vip')),
    shipping_fee_vnd INTEGER NOT NULL CHECK (shipping_fee_vnd >= 0),
    CHECK (delivered_at IS NULL OR delivered_at >= ordered_at)
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd INTEGER NOT NULL CHECK (unit_price_vnd > 0),
    discount_vnd INTEGER NOT NULL DEFAULT 0 CHECK (discount_vnd >= 0),
    is_clearance INTEGER NOT NULL DEFAULT 0 CHECK (is_clearance IN (0, 1)),
    CHECK (discount_vnd <= quantity * unit_price_vnd)
);
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    paid_at TEXT NOT NULL,
    amount_vnd INTEGER NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    method TEXT NOT NULL CHECK (method IN ('card', 'bank_transfer', 'cod'))
);
CREATE TABLE returns (
    return_id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL REFERENCES order_items(order_item_id),
    requested_at TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    reason TEXT NOT NULL CHECK (reason IN ('change_of_mind', 'defective')),
    item_condition TEXT NOT NULL CHECK (item_condition IN ('unused', 'used', 'unknown')),
    status TEXT NOT NULL CHECK (status IN ('requested', 'rejected', 'refunded')),
    refunded_at TEXT,
    refund_amount_vnd INTEGER NOT NULL DEFAULT 0 CHECK (refund_amount_vnd >= 0),
    CHECK ((status = 'refunded' AND refunded_at IS NOT NULL AND refund_amount_vnd > 0)
        OR (status != 'refunded' AND refunded_at IS NULL AND refund_amount_vnd = 0)),
    CHECK (refunded_at IS NULL OR refunded_at >= requested_at)
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(ordered_at);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_returns_item ON returns(order_item_id);
