"""Publication contract for manual-scheduler and UTB2; keep identical."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PublishedLesson(StrictModel):
    day_of_week: int = Field(ge=1, le=7)
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")
    subject: str = Field(min_length=1, max_length=512)
    room: str = Field(min_length=1, max_length=620)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.time[:5] >= self.time[6:]:
            raise ValueError("Время окончания должно быть позже начала")
        return self


class PublishedGroup(StrictModel):
    source_id: UUID
    title: str = Field(min_length=1, max_length=512)
    lessons: list[PublishedLesson] = Field(max_length=500)

    @model_validator(mode="after")
    def no_overlaps(self):
        previous = {}
        for lesson in sorted(self.lessons, key=lambda item: (item.day_of_week, item.time)):
            if previous.get(lesson.day_of_week, "") > lesson.time[:5]:
                raise ValueError(f"Пересечение пар в группе {self.title}")
            previous[lesson.day_of_week] = lesson.time[6:]
        return self


class TeacherLesson(PublishedLesson):
    id: int = Field(gt=0)
    groups: list[str] = Field(min_length=1, max_length=10000)


class PublishedTeacher(StrictModel):
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=512)
    lessons: list[TeacherLesson] = Field(max_length=500)


class PublicationPayload(StrictModel):
    schema_version: Literal[1] = 1
    source_id: UUID
    revision: int = Field(gt=0)
    published_at: AwareDatetime
    teachers: list[PublishedTeacher] = Field(default_factory=list, max_length=10000)
    groups: list[PublishedGroup] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_groups(self):
        if len({teacher.id for teacher in self.teachers}) != len(self.teachers):
            raise ValueError("Повторяющиеся преподаватели")
        for field in ("source_id", "title"):
            values = [getattr(group, field) for group in self.groups]
            if len(values) != len(set(values)):
                raise ValueError(f"Повторяющиеся группы: {field}")
        return self
