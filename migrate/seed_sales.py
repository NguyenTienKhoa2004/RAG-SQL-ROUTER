"""Create a separate sales database using only Python's standard library."""
import argparse
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import random
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / 'sales_database.sqlite'
APPLICATION_ID = 1396788293
VERSION = 1
TABLES = ('customers', 'products', 'orders', 'order_items', 'payments', 'returns')


def seed(connection):
    rng = random.Random(20261014)
    customers = [
        (f'KH{i:03}', 'Nguyễn Văn An' if i <= 2 else f'Khách mẫu {i:03}',
         f'customer{i:03}@example.invalid', ['Hà Nội', 'Đà Nẵng', 'TP.HCM'][i % 3])
        for i in range(1, 121)
    ]
    connection.executemany('INSERT INTO customers VALUES (?, ?, ?, ?)', customers)
    products = [
        ('SP01', 'Áo thun Basic', 'apparel', 200000),
        ('SP02', 'Áo khoác Light', 'apparel', 600000),
        ('SP03', 'Quần jeans Blue', 'apparel', 450000),
        ('SP04', 'Giày Daily', 'apparel', 800000),
        ('SP05', 'Tai nghe Air', 'electronics', 900000),
        ('SP06', 'Tai nghe Air Pro', 'electronics', 1500000),
        ('SP07', 'Chuột Silent', 'electronics', 300000),
        ('SP08', 'Bàn phím Mini', 'electronics', 700000),
        ('SP09', 'Bình nước Travel', 'home', 150000),
        ('SP10', 'Đèn bàn Study', 'home', 400000),
        ('SP11', 'Gối Soft', 'home', 250000),
        ('SP12', 'Chăn Warm', 'home', 650000),
    ]
    connection.executemany('INSERT INTO products VALUES (?, ?, ?, ?)', products)

    def add_order(order_id, customer, ordered, delivered, status, region, member, fee, items,
                  *, split=False, failed=False):
        connection.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (order_id, customer, ordered, delivered, status, region, member, fee))
        item_ids = []
        total = fee
        for product, quantity, price, discount, clearance in items:
            cursor = connection.execute(
                'INSERT INTO order_items (order_id, product_id, quantity, unit_price_vnd, '
                'discount_vnd, is_clearance) VALUES (?, ?, ?, ?, ?, ?)',
                (order_id, product, quantity, price, discount, clearance))
            item_ids.append(cursor.lastrowid)
            total += quantity * price - discount
        payments = []
        if failed:
            payments.append((order_id, ordered, total, 'failed', 'card'))
        if status == 'delivered':
            amounts = [total // 2, total - total // 2] if split else [total]
            payments.extend((order_id, ordered, amount, 'succeeded', 'bank_transfer') for amount in amounts)
        connection.executemany(
            'INSERT INTO payments (order_id, paid_at, amount_vnd, status, method) VALUES (?, ?, ?, ?, ?)', payments)
        return item_ids

    # Background orders: deterministic dates and discounts, no policy violations.
    for i in range(1, 601):
        ordered = date(2026, 8, 1) + timedelta(days=rng.randrange(61))
        status = 'cancelled' if i % 13 == 0 else 'pending' if i % 17 == 0 else 'delivered'
        region = 'remote' if i % 9 == 0 else 'standard'
        member = 'vip' if i % 7 == 0 else 'regular'
        items = []
        for product in rng.sample(products, rng.randint(1, 4)):
            quantity = rng.randint(1, 3)
            discount = product[3] * quantity // 10 if i % 5 == 0 else 0
            items.append((product[0], quantity, product[3], discount, int(i % 19 == 0)))
        subtotal = sum(qty * price - discount for _, qty, price, discount, _ in items)
        threshold = 700000 if ordered.month == 8 else 500000
        fee = 50000 if region == 'remote' else 0 if member == 'vip' or subtotal >= threshold else 30000
        add_order(f'DH{i:04}', f'KH{rng.randint(1, 120):03}', ordered.isoformat(),
                  (ordered + timedelta(days=3)).isoformat() if status == 'delivered' else None,
                  status, region, member, fee, items, split=i % 11 == 0, failed=i % 8 == 0)

    # Curated cases have stable IDs, independent of the background RNG.
    cases = [
        ('DH1001', 'KH001', '2026-08-31', '2026-09-03', 'standard', 'regular', 30000,
         [('SP02', 1, 600000, 0, 0)]),
        ('DH1002', 'KH002', '2026-09-01', '2026-09-04', 'standard', 'regular', 30000,
         [('SP02', 1, 600000, 0, 0)]),
        ('DH1003', 'KH003', '2026-09-05', '2026-09-08', 'remote', 'vip', 50000,
         [('SP05', 1, 900000, 0, 0)]),
        ('DH1004', 'KH004', '2026-09-10', '2026-09-13', 'standard', 'regular', 0,
         [('SP01', 3, 200000, 60000, 0), ('SP09', 1, 150000, 0, 0)]),
        ('DH1005', 'KH005', '2026-09-11', None, 'standard', 'regular', 30000,
         [('SP01', 1, 200000, 0, 0)]),
        ('DH1006', 'KH006', '2026-09-12', '2026-09-15', 'standard', 'regular', 30000,
         [('SP01', 1, 200000, 20000, 1)]),
        ('DH1007', 'KH007', '2026-09-12', '2026-09-15', 'standard', 'regular', 30000,
         [('SP01', 1, 200000, 20000, 1)]),
        ('DH1008', 'KH008', '2026-09-20', '2026-09-23', 'standard', 'regular', 30000,
         [('SP02', 1, 600000, 120000, 0)]),
    ]
    ids = {}
    for order_id, customer, ordered, delivered, region, member, fee, items in cases:
        ids[order_id] = add_order(order_id, customer, ordered, delivered, 'delivered',
                                  region, member, fee, items, split=order_id == 'DH1004',
                                  failed=order_id == 'DH1004')
    connection.executemany(
        'INSERT INTO returns (order_item_id, requested_at, quantity, reason, item_condition, '
        'status, refunded_at, refund_amount_vnd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [
            (ids['DH1001'][0], '2026-09-20', 1, 'change_of_mind', 'unused', 'requested', None, 0),
            (ids['DH1002'][0], '2026-09-21', 1, 'change_of_mind', 'unused', 'requested', None, 0),
            (ids['DH1004'][0], '2026-09-20', 1, 'defective', 'used', 'refunded', '2026-10-02', 180000),
            (ids['DH1005'][0], '2026-09-20', 1, 'change_of_mind', 'unused', 'requested', None, 0),
            (ids['DH1006'][0], '2026-09-20', 1, 'change_of_mind', 'unused', 'rejected', None, 0),
            (ids['DH1007'][0], '2026-09-20', 1, 'defective', 'used', 'requested', None, 0),
        ])


def validate(connection):
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Database integrity check failed')
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Foreign key check failed')
    return {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in TABLES}


def migrate(path=DEFAULT_DATABASE):
    path = Path(path).resolve()
    if path.exists():
        with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as connection:
            identity = connection.execute('PRAGMA application_id').fetchone()[0]
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if (identity, version) != (APPLICATION_ID, VERSION):
                raise ValueError(f'Refusing to overwrite an existing or unsupported database: {path}')
            return False, validate(connection)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new file exclusively; never overwrite a database created by another process.
    with path.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('PRAGMA foreign_keys = ON')
            connection.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
            try:
                seed(connection)
                counts = validate(connection)
                connection.execute(f'PRAGMA application_id = {APPLICATION_ID}')
                connection.execute(f'PRAGMA user_version = {VERSION}')
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    created, counts = migrate(args.database)
    print(f'{"Created" if created else "Already migrated"}: {args.database.resolve()}')
    for table, count in counts.items():
        print(f'  {table}: {count}')


if __name__ == '__main__':
    main()
