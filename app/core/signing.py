import base64
import hashlib
import hmac
import time
from typing import Any


def generate_signature(params: dict[str, Any], secret_key: str, uppercase: bool = True) -> str:
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
    digest = hmac.new(secret_key.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("utf-8")
    return signature.upper() if uppercase else signature


def generate_hmac_authorization(
    access_key_id: str,
    host: str,
    method: str,
    nonce: str,
    path: str,
    secret_key: str,
    query: str | None = None,
) -> str:
    timestamp = int(time.time())
    params: dict[str, Any] = {
        "accessKeyId": access_key_id,
        "host": host,
        "method": method.upper(),
        "nonce": nonce,
        "path": path,
        "timestamp": str(timestamp),
    }
    if query:
        params["query"] = query
    signature = generate_signature(params, secret_key, uppercase=False)
    return f"LJ-HMAC-SHA256 accessKeyId={access_key_id}; nonce={nonce}; timestamp={timestamp}; signature={signature}"
