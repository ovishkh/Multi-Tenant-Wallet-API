# Design Decisions & Implementation Notes

This document outlines the core architectural decisions made during the development of this Wallet API, the alternative options considered, and the rationale behind the final choices.

---

## 1. Idempotency Strategy

**The Decision:**  
We implemented a dedicated `IdempotencyKey` model and a custom `@check_idempotency` DRF decorator that caches the exact HTTP status code and response payload.

**Other Option:**  
Storing the `idempotency_key` as a `CharField(unique=True)` directly on the `Transaction` model.

**Why the other option wasn't chosen:**  
If we only store the key on the `Transaction`, we lose the ability to handle *expected failures* idempotently. For example, if a client tries to withdraw $100 but only has $50, the API returns `400 Insufficient Funds` and *no transaction is created*. If the client retries with the same idempotency key, we want to return the exact same `400` response without hitting the database or running business logic again. A dedicated model allows us to cache all outcomes (successes and failures) reliably.

---

## 2. Concurrency & Locking Strategy

**The Decision:**  
We used strict database-level pessimistic locking via PostgreSQL's `select_for_update()` inside `transaction.atomic()` blocks. For cross-wallet transfers, we explicitly order the locks deterministically (`.order_by("id")`).

**Other Option:**  
Optimistic locking (using a `version` column) or application-level distributed locks (e.g., Redis / Redlock).

**Why the other option wasn't chosen:**  
- **Optimistic Locking:** Requires the application or client to catch `ConcurrentModificationException` and retry the transaction. In high-contention financial systems, this leads to heavy retry loops and poor UX.
- **Distributed Locks (Redis):** Introduces a new infrastructure dependency just for locking. If a worker dies while holding a Redis lock, it can lead to stale locks or require complex TTL tuning. PostgreSQL row locks are natively atomic, tie directly to the transaction lifecycle, and are released instantly if the connection drops. The `order_by('id')` sorting completely eliminates the classic "A to B / B to A" deadlock scenario.

---

## 3. Multi-Tenancy Architecture

**The Decision:**  
We chose **Row-level isolation** (a `tenant` ForeignKey on all models), strictly enforced at the API boundary by overriding `get_queryset()` in a `BaseTenantViewSet` and using a custom `TenantAPIKeyAuthentication` class.

**Other Option:**  
Schema-level isolation (e.g., PostgreSQL schemas per tenant using a library like `django-tenants`) or Database-level isolation (one DB per tenant).

**Why the other option wasn't chosen:**  
Schema/Database isolation provides the strongest data guarantees, but adds immense operational complexity. Running migrations across thousands of schemas takes significant time, and connection pooling becomes a major bottleneck. For a modern, high-scale microservice, Row-level isolation combined with strict middleware/query scoping is the industry standard (used by Stripe, AWS, etc.) because it's fast, easily shardable later, and straightforward to maintain.

---

## 4. Balance Tracking: Caching vs On-the-Fly Calculation

**The Decision:**  
We maintain a `balance` DecimalField directly on the `Wallet` model, which is atomically updated in the same transaction that creates a `Transaction` ledger entry.

**Other Option:**  
Calculate the balance purely on-the-fly when requested: `wallet.transactions.aggregate(Sum('amount'))`.

**Why the other option wasn't chosen:**  
While calculating on-the-fly ensures the balance is always perfectly derived from the ledger, it becomes a severe read bottleneck as the transaction table grows into the millions. By treating the `Wallet.balance` as a synchronous cache, we guarantee `O(1)` read performance. Because both the ledger append and the balance update happen inside the same `transaction.atomic()` and `select_for_update()` block, they can never drift out of sync.

---

## 5. Currency & Money Representation

**The Decision:**  
We used PostgreSQL's `DECIMAL(12, 2)` (via Django's `DecimalField`) to represent money.

**Other Option:**  
Integer minor units (e.g., storing $10.50 as `1050` cents in an `IntegerField`).

**Why the other option wasn't chosen:**  
While storing minor units is a great pattern to avoid floating-point math errors, Python's `decimal.Decimal` and PostgreSQL's `DECIMAL` types are already specifically designed for exact-precision financial arithmetic without floating-point drift. Using `DecimalField` makes the database highly readable to analysts (no dividing by 100 in SQL queries) and keeps API contracts straightforward without needing serialization transformations on every request.
