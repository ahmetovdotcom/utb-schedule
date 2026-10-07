from contextlib import asynccontextmanager
from sqlalchemy import inspect, text
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine

# Импортируем модульные роутеры
from app.routers.analytics import router as analytics_router
from app.routers.teachers import router as teachers_router
from app.routers.groups import router as groups_router
from app.routers.publication import router as publication_router
from app.routers.schedules import router as schedules_router

# Импортируем модели обязательно, чтобы Base знал о них!
import app.models.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- СОБЫТИЕ ПРИ СТАРТЕ ПРИЛОЖЕНИЯ ---
    async with engine.begin() as conn:
        # Создает таблицы в БД, если их еще нет
        await conn.run_sync(Base.metadata.create_all)
        columns = {c['name'] for c in await conn.run_sync(lambda c: inspect(c).get_columns('schedules'))}
        for column, length, default in [('delivery',20,'in_person'), ('online_url',2048,''), ('meeting_id',100,''), ('passcode',100,'')]:
            if column not in columns:
                await conn.execute(text(f"ALTER TABLE schedules ADD COLUMN {column} VARCHAR({length}) NOT NULL DEFAULT '{default}'"))
        # Older publications used short VARCHAR columns. Preserve full manual names.
        if conn.dialect.name == 'postgresql':
            for table, column, length in [('groups','title',512), ('schedules','subject',512),
                                           ('schedules','room',620), ('published_teachers','title',512)]:
                columns = await conn.run_sync(lambda c: inspect(c).get_columns(table))
                previous = next(c['type'] for c in columns if c['name'] == column)
                if getattr(previous, 'length', None) is not None and previous.length < length:
                    await conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR({length})'))

    yield

    # --- СОБЫТИЕ ПРИ ОСТАНОВКЕ ---
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept"]


)


api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(analytics_router)
api_v1_router.include_router(teachers_router)
api_v1_router.include_router(groups_router)
api_v1_router.include_router(publication_router)
api_v1_router.include_router(schedules_router)

app.include_router(api_v1_router)






@app.middleware("http")
async def prevent_stale_api_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
