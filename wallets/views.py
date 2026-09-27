from rest_framework import viewsets, status, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from django.db import transaction
from functools import wraps
from decimal import Decimal, InvalidOperation
from wallets.models import Tenant, Wallet, Transaction, IdempotencyKey
from wallets.serializers import (
    TenantSerializer,
    WalletSerializer,
    TransactionSerializer,
)
from wallets.auth import TenantAPIKeyAuthentication


class TenantViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    # Publicly accessible for the purpose of the assessment


def check_idempotency(view_func):
    @wraps(view_func)
    def wrapper(self, request, *args, **kwargs):
        idem_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idem_key:
            return view_func(self, request, *args, **kwargs)

        tenant = request.auth
        try:
            stored = IdempotencyKey.objects.get(tenant=tenant, key=idem_key)
            return Response(stored.response_body, status=stored.response_code)
        except IdempotencyKey.DoesNotExist:
            pass

        with transaction.atomic():
            response = view_func(self, request, *args, **kwargs)
            if response.status_code in [200, 201, 400, 404]:
                IdempotencyKey.objects.create(
                    tenant=tenant,
                    key=idem_key,
                    request_path=request.path,
                    response_code=response.status_code,
                    response_body=response.data,
                )
        return response

    return wrapper


class BaseTenantViewSet(viewsets.GenericViewSet):
    authentication_classes = [TenantAPIKeyAuthentication]

    def get_permissions(self):
        class IsTenantAuthenticated(BasePermission):
            def has_permission(self, request, view):
                return request.auth is not None

            def has_object_permission(self, request, view, obj):
                return request.auth is not None

        return [IsTenantAuthenticated()]

    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.auth)


class WalletViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, BaseTenantViewSet
):
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.auth)

    @action(detail=True, methods=["post"])
    @check_idempotency
    def deposit(self, request, pk=None):
        amount = request.data.get("amount")
        try:
            amount = Decimal(str(amount))
            if amount <= Decimal("0"):
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return Response(
                {"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            wallet = self.get_queryset().select_for_update().get(pk=pk)
            Transaction.objects.create(wallet=wallet, amount=amount, type="DEPOSIT")
            wallet.balance += amount
            wallet.save(update_fields=["balance"])

        return Response(
            {"status": "deposited", "balance": str(wallet.balance)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    @check_idempotency
    def withdraw(self, request, pk=None):
        amount = request.data.get("amount")
        try:
            amount = Decimal(str(amount))
            if amount <= Decimal("0"):
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return Response(
                {"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            wallet = self.get_queryset().select_for_update().get(pk=pk)
            if wallet.balance < amount:
                return Response(
                    {"error": "Insufficient funds"}, status=status.HTTP_400_BAD_REQUEST
                )

            Transaction.objects.create(wallet=wallet, amount=-amount, type="WITHDRAWAL")
            wallet.balance -= amount
            wallet.save(update_fields=["balance"])

        return Response(
            {"status": "withdrawn", "balance": str(wallet.balance)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    @check_idempotency
    def transfer(self, request, pk=None):
        target_id = request.data.get("target_wallet_id")
        amount = request.data.get("amount")

        if str(pk) == str(target_id):
            return Response({"error": "Cannot transfer to same wallet"}, status=400)

        try:
            amount = Decimal(str(amount))
            if amount <= Decimal("0"):
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return Response({"error": "Invalid amount"}, status=400)

        with transaction.atomic():
            wallets = list(
                self.get_queryset()
                .select_for_update()
                .filter(id__in=[pk, target_id])
                .order_by("id")
            )
            if len(wallets) != 2:
                return Response(
                    {"error": "One or both wallets not found (must be same tenant)"},
                    status=404,
                )

            w1 = next(w for w in wallets if str(w.id) == str(pk))
            w2 = next(w for w in wallets if str(w.id) == str(target_id))

            if w1.balance < amount:
                return Response({"error": "Insufficient funds"}, status=400)

            tx_out = Transaction.objects.create(
                wallet=w1, amount=-amount, type="TRANSFER_OUT"
            )
            Transaction.objects.create(
                wallet=w2,
                amount=amount,
                type="TRANSFER_IN",
                reference_transaction=tx_out,
            )

            w1.balance -= amount
            w2.balance += amount
            w1.save(update_fields=["balance"])
            w2.save(update_fields=["balance"])

        return Response({"status": "transferred"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def transactions(self, request, pk=None):
        wallet = self.get_object()
        transactions = wallet.transactions.all().order_by("-created_at")
        page = self.paginate_queryset(transactions)
        if page is not None:
            serializer = TransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)
