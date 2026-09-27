import pytest
from rest_framework.test import APIClient
from decimal import Decimal
from wallets.models import Tenant, Wallet, Transaction, IdempotencyKey

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Acme Corp", api_key="acme_api_key")

@pytest.fixture
def auth_client(api_client, tenant):
    api_client.credentials(HTTP_X_TENANT_ID=tenant.api_key)
    return api_client

@pytest.mark.django_db
class TestTenantAPI:
    def test_create_tenant(self, api_client):
        response = api_client.post('/api/v1/tenants/', {'name': 'New Tenant'}, format='json')
        assert response.status_code == 201
        assert 'api_key' in response.data
        assert response.data['name'] == 'New Tenant'

@pytest.mark.django_db
class TestWalletAPI:
    def test_create_wallet(self, auth_client, tenant):
        response = auth_client.post('/api/v1/wallets/', {'user_reference': 'user123'}, format='json')
        assert response.status_code == 201
        assert response.data['user_reference'] == 'user123'
        assert response.data['balance'] == '0.0000'

    def test_create_wallet_unauthorized(self, api_client):
        response = api_client.post('/api/v1/wallets/', {'user_reference': 'user123'}, format='json')
        assert response.status_code in [401, 403]

    def test_get_wallet(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123', balance=Decimal('50.0000'))
        response = auth_client.get(f'/api/v1/wallets/{wallet.id}/')
        assert response.status_code == 200
        assert response.data['balance'] == '50.0000'

    def test_get_wallet_other_tenant(self, api_client, tenant):
        other_tenant = Tenant.objects.create(name="Other", api_key="other_key")
        wallet = Wallet.objects.create(tenant=other_tenant, user_reference='user123')
        api_client.credentials(HTTP_X_TENANT_ID=tenant.api_key)
        response = api_client.get(f'/api/v1/wallets/{wallet.id}/')
        assert response.status_code == 404

@pytest.mark.django_db
class TestTransactionAPI:
    def test_deposit(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123')
        response = auth_client.post(
            f'/api/v1/wallets/{wallet.id}/deposit/',
            {'amount': '100.50'},
            HTTP_IDEMPOTENCY_KEY='req-1',
            format='json'
        )
        assert response.status_code == 201
        wallet.refresh_from_db()
        assert wallet.balance == Decimal('100.50')
        assert wallet.transactions.count() == 1

    def test_withdraw_success(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123', balance=Decimal('100.0000'))
        response = auth_client.post(
            f'/api/v1/wallets/{wallet.id}/withdraw/',
            {'amount': '50.00'},
            HTTP_IDEMPOTENCY_KEY='req-2',
            format='json'
        )
        assert response.status_code == 201
        wallet.refresh_from_db()
        assert wallet.balance == Decimal('50.0000')

    def test_withdraw_insufficient_funds(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123', balance=Decimal('10.0000'))
        response = auth_client.post(
            f'/api/v1/wallets/{wallet.id}/withdraw/',
            {'amount': '50.00'},
            HTTP_IDEMPOTENCY_KEY='req-3',
            format='json'
        )
        assert response.status_code == 400
        assert 'error' in response.data
        wallet.refresh_from_db()
        assert wallet.balance == Decimal('10.0000')

    def test_transfer_success(self, auth_client, tenant):
        w1 = Wallet.objects.create(tenant=tenant, user_reference='u1', balance=Decimal('100.0000'))
        w2 = Wallet.objects.create(tenant=tenant, user_reference='u2', balance=Decimal('0.0000'))
        
        response = auth_client.post(
            f'/api/v1/wallets/{w1.id}/transfer/',
            {'target_wallet_id': str(w2.id), 'amount': '25.00'},
            HTTP_IDEMPOTENCY_KEY='req-4',
            format='json'
        )
        assert response.status_code == 201
        w1.refresh_from_db()
        w2.refresh_from_db()
        assert w1.balance == Decimal('75.0000')
        assert w2.balance == Decimal('25.0000')
        
    def test_transfer_cross_tenant_fails(self, auth_client, tenant):
        other_tenant = Tenant.objects.create(name="Other", api_key="other_key")
        w1 = Wallet.objects.create(tenant=tenant, user_reference='u1', balance=Decimal('100.0000'))
        w2 = Wallet.objects.create(tenant=other_tenant, user_reference='u2', balance=Decimal('0.0000'))
        
        response = auth_client.post(
            f'/api/v1/wallets/{w1.id}/transfer/',
            {'target_wallet_id': str(w2.id), 'amount': '25.00'},
            HTTP_IDEMPOTENCY_KEY='req-5',
            format='json'
        )
        assert response.status_code in [400, 404]
        
    def test_idempotency_deposit(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123')
        # First request
        res1 = auth_client.post(
            f'/api/v1/wallets/{wallet.id}/deposit/',
            {'amount': '10.00'},
            HTTP_IDEMPOTENCY_KEY='idem-key-1',
            format='json'
        )
        assert res1.status_code == 201
        
        # Second request
        res2 = auth_client.post(
            f'/api/v1/wallets/{wallet.id}/deposit/',
            {'amount': '10.00'},
            HTTP_IDEMPOTENCY_KEY='idem-key-1',
            format='json'
        )
        assert res2.status_code == 201
        
        wallet.refresh_from_db()
        assert wallet.balance == Decimal('10.0000') # Balance should only increment once

    def test_wallet_transactions_history(self, auth_client, tenant):
        wallet = Wallet.objects.create(tenant=tenant, user_reference='user123', balance=Decimal('50.0000'))
        # Create 15 transactions
        for i in range(15):
            Transaction.objects.create(wallet=wallet, amount=Decimal('1.00'), type='DEPOSIT')
        
        res = auth_client.get(f'/api/v1/wallets/{wallet.id}/transactions/', format='json')
        assert res.status_code == 200
        assert 'results' in res.data
        assert len(res.data['results']) == 10  # Pagination size is 10
        assert res.data['count'] == 15
