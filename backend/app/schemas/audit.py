from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_type: str
    actor_id: str
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    request_id: str | None
    created_at: datetime
