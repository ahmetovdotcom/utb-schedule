"""First-party usage events; aggregate reports are private to the staff API."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base, get_db
from app.models.models import Group, PublishedTeacher
from app.routers.publication import verify_publish_key

router = APIRouter(prefix="/analytics", tags=["Analytics"])
LOCAL_TZ = timezone(timedelta(hours=5))
RETENTION_DAYS = 180


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(primary_key=True)
    visitor: Mapped[str] = mapped_column(index=True)
    visit: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[int] = mapped_column(index=True)
    day: Mapped[str] = mapped_column(index=True)
    hour: Mapped[int]
    kind: Mapped[str]
    mode: Mapped[str]
    target_id: Mapped[int | None]
    target_title: Mapped[str | None]
    device: Mapped[str]
    browser: Mapped[str]
    referrer: Mapped[str]
    error_code: Mapped[str | None]


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    visitor: UUID
    visit: UUID
    kind: Literal["open", "schedule", "mode", "error"]
    mode: Literal["student", "teacher"]
    target_id: int | None = Field(default=None, gt=0)
    device: Literal["phone", "tablet", "desktop", "unknown"] = "unknown"
    browser: Literal["Chrome", "Safari", "Firefox", "Edge", "Other"] = "Other"
    referrer: str = Field(default="", max_length=253, pattern=r"^[a-zA-Z0-9.-]*$")
    error_code: Literal["network", "http", "load"] | None = None

    @model_validator(mode="after")
    def schedule_target(self):
        if self.kind == "schedule" and self.target_id is None:
            raise ValueError("Schedule event requires a target")
        return self


def private_id(value):
    return hmac.new(settings.PUBLISH_SECRET_KEY.encode(), str(value).encode(), hashlib.sha256).hexdigest()


@router.post("/events", status_code=204)
async def record(data: EventInput, db: AsyncSession = Depends(get_db)):
    now = int(time.time())
    visitor = private_id(data.visitor)
    # Bound a single browser's event rate. The public reverse proxy also limits
    # aggregate ingestion, including callers rotating their visitor IDs.
    recent = await db.scalar(select(func.count()).select_from(UsageEvent).where(
        UsageEvent.visitor == visitor, UsageEvent.created_at >= now - 60))
    if recent >= 120:
        raise HTTPException(429, "Слишком много событий")
    title = None
    if data.kind == "schedule":
        model = Group if data.mode == "student" else PublishedTeacher
        target = await db.get(model, data.target_id)
        if target is None:
            raise HTTPException(404, "Расписание не найдено")
        title = target.title
    local = datetime.fromtimestamp(now, LOCAL_TZ)
    await db.execute(delete(UsageEvent).where(UsageEvent.created_at < now - RETENTION_DAYS * 86400))
    db.add(UsageEvent(id=str(data.id), visitor=visitor, visit=private_id(f"{data.visitor}:{data.visit}"),
        created_at=now, day=local.date().isoformat(), hour=local.hour,
        kind=data.kind, mode=data.mode, target_id=data.target_id if title else None,
        target_title=title, device=data.device, browser=data.browser,
        referrer=data.referrer.lower(), error_code=data.error_code))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if not await db.get(UsageEvent, str(data.id)):
            raise
    return Response(status_code=204)


@router.get("/summary", dependencies=[Depends(verify_publish_key)])
async def summary(days: int = Query(30, ge=1, le=180), db: AsyncSession = Depends(get_db)):
    now = datetime.now(LOCAL_TZ)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    since = int(start.timestamp())
    where = UsageEvent.created_at >= since
    async def count(expression, *conditions):
        return await db.scalar(select(expression).select_from(UsageEvent).where(where, *conditions)) or 0
    totals = {
        "visitors": await count(func.count(func.distinct(UsageEvent.visitor))),
        "visits": await count(func.count(func.distinct(UsageEvent.visit))),
        "opens": await count(func.count(), UsageEvent.kind == "open"),
        "schedule_views": await count(func.count(), UsageEvent.kind == "schedule"),
        "errors": await count(func.count(), UsageEvent.kind == "error"),
        "active": await count(func.count(func.distinct(UsageEvent.visitor)), UsageEvent.created_at >= int(now.timestamp()) - 300),
    }
    repeats = select(UsageEvent.visitor).where(where).group_by(UsageEvent.visitor).having(func.count(func.distinct(UsageEvent.visit)) > 1).subquery()
    totals["returning"] = await db.scalar(select(func.count()).select_from(repeats))
    daily_rows = (await db.execute(select(UsageEvent.day,
        func.count(func.distinct(UsageEvent.visitor)), func.count(func.distinct(UsageEvent.visit)))
        .where(where).group_by(UsageEvent.day))).all()
    daily_map = {day: (visitors, visits) for day, visitors, visits in daily_rows}
    daily = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        visitors, visits = daily_map.get(day, (0, 0))
        daily.append({"day": day, "visitors": visitors, "visits": visits})
    async def breakdown(column):
        rows = (await db.execute(select(column, func.count(func.distinct(UsageEvent.visit)))
            .where(where).group_by(column).order_by(func.count(func.distinct(UsageEvent.visit)).desc()).limit(20))).all()
        return [{"name": name or "Прямой переход / неизвестно", "count": value} for name, value in rows]
    async def popular(mode):
        rows = (await db.execute(select(UsageEvent.target_id, UsageEvent.target_title, func.count())
            .where(where, UsageEvent.kind == "schedule", UsageEvent.mode == mode)
            .group_by(UsageEvent.target_id, UsageEvent.target_title).order_by(func.count().desc()).limit(15))).all()
        return [{"id": id, "name": title, "count": total} for id, title, total in rows]
    hours = (await db.execute(select(UsageEvent.hour, func.count()).where(where, UsageEvent.kind == "schedule")
        .group_by(UsageEvent.hour).order_by(UsageEvent.hour))).all()
    first = await db.scalar(select(func.min(UsageEvent.created_at)))
    return {"days": days, "timezone": "Asia/Almaty", "retention_days": RETENTION_DAYS,
        "first_event_at": datetime.fromtimestamp(first, LOCAL_TZ).isoformat() if first else None,
        "generated_at": now.isoformat(), "totals": totals, "daily": daily,
        "groups": await popular("student"), "teachers": await popular("teacher"),
        "devices": await breakdown(UsageEvent.device), "browsers": await breakdown(UsageEvent.browser),
        "modes": await breakdown(UsageEvent.mode), "referrers": await breakdown(UsageEvent.referrer),
        "hours": [{"hour": hour, "count": total} for hour, total in hours]}
