# Customer Support Bot – Day 7 Challenge

A small Flask app for customer support. A customer sends a message, an AI model
decides on a reply and an action (check an order, refund, close an account), and
the app carries out that action.

The AI model is **fake** (`llm.py`), so the app runs without internet or a real key.
All customers, orders and keys in this repo are **made up**.

**Your job:** review this app like a security and quality reviewer. Find the risks,
rate them, fix the two most serious ones, and add monitoring.

## Run it

```
python -m venv .venv
.venv\Scripts\activate        (Windows)
source .venv/bin/activate     (Mac/Linux)
pip install -r requirements.txt
python app.py
```

The app runs at http://127.0.0.1:5000.

## Postman authentication and order status

Send a `POST` request to `http://127.0.0.1:5000/chat` with:

- Header: `Authorization: Bearer dev-ravi-token`
- Header: `Content-Type: application/json`
- Body:

```json
{"message": "Where is my order 10231?"}
```

Use `dev-priya-token` for the fictional Priya customer. The `/chat` endpoint
does not accept a caller-supplied `customer_email` as proof of identity.

## Refund confirmation

To initiate a refund, send:

```json
{"message": "Refund Rs 500 for order 10231"}
```

The response will have HTTP 202 and include `confirmation_token` only after
server-side authentication and refund validation. Confirm it with:

```json
{"confirmation_token": "<token-from-refund-response>"}
```

Confirmation is valid for five minutes, can be used once, and is bound to
the authenticated customer and refund action.

## Account-closure confirmation

To initiate closure for the authenticated account, send:

```json
{"message": "Close my account"}
```

The response will have HTTP 202 and the account will remain active until the
returned token is confirmed:

```json
{"confirmation_token": "<token-from-closure-response>"}
```

The closure token is valid for five minutes, can be used once, and cannot be
used by another customer or as a refund confirmation.

## Run the tests

```
pytest -v
```

The test suite is run with `.venv\Scripts\python.exe -m pytest -v`. A CI workflow
in `.github/workflows/ci.yml` runs the tests on every push and pull request.

## Development authentication

This training application accepts only the following development bearer tokens:

- `Authorization: Bearer dev-ravi-token` identifies the fictional `ravi.kumar@example.com` customer.
- `Authorization: Bearer dev-priya-token` identifies the fictional `priya.s@example.com` customer.

These tokens are local fixture credentials, not production authentication. Do not deploy
them to a real environment. Production should use an external identity provider and
cryptographically validated access tokens.

## Sensitive actions

Refunds and account closure do not execute immediately from LLM output. The endpoint
first validates authentication, order ownership, action arguments, and refund limits.
It then returns a 5-minute, single-use confirmation token that is bound to the
authenticated customer and action.

## Files

| File | What it does |
|---|---|
| app.py | The web app, the tools the AI can use, and the /chat endpoint |
| llm.py | A fake AI model that returns a reply, an action and token usage |
| tests/test_app.py | Starter tests |
| Dockerfile | Builds the app as a Docker image |
| .github/workflows/ci.yml | Runs the tests on GitHub |
| logs/ | Where the app writes its log file |
# day7-support-bot
