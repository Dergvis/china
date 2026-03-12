import json
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from app.server import AppHandler


class E2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 18080), AppHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def post(self, path, payload):
        conn = HTTPConnection("127.0.0.1", 18080)
        conn.request("POST", path, body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode())
        conn.close()
        return response.status, body

    def get(self, path):
        conn = HTTPConnection("127.0.0.1", 18080)
        conn.request("GET", path)
        response = conn.getresponse()
        body = json.loads(response.read().decode())
        conn.close()
        return response.status, body

    def test_full_flow(self):
        user_id = "u100"
        s, body = self.post("/kyc/ocr", {"user_id": user_id, "image": "base64"})
        self.assertEqual(200, s)
        self.assertEqual("passport", body["document_type"])

        s, body = self.post("/kyc/liveness/start", {"user_id": user_id})
        self.assertEqual(200, s)
        session = body["session_id"]
        s, body = self.post("/kyc/liveness/finish", {"user_id": user_id, "session_id": session, "frames": ["f1"]})
        self.assertEqual(200, s)
        self.assertTrue(body["liveness_passed"])

        s, _ = self.post("/kyc/submit", {
            "user_id": user_id,
            "kyc_final": {"passport_number": "E123"},
            "address": {"address_line1": "Shanghai road 1", "city": "Shanghai", "country": "CN"},
        })
        self.assertEqual(200, s)

        s, _ = self.post("/docs/accept", {"user_id": user_id, "doc_version": "offer-v1", "accepted": True})
        self.assertEqual(200, s)

        s, body = self.post("/pep/sms/send", {"user_id": user_id, "rf_phone": "+79991234567"})
        self.assertEqual(200, s)
        otp_id = body["otp_id"]

        s, body = self.post("/pep/sms/verify", {"user_id": user_id, "otp_id": otp_id, "code": "123456"})
        self.assertEqual(200, s)
        self.assertTrue(body["verified"])

        s, body = self.post("/rf-card/create", {"user_id": user_id})
        self.assertEqual(200, s)
        card_id = body["rf_card_id"]

        s, body = self.post("/cny-card/bind", {"user_id": user_id, "card_last4": "1234", "brand": "UnionPay"})
        self.assertEqual(200, s)
        self.assertTrue(body["cny_funding_token"].startswith("tok_"))

        s, body = self.post("/topup", {"user_id": user_id, "amount_cny": 100})
        self.assertEqual(200, s)
        self.assertGreater(body["balance_rub"], 0)

        s, body = self.post("/qr/parse", {"user_id": user_id, "qr_raw": "pay:coffee_shop:50:RUB:inv-1"})
        self.assertEqual(200, s)
        draft_id = body["draft_id"]

        s, body = self.post("/payment/confirm", {"user_id": user_id, "draft_id": draft_id, "method": "pin", "pin": "1111"})
        self.assertEqual(200, s)
        self.assertEqual("SUCCESS", body["result"])

        s, body = self.get(f"/rf-card/{card_id}/transactions")
        self.assertEqual(200, s)
        self.assertGreaterEqual(len(body["transactions"]), 2)

        s, body = self.get(f"/export/user/{user_id}.json")
        self.assertEqual(200, s)
        self.assertIn("kyc_raw", body)

        s, body = self.get("/kyc/provider/status")
        self.assertEqual(200, s)
        self.assertIn("ocr_mode", body)
        self.assertIn("last_ocr_mode", body)

        s, body = self.get("/kyc/provider/logs?tail=5")
        self.assertEqual(200, s)
        self.assertIn("lines", body)


if __name__ == "__main__":
    unittest.main()
