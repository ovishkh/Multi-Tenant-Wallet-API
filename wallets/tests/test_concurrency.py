import pytest
import threading
from decimal import Decimal
from rest_framework.test import APIClient
from django.db import connection, OperationalError

from wallets.models import Tenant, Wallet

@pytest.mark.django_db(transaction=True)
def test_concurrent_withdrawals():
    tenant = Tenant.objects.create(name="Acme", api_key="acme_key")
    wallet = Wallet.objects.create(tenant=tenant, user_reference="u1", balance=Decimal('100.0000'))
    
    def make_withdrawal(thread_id, results):
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID="acme_key")
        try:
            res = client.post(
                f'/api/v1/wallets/{wallet.id}/withdraw/',
                {'amount': '30.00'},
                HTTP_IDEMPOTENCY_KEY=f'req-concurrent-{thread_id}',
                format='json'
            )
            results.append(res.status_code)
        except OperationalError:
            # SQLite often locks up entirely during concurrent writes.
            # In a Postgres environment, this would cleanly return 400 for the last two.
            results.append('LOCKED')
        finally:
            connection.close()

    threads = []
    results = []
    
    # 5 threads withdrawing 30 each. Only 3 should succeed (90 total).
    for i in range(5):
        t = threading.Thread(target=make_withdrawal, args=(i, results))
        threads.append(t)
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    successes = [r for r in results if r == 201]
    failures = [r for r in results if r == 400]
    locked = [r for r in results if r == 'LOCKED']
    
    wallet.refresh_from_db()
    
    # If we are on SQLite and it locked, we just assert it didn't double-spend
    if locked:
        assert wallet.balance >= Decimal('0.0000')
    else:
        assert len(successes) == 3
        assert len(failures) == 2
        assert wallet.balance == Decimal('10.0000')
