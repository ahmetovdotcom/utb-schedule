"""The only write endpoint: atomically replace the entire official publication."""
import hashlib
import hmac
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Group, Schedule, User, PublishedGroupLink, PublicationState, PublishedTeacher, ManualPublicationSource
from app.schemas.publication import PublicationPayload

router = APIRouter(tags=["Publication"])
security = HTTPBearer(auto_error=False)


def verify_publish_key(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    key = settings.PUBLISH_SECRET_KEY
    if not key or len(key) < 32:
        raise HTTPException(503, "Публикация не настроена")
    if not credentials or not hmac.compare_digest(credentials.credentials.encode(), key.encode()):
        raise HTTPException(401, "Недействительный ключ публикации")


def state_response(state):
    if state is None:
        return {"published": False}
    return {"published": True, "source_id": state.source_id, "revision": state.revision,
            "published_at": state.published_at, "groups_count": state.groups_count,
            "lessons_count": state.lessons_count}


@router.get("/publication")
async def publication_status(db: AsyncSession = Depends(get_db)):
    return state_response(await db.get(PublicationState, 1))


@router.post("/publication")
async def retired_publication():
    raise HTTPException(410, "Публикация из timetable-system отключена. Используйте manual-scheduler.")


@router.post("/manual-publication", dependencies=[Depends(verify_publish_key)])
async def publish(payload: PublicationPayload, db: AsyncSession = Depends(get_db)):
    # Serialize publishers across processes, including the very first publication.
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(734162901)"))
    else:  # SQLite used by isolated tests.
        await db.execute(text("BEGIN IMMEDIATE"))
    digest = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    state = await db.get(PublicationState, 1)
    binding = await db.get(ManualPublicationSource, 1)
    if binding and binding.source_id != str(payload.source_id):
        raise HTTPException(409, "UTB2 подключён к другой базе manual-scheduler")
    if state and binding:
        if state.source_id != str(payload.source_id):
            raise HTTPException(409, "Другой источник публикаций: проверьте базу системы сотрудников")
        if payload.revision < state.revision:
            raise HTTPException(409, "Эта версия устарела")
        if payload.revision == state.revision:
            if digest != state.payload_hash:
                raise HTTPException(409, "Содержимое версии не совпадает")
            return state_response(state)

    if binding is None:
        db.add(ManualPublicationSource(id=1, source_id=str(payload.source_id)))

    groups = (await db.scalars(select(Group))).all()
    links = (await db.scalars(select(PublishedGroupLink))).all()
    by_id = {group.id: group for group in groups}
    by_source = {link.source_id: by_id[link.group_id] for link in links} if binding else {}
    by_title = {group.title: group for group in groups} if binding is None else {}
    chosen = {}
    for incoming in payload.groups:
        existing = by_source.get(str(incoming.source_id)) or by_title.get(incoming.title)
        if existing:
            chosen[incoming.source_id] = existing

    # Clear lessons and mappings inside this transaction. Readers see the previous
    # committed version until commit. Preserve existing group IDs for links/iOS.
    await db.execute(delete(PublishedTeacher))
    for teacher in payload.teachers:
        db.add(PublishedTeacher(**teacher.model_dump(mode="json")))
    await db.execute(delete(Schedule))
    await db.execute(delete(PublishedGroupLink))
    keep_ids = {group.id for group in chosen.values()}
    removed_ids = [group.id for group in groups if group.id not in keep_ids]
    if removed_ids:
        await db.execute(update(User).where(User.group_id.in_(removed_ids)).values(group_id=None, is_approved=False))
        await db.execute(delete(Group).where(Group.id.in_(removed_ids)))
    # Temporary unique names allow swaps/renames under the existing unique constraint.
    for group in chosen.values():
        group.title = f"__sync_{uuid4().hex}"
    await db.flush()
    count = 0
    for incoming in payload.groups:
        group = chosen.get(incoming.source_id)
        if group is None:
            group = Group(title=incoming.title)
            db.add(group)
        else:
            group.title = incoming.title
        await db.flush()
        db.add(PublishedGroupLink(source_id=str(incoming.source_id), group_id=group.id))
        for lesson in incoming.lessons:
            db.add(Schedule(group_id=group.id, **lesson.model_dump()))
            count += 1
    if state is None:
        state = PublicationState(id=1)
        db.add(state)
    state.source_id = str(payload.source_id)
    state.revision = payload.revision
    state.published_at = payload.published_at.isoformat()
    state.payload_hash = digest
    state.groups_count = len(payload.groups)
    state.lessons_count = count
    result = state_response(state)
    await db.commit()
    return result
