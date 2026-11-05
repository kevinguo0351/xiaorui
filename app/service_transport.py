"""Explicit proxy policy for official life-service MCP connections."""
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def service_http_client(headers=None, timeout=None, auth=None):
    key = 'LIFE_SERVICES_TRUST_ENV'
    value = os.environ.get(key, dotenv_values(ROOT / '.env').get(key) or 'true')
    return httpx.AsyncClient(
        headers=headers, auth=auth,
        timeout=timeout if timeout is not None else httpx.Timeout(30, read=300),
        trust_env=str(value).lower() != 'false',
    )
