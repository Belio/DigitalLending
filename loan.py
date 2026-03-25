#!/usr/bin/env python3
"""
Mock Digital Lending API — Italian Tier-2 Bank Demo
Run: python3 lending_mock.py
Listens on: http://localhost:8080

Routes:
  POST /loans              — submit a loan application
  POST /eligibility        — check loan eligibility
  GET  /credit-score/{id}  — retrieve credit score for a customer
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, re, random, datetime

PORT = 8080

# ── Realistic response generators ────────────────────────────────────────────

def loan_application(body):
    ref = f"LOAN-IT-{random.randint(100000,999999)}"
    return {
        "application_id": ref,
        "status": "RECEIVED",
        "applicant": body.get("applicant", {}),
        "requested_amount_eur": body.get("amount_eur", 0),
        "purpose": body.get("purpose", "unspecified"),
        "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "estimated_decision_at": (
            datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        ).isoformat() + "Z",
        "next_step": "automated_credit_assessment",
        "_kong": {
            "note": "Request routed via Kong AI Gateway",
            "latency_ms": random.randint(12, 45)
        }
    }

def eligibility_check(body):
    amount = body.get("amount_eur", 0)
    income = body.get("annual_income_eur", 0)
    # Simple DTI logic for realism
    monthly_income = income / 12
    monthly_payment_est = amount * 0.025
    dti = round((monthly_payment_est / monthly_income * 100), 1) if monthly_income > 0 else 99.9
    eligible = dti < 40 and income > 20000 and amount <= 250000

    return {
        "eligible": eligible,
        "decision": "APPROVED_IN_PRINCIPLE" if eligible else "REFER_TO_UNDERWRITER",
        "requested_amount_eur": amount,
        "max_eligible_amount_eur": min(amount * 1.2, 250000) if eligible else round(income * 3.5, -3),
        "indicative_rate_pct": round(random.uniform(4.2, 7.8), 2),
        "indicative_term_months": body.get("term_months", 60),
        "debt_to_income_pct": dti,
        "assessed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "valid_for_hours": 48,
        "regulatory": {
            "framework": "CCD_EU_2023",
            "responsible_lending_check": "PASSED",
            "psd2_consent_required": True
        }
    }

def credit_score(customer_id):
    # Deterministic-ish score based on customer_id for demo consistency
    seed = sum(ord(c) for c in customer_id)
    random.seed(seed)
    score = random.randint(420, 850)
    band = (
        "EXCELLENT" if score >= 750 else
        "GOOD"      if score >= 670 else
        "FAIR"      if score >= 580 else
        "POOR"
    )
    random.seed()  # reset seed
    return {
        "customer_id": customer_id,
        "score": score,
        "band": band,
        "model": "CRIF_IT_v4",
        "factors": {
            "payment_history_pct": round(random.uniform(60, 99), 1),
            "credit_utilisation_pct": round(random.uniform(10, 75), 1),
            "account_age_months": random.randint(12, 180),
            "recent_enquiries": random.randint(0, 4)
        },
        "last_updated": (
            datetime.datetime.utcnow() - datetime.timedelta(days=random.randint(1, 30))
        ).isoformat() + "Z",
        "next_refresh": (
            datetime.datetime.utcnow() + datetime.timedelta(days=30)
        ).isoformat() + "Z"
    }

# ── HTTP handler ──────────────────────────────────────────────────────────────

class LendingHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {fmt % args}")

    def send_json(self, code, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Mock-Server", "lending-demo-v1")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, apikey")
        self.end_headers()

    def do_GET(self):
        # GET /credit-score/{customer_id}
        m = re.match(r"^/credit-score/([^/?]+)", self.path)
        if m:
            self.send_json(200, credit_score(m.group(1)))
        elif self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "lending-mock"})
        else:
            self.send_json(404, {"message": "not found", "path": self.path})

    def do_POST(self):
        body = self.read_body()

        if self.path == "/loans":
            self.send_json(201, loan_application(body))

        elif self.path == "/eligibility":
            if not body.get("amount_eur") or not body.get("annual_income_eur"):
                self.send_json(400, {
                    "message": "amount_eur and annual_income_eur are required",
                    "code": "MISSING_REQUIRED_FIELDS"
                })
            else:
                self.send_json(200, eligibility_check(body))

        else:
            self.send_json(404, {"message": "not found", "path": self.path})

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), LendingHandler)
    print(f"""
╔══════════════════════════════════════════════════════╗
║       Mock Digital Lending API — Demo Server         ║
╠══════════════════════════════════════════════════════╣
║  Listening on  http://localhost:{PORT}                   ║
║                                                      ║
║  POST  /eligibility        check loan eligibility    ║
║  POST  /loans              submit loan application   ║
║  GET   /credit-score/{{id}}  get credit score          ║
║  GET   /health             health check              ║
╚══════════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")