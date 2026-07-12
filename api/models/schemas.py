from pydantic import BaseModel, ConfigDict, Field


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
