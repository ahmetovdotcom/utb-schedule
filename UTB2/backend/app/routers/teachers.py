"""Read-only schedules from the last official publication."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.models import PublishedTeacher, PublicationState

router = APIRouter(prefix="/teachers", tags=["Teachers"])

@router.get("")
async def teachers(db: AsyncSession = Depends(get_db)):
    if not await db.get(PublicationState, 1):
        return []
    rows = await db.scalars(select(PublishedTeacher).order_by(PublishedTeacher.title, PublishedTeacher.id))
    return [{"id": row.id, "title": row.title} for row in rows]

@router.get("/{teacher_id}/schedule")
async def schedule(teacher_id: int, day: int = Query(..., ge=1, le=7), db: AsyncSession = Depends(get_db)):
    teacher = await db.get(PublishedTeacher, teacher_id)
    if not await db.get(PublicationState, 1) or teacher is None:
        raise HTTPException(404, "Преподаватель не найден в опубликованном расписании")
    return sorted((lesson for lesson in teacher.lessons if lesson["day_of_week"] == day),
                  key=lambda lesson: (lesson["time"], lesson["id"]))
