import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Früh laden — extensions.py wird vor load_dotenv() in app.py importiert.
# Ohne diesen Call ist REDIS_URL beim Limiter-Init noch None → memory://.
load_dotenv()

_redis_url = os.getenv("REDIS_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_url,
    storage_options={"socket_connect_timeout": 2} if _redis_url.startswith("redis") else {}
)
