from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class WSMessageEnvelope(BaseModel):
    type: str
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ref: Optional[str] = None
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, Any] = Field(default_factory=dict)


class AuthPayload(BaseModel):
    token: str