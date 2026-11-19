"""Webhook provider authenticity and at-most-once settlement regressions."""
import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot"))
from webhook_handler import WebhookHandler, _verify_provider_notification
from database import db


PAYMENT_ID = "11111111-1111-4111-8111-111111111111"
REFUND_ID = "22222222-2222-4222-8222-222222222222"


class MockResponse:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


def provider_payment(payment_id=PAYMENT_ID, status="succeeded",
                     paid=True, amount="1000.00"):
    return {
        "id": payment_id, "status": status, "paid": paid,
        "amount": {"value": amount, "currency": "RUB"},
    }


def payload_event(payment_id=PAYMENT_ID, amount="1000.00",
                  event="payment.succeeded"):
    return {
        "type": "notification", "event": event,
        "object": {"id": payment_id,
                   "amount": {"value": amount, "currency": "RUB"}},
    }


class ProviderVerificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for name, value in (("YOOKASSA_SHOP_ID", "test-shop"),
                            ("YOOKASSA_SECRET_KEY", "test-secret")):
            patcher = patch("webhook_handler.config." + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_payment_succeeded_rechecks_remote_state_and_amount(self):
        with patch("webhook_handler.requests.get", return_value=MockResponse(provider_payment())):
            self.assertTrue(await _verify_provider_notification(
                "payment.succeeded", payload_event()["object"]
            ))

    async def test_forged_unpaid_or_mismatched_notifications_are_rejected(self):
        for provider in (
            provider_payment(status="pending", paid=False),
            provider_payment(payment_id="another-id"),
            provider_payment(amount="999.00"),
        ):
            with self.subTest(provider=provider), patch(
                "webhook_handler.requests.get",
                return_value=MockResponse(provider),
            ):
                self.assertFalse(await _verify_provider_notification(
                    "payment.succeeded", payload_event()["object"]
                ))

    async def test_refund_notification_verifies_actual_provider_refund(self):
        refund = {
            "id": REFUND_ID, "status": "succeeded", "payment_id": PAYMENT_ID,
            "amount": {"value": "1000.00", "currency": "RUB"},
        }
        obj = {
            "id": REFUND_ID, "payment_id": PAYMENT_ID,
            "amount": {"value": "1000.00", "currency": "RUB"},
        }
        with patch("webhook_handler.requests.get", return_value=MockResponse(refund)):
            self.assertTrue(await _verify_provider_notification("refund.succeeded", obj))
            self.assertFalse(await _verify_provider_notification(
                "refund.succeeded", dict(obj, payment_id="forged")
            ))

    async def test_transient_provider_timeout_retries_once_then_verifies(self):
        import requests
        with patch(
            "webhook_handler.requests.get",
            side_effect=[
                requests.exceptions.ReadTimeout("mock transient timeout"),
                MockResponse(provider_payment()),
            ],
        ) as lookup:
            self.assertTrue(await _verify_provider_notification(
                "payment.succeeded", payload_event()["object"]
            ))
            self.assertEqual(lookup.call_count, 2)
            for call in lookup.call_args_list:
                self.assertEqual(call.kwargs["timeout"], (4, 6))

    async def test_missing_object_never_verifies(self):
        self.assertFalse(await _verify_provider_notification("payment.succeeded", {}))


class SettlementIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for name, value in (("YOOKASSA_SHOP_ID", "test-shop"),
                            ("YOOKASSA_SECRET_KEY", "test-secret")):
            patcher = patch("webhook_handler.config." + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original_db_path = db.db_path
        db.db_path = str(Path(self.temp.name) / "payments.db")
        self.addCleanup(setattr, db, "db_path", self.original_db_path)
        connection = sqlite3.connect(db.db_path)
        connection.executescript("""
            CREATE TABLE payments (
                payment_id TEXT PRIMARY KEY, user_id INTEGER,
                subscription_id INTEGER, plan_id TEXT, status TEXT,
                amount INTEGER, paid_at TEXT
            );
            CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, status TEXT);
            INSERT INTO payments VALUES ('11111111-1111-4111-8111-111111111111', 100, 10, 'month', 'pending', 1000, NULL);
            INSERT INTO subscriptions VALUES (10, 'pending');
        """)
        connection.close()

    async def test_duplicate_success_activates_once(self):
        handler = WebhookHandler()
        calls = []
        async def notify(*args):
            calls.append(args)
        handler._notify_payment_success = notify
        with patch("webhook_handler.requests.get", return_value=MockResponse(provider_payment())):
            await handler.handle_payment_succeeded(payload_event())
            await handler.handle_payment_succeeded(payload_event())
        with sqlite3.connect(db.db_path) as connection:
            status, = connection.execute(
                "SELECT status FROM payments WHERE payment_id = '11111111-1111-4111-8111-111111111111'"
            ).fetchone()
            subscription, = connection.execute(
                "SELECT status FROM subscriptions WHERE id = 10"
            ).fetchone()
        self.assertEqual((status, subscription), ("succeeded", "active"))
        self.assertEqual(len(calls), 1)

    async def test_http_webhook_forbidden_when_remote_unpaid(self):
        handler = WebhookHandler()
        with patch("webhook_handler.requests.get",
                   return_value=MockResponse(provider_payment(status="pending", paid=False))):
            async with TestClient(TestServer(handler.app)) as client:
                response = await client.post("/webhook/yookassa", json=payload_event())
                self.assertEqual(response.status, 403)
        with sqlite3.connect(db.db_path) as connection:
            status, = connection.execute(
                "SELECT status FROM payments WHERE payment_id = '11111111-1111-4111-8111-111111111111'"
            ).fetchone()
        self.assertEqual(status, "pending")

    async def test_http_webhook_returns_503_if_provider_lookup_unavailable(self):
        handler = WebhookHandler()
        with patch("webhook_handler.requests.get",
                   side_effect=TimeoutError("simulated outage")):
            async with TestClient(TestServer(handler.app)) as client:
                response = await client.post("/webhook/yookassa", json=payload_event())
                self.assertEqual(response.status, 503)

    async def test_http_webhook_verified_success_is_idempotent(self):
        handler = WebhookHandler()
        calls = []
        async def notify(*args):
            calls.append(args)
        handler._notify_payment_success = notify
        with patch("webhook_handler.requests.get", return_value=MockResponse(provider_payment())):
            async with TestClient(TestServer(handler.app)) as client:
                for _ in range(2):
                    response = await client.post("/webhook/yookassa", json=payload_event())
                    self.assertEqual(response.status, 200)
        with sqlite3.connect(db.db_path) as connection:
            payment_status, = connection.execute(
                "SELECT status FROM payments WHERE payment_id = '11111111-1111-4111-8111-111111111111'"
            ).fetchone()
            sub_status, = connection.execute(
                "SELECT status FROM subscriptions WHERE id = 10"
            ).fetchone()
        self.assertEqual((payment_status, sub_status), ("succeeded", "active"))
        self.assertEqual(len(calls), 1)

    async def test_amount_mismatch_prevents_local_activation(self):
        handler = WebhookHandler()
        with self.assertRaises(ValueError):
            await handler.handle_payment_succeeded(payload_event(amount="800.00"))
        with sqlite3.connect(db.db_path) as connection:
            status, = connection.execute(
                "SELECT status FROM payments WHERE payment_id = '11111111-1111-4111-8111-111111111111'"
            ).fetchone()
        self.assertEqual(status, "pending")


if __name__ == "__main__":
    unittest.main()
