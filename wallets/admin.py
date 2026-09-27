from django.contrib import admin
from wallets.models import Tenant, Wallet, Transaction, IdempotencyKey

admin.site.register(Tenant)
admin.site.register(Wallet)
admin.site.register(Transaction)
admin.site.register(IdempotencyKey)
