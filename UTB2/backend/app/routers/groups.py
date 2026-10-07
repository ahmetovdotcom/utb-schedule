from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Group, PublicationState
from app.schemas.schemas import GroupResponse

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.get("", response_model=list[GroupResponse])
async def get_all_groups(db: AsyncSession = Depends(get_db)):
    """Получить список всех групп/подгрупп для выбора на сайте."""
    if not await db.get(PublicationState, 1):
        return []
    stmt = select(Group).order_by(Group.title)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group_by_id(group_id: int, db: AsyncSession = Depends(get_db)):
    """Получить информацию о конкретной группе."""
    if not await db.get(PublicationState, 1):
        raise HTTPException(404, "Расписание ещё не опубликовано")
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Группа не найдена"
        )
    return group
