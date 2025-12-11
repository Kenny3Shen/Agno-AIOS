from pydantic import BaseModel


class CveSearchRequest(BaseModel):
    cve_id: str | None = None
    keyword: str | None = None
    source: str | None = None
    page: int = 1
    size: int = 10


class AssetSearchRequest(BaseModel):
    fingerprint: str
    page: int = 1
    size: int = 10


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    sources: list[str] | None = None
