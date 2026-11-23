"""Customer Support Bot (Day 7 Challenge: risk review).

A small Flask app. A customer sends a message, the LLM decides on a reply
and an action, and the app carries out the action.
"""
import json
import logging
import time
import uuid

from flask import Flask, jsonify, request

from llm import call_llm

app = Flask(__name__)

API_KEY = "sk-demo-4f9a2c71-FAKE-KEY-for-training-only"

logging.basicConfig(filename="logs/app.log", level=logging.INFO)

ORDERS = {
    "10231": {"status": "Shipped", "amount": 1299, "customer_email": "ravi.kumar@example.com"},
    "10232": {"status": "Delivered", "amount": 499, "customer_email": "priya.s@example.com"},
    "10233": {"status": "Processing", "amount": 2499, "customer_email": "ravi.kumar@example.com"},
}
CUSTOMERS = {
    "ravi.kumar@example.com": {"name": "Ravi Kumar", "phone": "+91 98480 12345", "active": True},
    "priya.s@example.com": {"name": "Priya Sharma", "phone": "+91 99890 67890", "active": True},
}
REFUNDS = []

# Development-only training credentials. These tokens identify a fixture customer;
# they are not a production authentication mechanism.
AUTH_TOKENS = {
    "dev-ravi-token": "ravi.kumar@example.com",
    "dev-priya-token": "priya.s@example.com",
}

MAX_REFUND_AMOUNT = 1000
CONFIRMATION_TTL_SECONDS = 300
PENDING_CONFIRMATIONS = {}


# ---------- Tools the LLM can use ----------

def get_order_status(order_id):
    order = ORDERS.get(order_id)
    return order["status"] if order else "Order not found"


def issue_refund(order_id, amount):
    REFUNDS.append({"order_id": order_id, "amount": amount})
    return f"Refunded Rs {amount} for order {order_id}"


def delete_customer_account(customer_email):
    CUSTOMERS.pop(customer_email, None)
    return f"Deleted account {customer_email}"


TOOLS = {
    "get_order_status": get_order_status,
    "issue_refund": issue_refund,
    "delete_customer_account": delete_customer_account,
}


def authenticate_request():
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return AUTH_TOKENS.get(parts[1])


def validate_order_owner(order_id, customer_email):
    order = ORDERS.get(order_id)
    if not order:
        return None, jsonify({"error": "Order not found"}), 404
    if order["customer_email"] != customer_email:
        return None, jsonify({"error": "Forbidden"}), 403
    return order, None, None


def validate_refund(order_id, amount, customer_email):
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return "Refund amount must be a positive whole-number amount"

    order, error_response, status_code = validate_order_owner(order_id, customer_email)
    if error_response:
        return error_response, status_code

    if amount > MAX_REFUND_AMOUNT:
        return f"Refund amount exceeds the permitted limit of Rs {MAX_REFUND_AMOUNT}"
    if amount > order["amount"]:
        return f"Refund amount exceeds the order amount of Rs {order['amount']}"
    return None


def create_confirmation(customer_email, action, args):
    token = uuid.uuid4().hex
    PENDING_CONFIRMATIONS[token] = {
        "customer_email": customer_email,
        "action": action,
        "args": dict(args),
        "expires_at": time.time() + CONFIRMATION_TTL_SECONDS,
    }
    return token


def purge_expired_confirmations():
    now = time.time()
    expired_tokens = [
        token for token, confirmation in PENDING_CONFIRMATIONS.items()
        if confirmation["expires_at"] <= now
    ]
    for token in expired_tokens:
        PENDING_CONFIRMATIONS.pop(token, None)


