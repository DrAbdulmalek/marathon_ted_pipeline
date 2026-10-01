"""مستقبل webhook بسيط للاختبار."""
import hmac
import hashlib
from flask import Flask, request, abort

app = Flask(__name__)
SECRET = "your_webhook_secret"

@app.route("/webhook", methods=["POST"])
def receive():
    signature = request.headers.get("X-Marathon-Signature", "")
    body = request.get_data()

    expected = "sha256=" + hmac.new(
        SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        abort(401, "Invalid signature")

    data = request.get_json()
    print(f"📨 {data['event']}: {data['data']}")
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(port=9000)
