from rest_framework import authentication
from rest_framework import exceptions
from wallets.models import Tenant


class TenantAPIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        tenant_id = request.META.get("HTTP_X_TENANT_ID")
        if not tenant_id:
            return None

        try:
            tenant = Tenant.objects.get(api_key=tenant_id)
        except Tenant.DoesNotExist:
            raise exceptions.AuthenticationFailed("No such tenant")

        return (None, tenant)
