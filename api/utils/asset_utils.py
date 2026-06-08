import polars as pl
from pathlib import Path
from loguru import logger

# IP 聚合数据的全局缓存
_ip_data_cache = {
    "dataframe": None,
    "last_loaded": None,
}

IP_DATA_PATH = "./api/data/aggregated_ip_entities.json"


def get_ip_data_cache() -> pl.DataFrame:
    """获取缓存的 IP 数据，如果缓存不存在则从文件加载"""
    global _ip_data_cache

    if _ip_data_cache["dataframe"] is not None:
        logger.debug("使用缓存的 IP 数据")
        return _ip_data_cache["dataframe"]

    ip_data_file = Path(IP_DATA_PATH)
    if ip_data_file.exists():
        logger.info("从 {} 加载 IP 数据", IP_DATA_PATH)
        ip_df = pl.read_json(IP_DATA_PATH)
        _ip_data_cache["dataframe"] = ip_df
        _ip_data_cache["last_loaded"] = ip_data_file.stat().st_mtime
        return ip_df
    else:
        logger.warning("未找到 IP 数据文件: {}", IP_DATA_PATH)
        return pl.DataFrame(
            {
                "ip": [],
                "port_info": [],
                "os_info": [],
                "ip_type": [],
                "domain": [],
            }
        )


def invalidate_ip_cache():
    """使 IP 数据缓存失效（更新后调用）"""
    global _ip_data_cache
    _ip_data_cache["dataframe"] = None
    _ip_data_cache["last_loaded"] = None
    logger.info("IP 数据缓存已失效")


def process_asset_data(asset_data: list[dict]) -> list[dict]:
    """处理资产数据并与 IP 信息连接

    Args:
        asset_data: 来自 ACL API 的资产字典列表

    Returns:
        处理后的资产字典列表，包含连接的 IP 信息
    """
    if not asset_data:
        logger.info("没有资产数据需要处理")
        return []

    asset_df = pl.DataFrame(asset_data, infer_schema_length=None)
    asset_df = (
        asset_df.unique(subset=["site"])
        .select(
            "site",
            "hostname",
            "ip",
            "title",
            "status",
            "http_server",
            "finger",
            "tag",
        )
        .with_columns(
            finger=pl.col("finger").list.eval(pl.element().struct.field("name"))
        )
    )
    ip_df_agg = get_ip_data_cache()
    asset_df = asset_df.join(ip_df_agg, on="ip", how="left")
    return asset_df.to_dicts()


def aggregate_ip_entities(ip_items: list[dict]):
    """聚合 IP 实体数据并写入文件"""
    ip_df = pl.DataFrame(ip_items, infer_schema_length=None)
    ip_df_agg = (
        ip_df.select(
            pl.all().exclude("geo_asn", "geo_city", "cdn_name", "task_id", "_id")
        )
        .with_columns(
            port_info=pl.col("port_info").list.eval(
                pl.element().struct.field("port_id")
            ),
            os_info=pl.col("os_info").struct.field("name"),
        )
        .group_by("ip")
        .agg(pl.all().exclude("ip"))
        .with_columns(
            domain=pl.col("domain").list.eval(
                pl.element()
                .list.explode(keep_nulls=False, empty_as_null=False)
                .unique()
                .drop_nulls()
            ),
            port_info=pl.col("port_info").list.eval(
                pl.element()
                .list.explode(keep_nulls=False, empty_as_null=False)
                .unique()
                .drop_nulls()
                .sort()
            ),
            os_info=pl.col("os_info").list.eval(
                pl.element()
                .list.explode(keep_nulls=False, empty_as_null=False)
                .unique()
                .drop_nulls()
            ),
            ip_type=pl.col("ip_type")
            .list.eval(
                pl.element()
                .list.explode(keep_nulls=False, empty_as_null=False)
                .unique()
            )
            .list.get(0),
        )
    )

    ip_df_agg.write_json("./api/data/aggregated_ip_entities.json")
    invalidate_ip_cache()
