# Multi-Tenant Wallet API

A highly scalable, secure, and robust multi-tenant wallet and ledger service built with Django and Django REST Framework. This system acts as a financial ledger for multiple tenants (e.g., merchants or organizations), ensuring strict data isolation, atomicity, and mathematical correctness under high concurrency.

---

## Core System Architecture & Features

- **Strict Multi-Tenancy:** Data is strictly isolated per tenant at the database query level. Every API request is securely scoped to a tenant using the `X-Tenant-ID` header API key. Cross-tenant leakage is mathematically impossible by design.
- **Immutable Ledger (Event Sourcing Pattern):** The system treats the `Transaction` table as the absolute source of truth. The `Wallet.balance` acts purely as a synchronized, high-speed cache.
- **Idempotency Guarantee:** Mutating endpoints (Deposit, Withdraw, Transfer) require an `Idempotency-Key` header. Requests are cached in an `IdempotencyKey` table. This guarantees safe retries for network failures without ever double-charging a user.
- **High-Concurrency Atomic Operations:** Core business logic leverages strict database transactions and row-level locks (`select_for_update()`) to entirely prevent race conditions, dirty reads, and phantom reads.
- **Deadlock Prevention:** The system utilizes deterministic row-locking strategies to prevent database deadlocks during multi-wallet transfers.

---

## Architectural Tradeoffs, Assumptions, & Scaling Strategies

As the system scales to millions of users, several initial assumptions and tradeoffs will need to be evolved. Below are the tradeoffs made for this V1, alongside the strategy to tackle them in V2.

### 1. The Wallet Balance Cache Bottleneck
#### The Tradeoff:
Calculating balances on-the-fly by summing `Transaction` rows is too slow. We currently maintain a `balance` Decimal field on the `Wallet` and update it atomically during every transaction.

#### How to Scale It (V2):
Under extreme write-heavy workloads (thousands of TPS to a single wallet), locking the `Wallet` row creates a bottleneck. We would tackle this by moving to a **CQRS (Command Query Responsibility Segregation)** architecture. We would append `Transactions` to an event queue (like Kafka) without locking the wallet, and asynchronously update the balance cache. Clients would read from a Redis cache that guarantees eventual consistency.

---

### 2. Idempotency Storage
#### The Tradeoff:
We use a separate `IdempotencyKey` model to store API responses rather than piggybacking off the `Transaction` table. This allows us to cleanly handle retries for requests that fail *expectedly* (e.g., returning a cached `400 Insufficient Funds` without hitting the business logic again).

#### How to Scale It (V2):
PostgreSQL will eventually bloat with stale idempotency keys. We would tackle this by migrating the Idempotency store to **Redis** with a strict TTL (Time To Live) of 24-48 hours.

---

### 3. Transfer Deadlocks
#### The Tradeoff:
When transferring money between two wallets, we lock *both* wallets simultaneously in a deterministic order (`order_by('id')`) to absolutely prevent deadlocks in high concurrency environments.

#### How to Scale It (V2):
While deterministic locking prevents deadlocks, it still holds locks across multiple rows. In a distributed, microservice environment (or across sharded databases), we would implement the **Saga Pattern** or **Two-Phase Commit (2PC)**. The transfer would be broken into two separate local transactions (Debit Wallet A -> Message Broker -> Credit Wallet B) with compensation logic if step 2 fails.

---

### 4. Currency Handling
#### The Tradeoff:
The system currently assumes a single implicit currency (or uses Integer minor units / Decimal types) as specified.

#### How to Scale It (V2):
Multi-currency support would require tracking the `currency_code` (ISO 4217) on both the `Wallet` and `Transaction` levels, and implementing exchange-rate oracles before cross-currency transfers are authorized.


---

## Setup & Run Locally

### Prerequisites
- Python 3.13+
- PostgreSQL (Highly Recommended to enforce row-level locking via `select_for_update`)
- Docker (Optional, to run PostgreSQL easily)

### 1. Initialization
Clone the repository and enter the directory, then set up the virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt # (or pip install django djangorestframework psycopg2-binary pytest pytest-django pytest-html)
```

### 2. Database Setup (Optional Docker)
To start a local PostgreSQL instance:
```bash
docker compose up -d
```
*Note: If using PostgreSQL, export `USE_POSTGRES=1` in your terminal.*

### 3. Run Migrations & Start Server
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

---

## Manual Testing (Automated Script)

To make evaluating the API as frictionless as possible, a script is included that runs through a complete manual lifecycle against your local server.

While the server is running, open a new terminal tab and run:
```bash
source venv/bin/activate
python run_manual_tests.py
```
This script will:
1. Create a Tenant and fetch its API key.
2. Create two Wallets.
3. Perform a Deposit and verify Idempotency (by re-running the exact same request).
4. Perform a Cross-Wallet Transfer.
5. Fetch the Paginated Transaction Ledger.

---

## Automated Test Suite (Pytest & HTML Reports)

This project contains a comprehensive automated test suite testing Models, API boundaries, Tenant Isolation, Idempotency, and Concurrency (using simultaneous threaded workers).

To run the tests and generate a professional HTML and XML report:
```bash
source venv/bin/activate
pytest wallets/tests/ --html=test_report.html --self-contained-html --junitxml=test_results.xml
```
*Open `test_report.html` in your web browser for a detailed breakdown of the test results.*

---

## Project Structure
```text
Multi-Tenant-Wallet-API/
├── .github/                # GitHub Actions Workflows (CI pipeline)
├── docs/                   # Original assessment document
├── .flake8                 # Linter configuration
├── .gitignore              # Git ignore patterns
├── .pre-commit-config.yaml # Pre-commit hook configurations
├── Dockerfile              # Docker configuration for API
├── docker-compose.yml      # Local Postgres & API infrastructure
├── LICENSE                 # MIT License
├── Makefile                # Shortcut commands (e.g., make test, make up)
├── manage.py               # Django execution script
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Python dependencies
├── run_manual_tests.py     # End-to-end API lifecycle manual test script
├── README.md               # You are here
├── config/                 # Django project config & routing
│   ├── settings.py
│   └── urls.py
└── wallets/                # Core Ledger Application
    ├── models.py           # DB schema (Tenant, Wallet, Transaction, IdempotencyKey)
    ├── views.py            # API logic, locking, & concurrency control
    ├── serializers.py      # DRF serialization
    ├── auth.py             # Custom X-Tenant-ID authentication
    ├── urls.py             # Router endpoints
    ├── admin.py            # Django Admin registrations
    └── tests/              # Comprehensive test suite
        ├── test_api.py          # API & Idempotency tests
        ├── test_concurrency.py  # Threaded race-condition tests
        └── test_models.py       # Database constraint tests
```