def execute_confirmation(token, customer_email):
    purge_expired_confirmations()
    confirmation = PENDING_CONFIRMATIONS.get(token)
    if not confirmation:
        return jsonify({"error": "Invalid or expired confirmation token"}), 400
    if confirmation["customer_email"] != customer_email:
        return jsonify({"error": "Forbidden"}), 403

    action = confirmation["action"]
    args = confirmation["args"]
    PENDING_CONFIRMATIONS.pop(token, None)

    if action == "issue_refund":
        validation_error = validate_refund(
            args["order_id"], args["amount"], customer_email
        )
        if validation_error:
            if isinstance(validation_error, tuple):
                return jsonify(validation_error[0].get_json()), validation_error[1]
            return jsonify({"error": validation_error}), 400
        result = TOOLS[action](**args)
        return jsonify({"reply": "Refund confirmed and issued.", "action_result": result}), 200

    if action == "delete_customer_account":
        if args["customer_email"] != customer_email:
            return jsonify({"error": "Forbidden"}), 403
        if customer_email not in CUSTOMERS:
            return jsonify({"error": "Account not found"}), 404
        result = TOOLS[action](customer_email)
        return jsonify({"reply": "Account closure confirmed.", "action_result": result}), 200

    return jsonify({"error": "Invalid confirmation action"}), 400


# ---------- Chat endpoint ----------

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON request"}), 400

    email = authenticate_request()
    if not email:
        return jsonify({"error": "Authentication required"}), 401

    message = data.get("message", "")
    if not isinstance(message, str) or len(message) > 2000:
        return jsonify({"error": "Message must be a string of at most 2000 characters"}), 400

    confirmation_token = data.get("confirmation_token")
    if confirmation_token is not None:
        if not isinstance(confirmation_token, str):
            return jsonify({"error": "Invalid confirmation token"}), 400
        return execute_confirmation(confirmation_token, email)

    customer = CUSTOMERS.get(email, {})

    prompt = (
        "You are a helpful support agent. Reply in JSON with reply, action and args.\n"
        f"Customer name: {customer.get('name')}\n"
        f"Customer email: {email}\n"
        f"Customer phone: {customer.get('phone')}\n"
        f"Customer message: {message}"
    )

    text, usage = call_llm(prompt, API_KEY)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        logging.warning("chat event=llm_invalid_json")
        return jsonify({"error": "Support assistant response could not be processed"}), 502

    action = result.get("action")
    args = result.get("args", {})
    action_result = None

    if action == "get_order_status":
        order_id = args.get("order_id") if isinstance(args, dict) else None
        if not isinstance(order_id, str):
            return jsonify({"error": "A valid order ID is required"}), 400
        order, error_response, status_code = validate_order_owner(order_id, email)
        if error_response:
            return error_response, status_code
        action_result = order["status"]

    elif action == "issue_refund":
        if not isinstance(args, dict):
            return jsonify({"error": "Invalid refund details"}), 400
        order_id = args.get("order_id")
        amount = args.get("amount")
        if not isinstance(order_id, str):
            return jsonify({"error": "A valid order ID is required"}), 400

        validation_error = validate_refund(order_id, amount, email)
        if isinstance(validation_error, tuple):
            response, status_code = validation_error
            return response, status_code
        if validation_error:
            return jsonify({"error": validation_error}), 400

        token = create_confirmation(email, "issue_refund", {
            "order_id": order_id,
            "amount": amount,
        })
        action_result = "Confirmation required"
        logging.info("chat event=confirmation_required action=refund")
        return jsonify({
            "reply": "Please confirm this refund to continue.",
            "action_result": action_result,
            "confirmation_required": True,
            "confirmation_token": token,
            "expires_in": CONFIRMATION_TTL_SECONDS,
        }), 202

    elif action == "delete_customer_account":
        if email not in CUSTOMERS:
            return jsonify({"error": "Account not found"}), 404
        token = create_confirmation(email, "delete_customer_account", {
            "customer_email": email,
        })
        action_result = "Confirmation required"
        logging.info("chat event=confirmation_required action=account_closure")
        return jsonify({
            "reply": "Please confirm account closure to continue.",
            "action_result": action_result,
            "confirmation_required": True,
            "confirmation_token": token,
            "expires_in": CONFIRMATION_TTL_SECONDS,
        }), 202

    elif action is not None:
        logging.warning("chat event=unknown_llm_action")
        return jsonify({"error": "The requested action is not permitted"}), 400

    logging.info("chat event=reply_generated")
    return jsonify({"reply": result["reply"], "action_result": action_result})


if __name__ == "__main__":
    app.run(debug=True)
