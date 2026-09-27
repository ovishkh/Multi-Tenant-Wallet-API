from rest_framework import serializers
from wallets.models import Tenant, Wallet, Transaction

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'api_key', 'created_at']
        read_only_fields = ['id', 'api_key', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'user_reference', 'balance', 'created_at']
        read_only_fields = ['id', 'balance', 'created_at']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'type', 'created_at']
