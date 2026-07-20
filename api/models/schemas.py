from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CveSearchRequest(BaseModel):
    """CVE 搜索请求；空查询返回最近入库的 CVE。"""
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = ""
    source: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)


class Url2MdRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: str

    @field_validator("url")
    @classmethod
    def require_absolute_http_url(cls, value: str) -> str:
        """Reject malformed input before a failed parse is persisted."""
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("url credentials are not allowed")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("url port is invalid") from exc
        return value
