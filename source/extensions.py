import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


_redis_url = os.getenv("REDIS_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_url,
    storage_options={"socket_connect_timeout": 2} if _redis_url.startswith("redis") else {}
)
