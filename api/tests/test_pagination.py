from api.utils.pagination import pagination_meta


def test_pagination_meta_basic() -> None:
    assert pagination_meta(page=2, limit=20, total_count=45) == {
        "page": 2,
        "limit": 20,
        "total_pages": 3,
        "total_count": 45,
        "search_time_ms": 0.0,
    }


def test_pagination_meta_clamps_and_empty() -> None:
    assert pagination_meta(page=0, limit=0, total_count=0) == {
        "page": 1,
        "limit": 1,
        "total_pages": 0,
        "total_count": 0,
        "search_time_ms": 0.0,
    }
