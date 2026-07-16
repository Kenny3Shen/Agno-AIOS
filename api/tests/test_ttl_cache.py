import time

from api.utils.ttl_cache import TtlCache


def test_ttl_cache_hit_and_clear() -> None:
    cache: TtlCache[str] = TtlCache(ttl_sec=60)
    assert cache.get() is None
    assert cache.set("v1") == "v1"
    assert cache.get() == "v1"
    cache.clear()
    assert cache.get() is None


def test_ttl_cache_expires() -> None:
    cache: TtlCache[int] = TtlCache(ttl_sec=0.01)
    cache.set(7)
    assert cache.get() == 7
    time.sleep(0.02)
    assert cache.get() is None
