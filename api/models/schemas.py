from pydantic import BaseModel, Field, ConfigDict, model_validator


class CveSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    cve_id: str | None = None
    keyword: str | None = None
    source: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)

    @model_validator(mode="after")
    def check_id_or_keyword(self) -> "CveSearchRequest":
        if not self.cve_id and not self.keyword:
            raise ValueError("请提供 CVE 编号或关键字")
        return self


class Url2MdRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    url: str


class AssetSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    fingerprint: str | None = Field(default=None, min_length=1)
    ip: str | None = Field(default=None, min_length=1)
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)

    @model_validator(mode="after")
    def check_fingerprint_or_ip(self) -> "AssetSearchRequest":
        if not self.fingerprint and not self.ip:
            raise ValueError("请提供指纹或 IP")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    response: str
    sources: list[str] | None = None
