import urllib.request
import urllib.error
import json

BASE_URL = "http://localhost:8000/api/v1"


def make_request(method, endpoint, data=None, headers=None):
    url = f"{BASE_URL}{endpoint}"
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"

    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            return status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}


print("--- STARTING MANUAL API TESTS ---")

# 1. Create Tenant
print("\n1. Creating a new Tenant (Acme Corp)...")
status, data = make_request("POST", "/tenants/", {"name": "Acme Corp"})
api_key = data.get("api_key")
print(f"   Response {status}: {data}")
print(f"   => Got API Key: {api_key}")

auth_headers = {"X-Tenant-ID": api_key}

# 2. Create Wallets
print("\n2. Creating Tony's Wallet...")
status, tony = make_request(
    "POST", "/wallets/", {"user_reference": "tony_stark"}, auth_headers
)
tony_id = tony.get("id")
print(f"   Response {status}: {tony}")

print("\n   Creating Pepper's Wallet...")
status, pepper = make_request(
    "POST", "/wallets/", {"user_reference": "pepper_potts"}, auth_headers
)
pepper_id = pepper.get("id")
print(f"   Response {status}: {pepper}")

# 3. Deposit Money
print("\n3. Depositing $1000 into Tony's Wallet (with Idempotency-Key 'dep-001')...")
dep_headers = auth_headers.copy()
dep_headers["Idempotency-Key"] = "dep-001"
status, data = make_request(
    "POST", f"/wallets/{tony_id}/deposit/", {"amount": "1000.00"}, dep_headers
)
print(f"   Response {status}: {data}")

print("\n   Retrying EXACT SAME deposit (Testing Idempotency)...")
status, data = make_request(
    "POST", f"/wallets/{tony_id}/deposit/", {"amount": "1000.00"}, dep_headers
)
print(f"   Response {status}: {data}  <-- Notice balance didn't double!")

# 4. Transfer Money
print("\n4. Transferring $250 from Tony to Pepper...")
tx_headers = auth_headers.copy()
tx_headers["Idempotency-Key"] = "tx-001"
status, data = make_request(
    "POST",
    f"/wallets/{tony_id}/transfer/",
    {"target_wallet_id": pepper_id, "amount": "250.00"},
    tx_headers,
)
print(f"   Response {status}: {data}")

# 5. Check History
print("\n5. Checking Tony's Transaction History...")
status, data = make_request(
    "GET", f"/wallets/{tony_id}/transactions/", headers=auth_headers
)
print(f"   Response {status}: {json.dumps(data, indent=2)}")

print("\n--- TESTS COMPLETED SUCCESSFULLY ---")
