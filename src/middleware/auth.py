# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# In-memory store for API keys
# Structure: {"api_key": {"client_id": "name", "permissions": []}}
API_KEYS: Dict[str, Dict[str, str]] = {}

# HTTP Bearer token security scheme
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def init_api_keys():
    """
    Initialize API keys from environment variables on server startup.

    Environment variables:
    - ADMIN_API_KEY: Admin-level API key (sk_live_ prefix)
    - DEV_API_KEY: Development API key (sk_test_ prefix)
    - Add more keys as needed

    Note: In production, consider loading from a database or secret manager.
    """
    global API_KEYS

    # Load admin key
    admin_key = os.getenv("ADMIN_API_KEY")
    if admin_key:
        API_KEYS[admin_key] = {
            "client_id": "admin",
            "description": "Admin API key",
        }
        logger.info("Loaded ADMIN_API_KEY")

    # Load dev key
    dev_key = os.getenv("DEV_API_KEY")
    if dev_key:
        API_KEYS[dev_key] = {
            "client_id": "dev-client",
            "description": "Development API key",
        }
        logger.info("Loaded DEV_API_KEY")

    # Load additional keys (format: API_KEY_1, API_KEY_2, etc.)
    key_num = 1
    while True:
        key = os.getenv(f"API_KEY_{key_num}")
        if not key:
            break
        API_KEYS[key] = {
            "client_id": f"client-{key_num}",
            "description": f"API key {key_num}",
        }
        logger.info(f"Loaded API_KEY_{key_num}")
        key_num += 1

    if not API_KEYS:
        logger.warning(
            "No API keys loaded! Set ADMIN_API_KEY or DEV_API_KEY in environment. "
            "Authentication will be enforced but no keys are valid."
        )
    else:
        logger.info(f"Initialized {len(API_KEYS)} API key(s)")


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, str]:
    """
    Verify the API key from the Authorization header.

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        Dict with client_id and other metadata

    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    if not credentials:
        logger.warning("Missing authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header. Include 'Authorization: Bearer YOUR_API_KEY'",
        )

    api_key = credentials.credentials

    # Validate key format
    if not api_key.startswith(("sk_live_", "sk_test_")):
        logger.warning(f"Invalid API key format: {api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Keys must start with 'sk_live_' or 'sk_test_'",
        )

    # Check if key exists
    if api_key not in API_KEYS:
        logger.warning(f"Invalid API key attempted: {api_key[:15]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Check your credentials.",
        )

    # Key is valid
    client_info = API_KEYS[api_key]
    logger.info(f"Authenticated client: {client_info['client_id']}")

    return client_info


def optional_verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
) -> Optional[Dict[str, str]]:
    """
    Optional authentication that respects SKIP_AUTH setting.

    If SKIP_AUTH=true, allows requests without authentication.
    If SKIP_AUTH=false, enforces API key authentication.

    Returns:
        Dict with client info if authenticated, or None if SKIP_AUTH=true
    """
    skip_auth = os.getenv("SKIP_AUTH", "false").lower() == "true"

    if skip_auth:
        # Auth is disabled, allow all requests
        return {"client_id": "anonymous", "skip_auth": True}

    # Auth is enabled, verify the key
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header. Include 'Authorization: Bearer YOUR_API_KEY'",
        )

    api_key = credentials.credentials

    # Validate key format
    if not api_key.startswith(("sk_live_", "sk_test_")):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Keys must start with 'sk_live_' or 'sk_test_'",
        )

    # Check if key exists
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Check your credentials.",
        )

    # Key is valid
    client_info = API_KEYS[api_key]
    logger.info(f"Authenticated client: {client_info['client_id']}")

    return client_info
