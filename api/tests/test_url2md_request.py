import pytest
from pydantic import ValidationError

from api.models.schemas import Url2MdRequest


@pytest.mark.parametrize(
    "url",
    [
        "anquanke",
        "ftp://example.com/article",
        "https://",
        "javascript:alert(1)",
        "https://user:password@example.com/article",
        "https://example.com:invalid/article",
    ],
)
def test_url2md_request_rejects_invalid_urls_before_persistence(url: str):
    with pytest.raises(ValidationError):
        Url2MdRequest(url=url)


def test_url2md_request_accepts_an_absolute_http_url():
    request = Url2MdRequest(url=" https://example.com/article ")
    assert request.url == "https://example.com/article"
