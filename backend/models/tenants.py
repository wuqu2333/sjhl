from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantConnectionModel:
    id: str
    name: str
    tenant_id: str
    auth_mode: str
