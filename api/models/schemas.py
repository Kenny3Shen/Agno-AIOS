from pydantic import BaseModel, Field, ConfigDict, model_validator


class CveSearchRequest(BaseModel):
    """CVE 搜索请求，单一查询词，匹配 cve_id 或 description"""
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1)
    source: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)

    @model_validator(mode="after")
    def check_query(self) -> "CveSearchRequest":
        if not self.query:
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
