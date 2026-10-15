"""Exercise migration safety and independently calculated benchmark answers."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from migrate.seed_sales import migrate, TABLES


class SalesMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, 'sales.sqlite')

    def database(self):
        migrate(self.path)
        connection = sqlite3.connect(self.path)
        self.addCleanup(connection.close)
        return connection

    def test_rerun_is_noop_and_reproduction_is_deterministic(self):
        created, counts = migrate(self.path)
        self.assertTrue(created)
        self.assertEqual(counts['orders'], 608)
        self.assertEqual(counts['customers'], 120)
        self.assertEqual(counts['products'], 12)
        original = self.path.read_bytes()
        self.assertEqual(migrate(self.path), (False, counts))
        self.assertEqual(self.path.read_bytes(), original)
        other = Path(self.directory.name, 'other.sqlite')
        migrate(other)
        with closing(sqlite3.connect(self.path)) as first, closing(sqlite3.connect(other)) as second:
            self.assertEqual(list(first.iterdump()), list(second.iterdump()))
            self.assertEqual(first.execute('PRAGMA foreign_key_check').fetchall(), [])
            for table in TABLES:
                self.assertGreater(counts[table], 0)

    def test_existing_unrelated_database_is_untouched(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('CREATE TABLE city_stats (city_name TEXT)')
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            migrate(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_seed_leaves_no_partial_database(self):
        with patch('migrate.seed_sales.seed', side_effect=RuntimeError('seed failed')):
            with self.assertRaisesRegex(RuntimeError, 'seed failed'):
                migrate(self.path)
        self.assertFalse(self.path.exists())
        self.assertTrue(migrate(self.path)[0])

    def test_payments_balance_without_counting_failed_attempts(self):
        database = self.database()
        mismatches = database.execute('''
            WITH items AS (
                SELECT order_id, SUM(quantity * unit_price_vnd - discount_vnd) AS amount
                FROM order_items GROUP BY order_id
            ), paid AS (
                SELECT order_id, SUM(amount_vnd) AS amount FROM payments
                WHERE status = 'succeeded' GROUP BY order_id
            )
            SELECT o.order_id FROM orders o JOIN items i USING (order_id)
            LEFT JOIN paid p USING (order_id)
            WHERE COALESCE(p.amount, 0) != CASE WHEN o.status = 'delivered'
                THEN i.amount + o.shipping_fee_vnd ELSE 0 END
        ''').fetchall()
        self.assertEqual(mismatches, [])
        self.assertEqual(database.execute(
            "SELECT status, SUM(amount_vnd) FROM payments WHERE order_id = 'DH1004' GROUP BY status"
        ).fetchall(), [('failed', 690000), ('succeeded', 690000)])
        self.assertEqual(database.execute('''
            SELECT SUM(refund_amount_vnd) FROM returns r JOIN order_items i USING (order_item_id)
            WHERE i.order_id = 'DH1004' AND r.status = 'refunded'
        ''').fetchone()[0], 180000)
        self.assertEqual(database.execute('''
            SELECT r.refunded_at FROM returns r JOIN order_items i USING (order_item_id)
            WHERE i.order_id = 'DH1004'
        ''').fetchone()[0], '2026-10-02')
        self.assertEqual(database.execute('''
            SELECT i.order_item_id FROM order_items i JOIN returns r USING (order_item_id)
            GROUP BY i.order_item_id
            HAVING SUM(r.quantity) > i.quantity OR SUM(r.refund_amount_vnd) >
                i.quantity * i.unit_price_vnd - i.discount_vnd
        ''').fetchall(), [])

    def test_shipping_audit_matches_published_policy(self):
        database = self.database()
        # Independent implementation of the two dated Markdown policies.
        violations = []
        for order_id, ordered, region, member, actual, subtotal in database.execute('''
            SELECT o.order_id, o.ordered_at, o.shipping_region, o.membership_at_purchase,
                   o.shipping_fee_vnd, SUM(i.quantity * i.unit_price_vnd - i.discount_vnd)
            FROM orders o JOIN order_items i USING (order_id)
            WHERE o.status = 'delivered' GROUP BY o.order_id
        '''):
            if region == 'remote':
                expected = 50000
            elif member == 'vip':
                expected = 0
            else:
                threshold = 700000 if ordered < '2026-09-01' else 500000
                expected = 0 if subtotal >= threshold else 30000
            if actual != expected:
                violations.append((order_id, actual - expected))
        self.assertEqual(violations, [('DH1002', 30000)])

    def test_missing_dates_and_policy_version_boundary_are_preserved(self):
        database = self.database()
        cases = database.execute('''
            SELECT o.order_id, o.ordered_at, julianday(r.requested_at) - julianday(o.delivered_at)
            FROM orders o JOIN order_items i USING (order_id) JOIN returns r USING (order_item_id)
            WHERE o.order_id IN ('DH1001', 'DH1002', 'DH1005') ORDER BY o.order_id
        ''').fetchall()
        self.assertEqual(cases, [('DH1001', '2026-08-31', 17.0),
                                 ('DH1002', '2026-09-01', 17.0), ('DH1005', '2026-09-11', None)])


if __name__ == '__main__':
    unittest.main()
