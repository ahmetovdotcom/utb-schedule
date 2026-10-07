"""Public read-only API responses."""
from pydantic import BaseModel, ConfigDict


class GroupResponse(BaseModel):
    id: int
    title: str
    model_config = ConfigDict(from_attributes=True)


class LessonResponse(BaseModel):
    id: int
    day_of_week: int
    time: str
    subject: str
    room: str
    delivery: str = 'in_person'
    online_url: str = ''
    meeting_id: str = ''
    passcode: str = ''
    model_config = ConfigDict(from_attributes=True)
