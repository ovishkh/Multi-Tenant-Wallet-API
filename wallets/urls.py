from django.urls import path, include
from rest_framework.routers import DefaultRouter
from wallets.views import TenantViewSet, WalletViewSet

router = DefaultRouter()
router.register(r"tenants", TenantViewSet)
router.register(r"wallets", WalletViewSet)

urlpatterns = [
    path("v1/", include(router.urls)),
]
