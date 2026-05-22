from pydantic import BaseModel, Field


class DemoListItem(BaseModel):
    id: str
    filename: str
    status: str


class DemoListResponse(BaseModel):
    items: list[DemoListItem] = Field(default_factory=list)
    total: int = 0


class DemoUploadResponse(DemoListItem):
    pass


class HltvDemoResolveRequest(BaseModel):
    match_url: str

class HltvDemoResolveResponse(HltvDemoResolveRequest):
    download_url: str
    archive_url: str | None = None
