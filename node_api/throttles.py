from rest_framework.throttling import SimpleRateThrottle


class BaseIPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class SyncThrottle(BaseIPThrottle):
    scope = "sync"


class AddressInfoThrottle(BaseIPThrottle):
    scope = "address_info"


class AddNodeThrottle(BaseIPThrottle):
    scope = "add_node"


class TransactionThrottle(BaseIPThrottle):
    scope = "transaction"


class BlockThrottle(BaseIPThrottle):
    scope = "block"


class BlocksThrottle(BaseIPThrottle):
    scope = "blocks"
