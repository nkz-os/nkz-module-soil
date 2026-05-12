from fastapi import Depends, Request


def get_tenant_id(request: Request) -> str:
    return request.headers.get("X-Tenant-ID", "")


def get_tenant_id_dep(request: Request) -> str:
    return request.headers.get("X-Tenant-ID", "")
