from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    role: Literal["viewer", "operator", "admin"] = "viewer"


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    role: Literal["viewer", "operator", "admin"] | None = None
    is_active: bool | None = None

