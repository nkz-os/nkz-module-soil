from fastapi import Depends, HTTPException, Request
from nkz_platform_sdk import require_auth


def get_tenant_id(request: Request) -> str:
    tenant = request.headers.get("X-Tenant-ID", "")
    if not tenant:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-ID header")
    return tenant


def require_auth_dep():
    return Depends(require_auth())
