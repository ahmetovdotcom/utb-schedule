"""Read-only student schedules and iOS wallpapers."""
from functools import lru_cache
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.models.models import Group, Schedule, PublicationState
from app.schemas.schemas import LessonResponse
from app.services.wallpaper import generate_schedule_wallpaper
from app.utils.time_parser import sort_schedules_by_time

router = APIRouter(prefix="/schedules", tags=["Schedules"])
DAYS_MAP = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг",
            5: "Пятница", 6: "Суббота", 7: "Воскресенье"}


async def read_lessons(db, group_id, day):
    if not await db.get(PublicationState, 1):
        raise HTTPException(404, "Расписание ещё не опубликовано")
    if not await db.get(Group, group_id):
        raise HTTPException(404, "Группа удалена или не найдена")
    lessons = await db.scalars(select(Schedule).where(
        Schedule.group_id == group_id, Schedule.day_of_week == day))
    return sort_schedules_by_time(lessons.all())


@router.get("/{group_id}", response_model=list[LessonResponse])
async def get_schedule(group_id: int, day: int = Query(..., ge=1, le=7),
                       db: AsyncSession = Depends(get_db)):
    return await read_lessons(db, group_id, day)


@lru_cache(maxsize=64)
def wallpaper(day, content):
    # Cache by actual immutable content, never group/day alone. A publication or
    # concurrent older render cannot poison the cache for the new version.
    lessons = [SimpleNamespace(time=time, subject=subject, room=room)
               for time, subject, room in content]
    return generate_schedule_wallpaper(DAYS_MAP[day], lessons)


@router.get("/{group_id}/wallpaper.png")
async def get_schedule_wallpaper(group_id: int, day: int = Query(..., ge=1, le=7),
                                 db: AsyncSession = Depends(get_db)):
    lessons = await read_lessons(db, group_id, day)
    content = tuple((lesson.time, lesson.subject, lesson.room) for lesson in lessons)
    png = await run_in_threadpool(wallpaper, day, content)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})
