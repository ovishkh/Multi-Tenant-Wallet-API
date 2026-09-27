import pytest
from django.db import IntegrityError
from decimal import Decimal
from wallets.models import Tenant, Wallet, Transaction, IdempotencyKey

@pytest.mark.django_db
class TestTenantModel:
    def test_tenant_creation(self):
        tenant = Tenant.objects.create(name="Acme Corp", api_key="test_api_key_123")
        assert tenant.id is not None
        assert tenant.name == "Acme Corp"
        assert tenant.api_key == "test_api_key_123"

    def test_tenant_api_key_unique(self):
        Tenant.objects.create(name="Acme Corp", api_key="unique_key")
        with pytest.raises(IntegrityError):
            Tenant.objects.create(name="Another Corp", api_key="unique_key")

@pytest.mark.django_db
class TestWalletModel:
    def test_wallet_creation(self):
        tenant = Tenant.objects.create(name="Acme Corp", api_key="test_api_key_123")
        wallet = Wallet.objects.create(tenant=tenant, user_reference="user_1")
        assert wallet.id is not None
        assert wallet.tenant == tenant
        assert wallet.user_reference == "user_1"
        assert wallet.balance == Decimal('0.0000')

    def test_wallet_user_reference_unique_per_tenant(self):
        tenant = Tenant.objects.create(name="Acme Corp", api_key="test_api_key_123")
        Wallet.objects.create(tenant=tenant, user_reference="user_1")
        with pytest.raises(IntegrityError):
            Wallet.objects.create(tenant=tenant, user_reference="user_1")

    def test_wallet_user_reference_not_unique_across_tenants(self):
        tenant1 = Tenant.objects.create(name="Acme Corp", api_key="test_api_key_1")
        tenant2 = Tenant.objects.create(name="Beta Corp", api_key="test_api_key_2")
        wallet1 = Wallet.objects.create(tenant=tenant1, user_reference="user_1")
        wallet2 = Wallet.objects.create(tenant=tenant2, user_reference="user_1")
        assert wallet1.id != wallet2.id

@pytest.mark.django_db
class TestTransactionModel:
    def test_transaction_creation(self):
        tenant = Tenant.objects.create(name="Acme", api_key="key")
        wallet = Wallet.objects.create(tenant=tenant, user_reference="user_1")
        tx = Transaction.objects.create(
            wallet=wallet,
            amount=Decimal('100.00'),
            type='DEPOSIT'
        )
        assert tx.id is not None
        assert tx.wallet == wallet
        assert tx.amount == Decimal('100.00')

@pytest.mark.django_db
class TestIdempotencyKeyModel:
    def test_idempotency_key_creation(self):
        tenant = Tenant.objects.create(name="Acme", api_key="key")
        ik = IdempotencyKey.objects.create(
            tenant=tenant,
            key="req-123",
            request_path="/api/deposit",
            response_code=200,
            response_body={"status": "success"}
        )
        assert ik.id is not None
        assert ik.key == "req-123"

    def test_idempotency_key_unique_per_tenant(self):
        tenant = Tenant.objects.create(name="Acme", api_key="key")
        IdempotencyKey.objects.create(
            tenant=tenant, key="req-123", request_path="/api", response_code=200, response_body={}
        )
        with pytest.raises(IntegrityError):
            IdempotencyKey.objects.create(
                tenant=tenant, key="req-123", request_path="/api2", response_code=400, response_body={}
            )
