from datetime import date, datetime
from pydantic import BaseModel, Field

from schemas.base import UTCDateTimeModel


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=128)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class AdminUserResponse(UTCDateTimeModel):
    user_id: str
    username: str
    role: str
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    total: int


class AdminUsageRow(BaseModel):
    usage_date: date
    user_id: str
    username: str
    model: str
    call_count: int
    input_uncached_tokens: int
    input_cache_read_tokens: int
    input_cache_write_tokens: int
    output_tokens: int
    total_tokens: int


class AdminUsageTotals(BaseModel):
    call_count: int
    input_uncached_tokens: int
    input_cache_read_tokens: int
    input_cache_write_tokens: int
    output_tokens: int
    total_tokens: int


class AdminUsageResponse(BaseModel):
    rows: list[AdminUsageRow]
    totals: AdminUsageTotals


class AdminUserStatsRow(UTCDateTimeModel):
    user_id: str | None
    username: str
    role: str
    projects: int = 0
    files: int = 0
    ready_files: int = 0
    storage_bytes: int = 0
    sessions: int = 0
    messages: int = 0
    outputs: int = 0
    llm_calls: int = 0
    tokens: int = 0
    last_active_at: datetime | None = None


class AdminUserStatsTotals(BaseModel):
    projects: int = 0
    files: int = 0
    ready_files: int = 0
    storage_bytes: int = 0
    sessions: int = 0
    messages: int = 0
    outputs: int = 0
    llm_calls: int = 0
    tokens: int = 0
    active_users: int = 0


class AdminUserStatsResponse(BaseModel):
    period_days: int
    rows: list[AdminUserStatsRow]
    totals: AdminUserStatsTotals
