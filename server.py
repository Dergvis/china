from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class User:
    user_id: str
    created_at: str = field(default_factory=now_iso)
    locale: str = "zh"
    kyc_raw: dict[str, Any] = field(default_factory=dict)
    kyc_final: dict[str, Any] = field(default_factory=dict)
    address: dict[str, Any] = field(default_factory=dict)
    docs: list[dict[str, Any]] = field(default_factory=list)
    pep: dict[str, Any] = field(default_factory=dict)
    rf_card: dict[str, Any] = field(default_factory=dict)
    cny_funding: dict[str, Any] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    payment_drafts: dict[str, dict[str, Any]] = field(default_factory=dict)


class Store:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.otp: dict[str, dict[str, Any]] = {}

    def get_or_create(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            user = User(user_id=user_id)
            self.users[user_id] = user
        return user


store = Store()

KYC_DEBUG_STATE: dict[str, Any] = {"last_ocr_mode": "unknown", "last_ocr_message": "init"}


def _kyc_log(event: str, details: dict[str, Any] | None = None) -> None:
    payload = {"ts": now_iso(), "event": event, "details": details or {}}
    KYC_DEBUG_STATE["last_ocr_message"] = f"{event}: {json.dumps(payload['details'], ensure_ascii=False)}"
    log_path = os.getenv("KYC_DEBUG_LOG_PATH", "app/kyc_debug.log").strip() or "app/kyc_debug.log"
    try:
        folder = os.path.dirname(log_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


class KycProvider:
    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _tencent_request(service: str, action: str, version: str, region: str, payload: dict[str, Any]) -> dict[str, Any]:
        secret_id = os.getenv("TENCENT_SECRET_ID", "").strip()
        secret_key = os.getenv("TENCENT_SECRET_KEY", "").strip()
        if not secret_id or not secret_key:
            raise ValueError("TENCENT_SECRET_ID/TENCENT_SECRET_KEY are required")

        host = f"{service}.tencentcloudapi.com"
        endpoint = f"https://{host}"
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = (
            f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        )

        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        def _sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = _sign(secret_date, service)
        secret_signing = _sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": timestamp,
            "X-TC-Version": version,
            "X-TC-Region": region,
        }
        return KycProvider._post_json(endpoint, payload, headers=headers)

    @staticmethod
    def ocr(payload: dict[str, Any]) -> dict[str, Any]:
        ocr_url = os.getenv("OCR_API_URL", "").strip()
        if ocr_url:
            _kyc_log("ocr.custom_url.attempt", {"url": ocr_url})
            try:
                result = KycProvider._post_json(ocr_url, payload)
                KYC_DEBUG_STATE["last_ocr_mode"] = "custom-ocr-url"
                _kyc_log("ocr.custom_url.success")
                return result
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                _kyc_log("ocr.custom_url.error", {"error": str(e)})


        if os.getenv("KYC_PROVIDER", "").strip().lower() == "tencent":
            _kyc_log("ocr.tencent.attempt")
            image_data = str(payload.get("image_base64") or payload.get("image") or "")
            if image_data.startswith("data:") and "," in image_data:
                image_data = image_data.split(",", 1)[1]
            if image_data and ("/" in image_data or "\\" in image_data) and not image_data.startswith("http"):
                image_data = ""
            if image_data:
                try:
                    req_payload = {"ImageBase64": image_data}
                    region = os.getenv("TENCENT_OCR_REGION", "ap-beijing")
                    raw = KycProvider._tencent_request("ocr", "PassportOCR", "2018-11-19", region, req_payload)
                    response = raw.get("Response", raw)
                    KYC_DEBUG_STATE["last_ocr_mode"] = "tencent"
                    _kyc_log("ocr.tencent.success", {"request_id": response.get("RequestId", "")})
                    return {
                        "document_type": "passport",
                        "issuing_country": "CN",
                        "full_name_latin": response.get("Name", ""),
                        "passport_number": response.get("PassportNo", ""),
                        "birth_date": response.get("BirthDate", ""),
                        "expiry_date": response.get("ExpireDate", ""),
                        "nationality": response.get("Nationality", ""),
                        "gender": response.get("Sex", ""),
                        "mrz_raw": response.get("MRZCode", ""),
                        "confidence": {},
                        "provider_mode": "tencent-ocr",
                        "provider_raw": response,
                    }
                except Exception as e:
                    _kyc_log("ocr.tencent.error", {"error": str(e)})

        KYC_DEBUG_STATE["last_ocr_mode"] = "mock"
        _kyc_log("ocr.mock.fallback")
        return {
            "document_type": "passport",
            "issuing_country": "CN",
            "full_name_latin": "ZHANG SAN",
            "full_name_cn": "张三",
            "passport_number": "E12345678",
            "birth_date": "1990-01-01",
            "expiry_date": "2030-01-01",
            "gender": "M",
            "nationality": "CHN",
            "mrz_raw": "P<CHNZHANG<<SAN<<<<<<<<<<<<<<<<<<<<",
            "confidence": {
                "full_name_latin": 0.95,
                "passport_number": 0.93,
                "birth_date": 0.92,
            },
            "provider_mode": "mock",
        }

    @staticmethod
    def liveness_finish(session_id: str, frames: list[str] | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        liveness_url = os.getenv("LIVENESS_API_URL", "").strip()
        if liveness_url:
            try:
                response = KycProvider._post_json(liveness_url, {"session_id": session_id, "frames": frames or []})
                response.setdefault("created_at", now_iso())
                return response
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                pass

        if os.getenv("KYC_PROVIDER", "").strip().lower() == "tencent":
            _kyc_log("ocr.tencent.attempt")
            lp = dict(payload or {}).get("tencent_liveness_payload", {})
            if lp:
                try:
                    action = os.getenv("TENCENT_LIVENESS_ACTION", "LivenessCompare")
                    version = os.getenv("TENCENT_LIVENESS_VERSION", "2018-03-01")
                    region = os.getenv("TENCENT_LIVENESS_REGION", "ap-beijing")
                    raw = KycProvider._tencent_request("faceid", action, version, region, lp)
                    response = raw.get("Response", raw)
                    score = float(response.get("Sim", response.get("Score", 0.0)) or 0.0)
                    threshold = float(os.getenv("LIVENESS_PASS_THRESHOLD", "80"))
                    return {
                        "liveness_passed": score >= threshold,
                        "liveness_score": score,
                        "liveness_vendor_session_id": response.get("RequestId", session_id),
                        "created_at": now_iso(),
                        "provider_mode": "tencent-faceid",
                        "provider_raw": response,
                    }
                except Exception:
                    pass

        score = 0.91 if frames is None or len(frames) > 0 else 0.4
        return {
            "liveness_passed": score >= 0.8,
            "liveness_score": score,
            "liveness_vendor_session_id": session_id,
            "created_at": now_iso(),
            "provider_mode": "mock",
        }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "TouristCardMVP/0.1"

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _user(self, data: dict[str, Any]) -> User | None:
        user_id = data.get("user_id")
        if not user_id:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "user_id is required"})
            return None
        return store.get_or_create(user_id)

    def do_GET(self) -> None:
        path = self.path

        if path.startswith("/kyc/provider/logs"):
            try:
                tail = 30
                if "?" in path:
                    qs = path.split("?", 1)[1]
                    for item in qs.split("&"):
                        if item.startswith("tail="):
                            tail = max(1, min(200, int(item.split("=", 1)[1] or "30")))
                log_path = os.getenv("KYC_DEBUG_LOG_PATH", "app/kyc_debug.log").strip() or "app/kyc_debug.log"
                lines: list[str] = []
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()[-tail:]
                self._send(200, {
                    "log_path": log_path,
                    "tail": tail,
                    "lines": [ln.rstrip("\n") for ln in lines],
                })
            except Exception as e:
                self._send(500, {"error": str(e)})
            return
        if path == "/kyc/provider/status":
            provider = os.getenv("KYC_PROVIDER", "").strip().lower() or "mock"
            tencent_ready = bool(os.getenv("TENCENT_SECRET_ID", "").strip() and os.getenv("TENCENT_SECRET_KEY", "").strip())
            ocr_api_url = os.getenv("OCR_API_URL", "").strip()
            liveness_api_url = os.getenv("LIVENESS_API_URL", "").strip()
            if provider == "tencent":
                ocr_mode = "tencent" if tencent_ready else "mock-fallback"
            elif ocr_api_url:
                ocr_mode = "custom-ocr-url"
            else:
                ocr_mode = "mock"
            self._send(200, {
                "kyc_provider": provider,
                "ocr_mode": ocr_mode,
                "tencent_ready": tencent_ready,
                "ocr_api_url_configured": bool(ocr_api_url),
                "liveness_api_url_configured": bool(liveness_api_url),
                "last_ocr_mode": KYC_DEBUG_STATE.get("last_ocr_mode", "unknown"),
                "last_ocr_message": KYC_DEBUG_STATE.get("last_ocr_message", ""),
                "kyc_debug_log_path": os.getenv("KYC_DEBUG_LOG_PATH", "app/kyc_debug.log"),
            })
            return
        if path.startswith("/docs/offer"):
            self._send(200, {"doc_type": "offer", "doc_version": "offer-v1", "content": "Offer text (MVP)"})
            return
        if path.startswith("/docs/pd-consent"):
            self._send(200, {"doc_type": "pd-consent", "doc_version": "pd-v1", "content": "PD consent text (MVP)"})
            return
        if path.startswith("/cny-card"):
            parts = self.path.split("?")
            user_id = ""
            if len(parts) > 1:
                for param in parts[1].split("&"):
                    if param.startswith("user_id="):
                        user_id = param.split("=", 1)[1]
            if not user_id:
                self._send(400, {"error": "user_id query parameter required"})
                return
            user = store.get_or_create(user_id)
            self._send(200, {"cny_card": user.cny_funding})
            return
        m = re.fullmatch(r"/rf-card/([^/]+)$", path)
        if m:
            card_id = m.group(1)
            for user in store.users.values():
                if user.rf_card.get("rf_card_id") == card_id:
                    self._send(200, user.rf_card)
                    return
            self._send(404, {"error": "card not found"})
            return
        m = re.fullmatch(r"/rf-card/([^/]+)/transactions$", path)
        if m:
            card_id = m.group(1)
            for user in store.users.values():
                if user.rf_card.get("rf_card_id") == card_id:
                    self._send(200, {"transactions": user.transactions})
                    return
            self._send(404, {"error": "card not found"})
            return
        m = re.fullmatch(r"/export/user/([^/]+)\.json$", path)
        if m:
            user = store.users.get(m.group(1))
            if not user:
                self._send(404, {"error": "user not found"})
                return
            self._send(200, asdict(user))
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        data = self._read_json()
        path = self.path

        if path == "/kyc/ocr":
            user = self._user(data)
            if not user:
                return
            result = KycProvider.ocr(data)
            user.kyc_raw["ocr"] = result
            self._send(200, result)
            return

        if path == "/kyc/liveness/start":
            user = self._user(data)
            if not user:
                return
            session_id = str(uuid4())
            user.kyc_raw["liveness_start"] = {"session_id": session_id, "created_at": now_iso()}
            self._send(200, {"session_id": session_id})
            return

        if path == "/kyc/liveness/finish":
            user = self._user(data)
            if not user:
                return
            session_id = data.get("session_id")
            if not session_id:
                self._send(400, {"error": "session_id is required"})
                return
            result = KycProvider.liveness_finish(session_id, data.get("frames"), data)
            user.kyc_raw["liveness_finish"] = result
            self._send(200, result)
            return

        if path == "/kyc/submit":
            user = self._user(data)
            if not user:
                return
            user.kyc_final = data.get("kyc_final", {})
            user.address = data.get("address", {})
            self._send(200, {"status": "accepted"})
            return

        if path == "/docs/accept":
            user = self._user(data)
            if not user:
                return
            log = {
                "doc_version": data.get("doc_version"),
                "accepted": bool(data.get("accepted")),
                "timestamp": now_iso(),
                "ip": self.client_address[0],
                "device": data.get("device_info", "wechat-mini-program"),
            }
            user.docs.append(log)
            self._send(200, {"logged": True, "entry": log})
            return

        if path == "/pep/sms/send":
            user = self._user(data)
            if not user:
                return
            rf_phone = data.get("rf_phone", "")
            if not re.fullmatch(r"\+7\d{10}", rf_phone):
                self._send(400, {"error": "rf_phone must match +7XXXXXXXXXX"})
                return
            otp_code = "123456"
            otp_id = str(uuid4())
            store.otp[otp_id] = {"user_id": user.user_id, "rf_phone": rf_phone, "code": otp_code, "verified": False}
            self._send(200, {"otp_id": otp_id, "status": "sent"})
            return

        if path == "/pep/sms/verify":
            user = self._user(data)
            if not user:
                return
            otp_id = data.get("otp_id")
            code = data.get("code")
            otp = store.otp.get(otp_id)
            if not otp or otp["user_id"] != user.user_id:
                self._send(404, {"error": "otp not found"})
                return
            if code != otp["code"]:
                self._send(400, {"verified": False})
                return
            otp["verified"] = True
            user.pep = {"verified": True, "rf_phone": otp["rf_phone"], "verified_at": now_iso()}
            self._send(200, {"verified": True})
            return

        if path == "/rf-card/create":
            user = self._user(data)
            if not user:
                return
            if not user.pep.get("verified"):
                self._send(400, {"error": "PEP verification required"})
                return
            if not user.rf_card:
                suffix = str(uuid4().int)[-4:]
                user.rf_card = {
                    "rf_card_id": str(uuid4()),
                    "masked_pan": f"2200 **** **** {suffix}",
                    "card_status": "ACTIVE",
                    "balance_rub": 0.0,
                    "limits": {"daily_rub": 200000},
                }
            self._send(200, user.rf_card)
            return

        if path == "/cny-card/bind":
            user = self._user(data)
            if not user:
                return
            user.cny_funding = {
                "cny_funding_token": f"tok_{uuid4().hex[:16]}",
                "last4": str(data.get("card_last4", "0000"))[-4:],
                "brand": data.get("brand", "MOCK_UNIONPAY"),
            }
            self._send(200, user.cny_funding)
            return

        if path == "/topup":
            user = self._user(data)
            if not user:
                return
            if not user.rf_card or not user.cny_funding:
                self._send(400, {"error": "rf_card and cny funding required"})
                return
            amount_cny = float(data.get("amount_cny", 0))
            if amount_cny <= 0:
                self._send(400, {"error": "amount_cny must be > 0"})
                return
            rate = 12.5
            rub = round(amount_cny * rate, 2)
            user.rf_card["balance_rub"] = round(float(user.rf_card["balance_rub"]) + rub, 2)
            tx = {
                "tx_id": str(uuid4()),
                "type": "TOPUP",
                "amount_cny": amount_cny,
                "amount_rub": rub,
                "rate": rate,
                "timestamp": now_iso(),
                "status": "SUCCESS",
            }
            user.transactions.append(tx)
            self._send(200, {"balance_rub": user.rf_card["balance_rub"], "tx": tx, "qr_pay_enabled": True})
            return

        if path == "/qr/parse":
            user = self._user(data)
            if not user:
                return
            if not any(t["type"] == "TOPUP" and t["status"] == "SUCCESS" for t in user.transactions):
                self._send(400, {"error": "topup required before qr pay"})
                return
            raw = str(data.get("qr_raw", ""))
            merchant = "Unknown Merchant"
            amount = None
            currency = "RUB"
            invoice = None
            if raw.startswith("pay:"):
                parts = raw.split(":")
                if len(parts) >= 5:
                    _, merchant, amount, currency, invoice = parts[:5]
            elif raw.startswith("http"):
                merchant = raw.split("/")[2]
            draft_id = str(uuid4())
            draft = {
                "draft_id": draft_id,
                "merchant": merchant,
                "amount": float(amount) if amount else 100.0,
                "currency": currency,
                "invoice_id": invoice,
                "fee": 0,
                "status": "PREPARED",
            }
            user.payment_drafts[draft_id] = draft
            self._send(200, draft)
            return

        if path == "/payment/confirm":
            user = self._user(data)
            if not user:
                return
            draft = user.payment_drafts.get(str(data.get("draft_id")))
            if not draft:
                self._send(404, {"error": "draft not found"})
                return
            method = data.get("method", "pin")
            if method == "pin" and data.get("pin") != "1111":
                self._send(400, {"result": "DECLINED", "reason": "invalid pin"})
                return
            amount = float(draft["amount"])
            if user.rf_card.get("balance_rub", 0) < amount:
                self._send(400, {"result": "DECLINED", "reason": "insufficient funds"})
                return
            user.rf_card["balance_rub"] = round(float(user.rf_card["balance_rub"]) - amount, 2)
            tx = {
                "tx_id": str(uuid4()),
                "type": "QR_PAY",
                "amount_rub": amount,
                "merchant": draft["merchant"],
                "invoice_id": draft["invoice_id"],
                "status": "SUCCESS",
                "timestamp": now_iso(),
            }
            user.transactions.append(tx)
            draft["status"] = "CONFIRMED"
            self._send(200, {"result": "SUCCESS", "balance_rub": user.rf_card["balance_rub"], "tx": tx})
            return

        self._send(404, {"error": "not found"})


def run() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), AppHandler)
    print("Server listening on http://0.0.0.0:8080")
    server.serve_forever()


if __name__ == "__main__":
    run()
