import polars as pl
from pathlib import Path
from loguru import logger

# Global cache for IP aggregated data
_ip_data_cache = {
    "dataframe": None,
    "last_loaded": None,
}

IP_DATA_PATH = "./api/data/aggregated_ip_entities.json"


def get_ip_data_cache() -> pl.DataFrame:
    """Get cached IP data or load from file if not cached"""
    global _ip_data_cache
    
    if _ip_data_cache["dataframe"] is not None:
        logger.debug("Using cached IP data")
        return _ip_data_cache["dataframe"]
    
    # Load from file
    ip_data_file = Path(IP_DATA_PATH)
    if ip_data_file.exists():
        logger.info("Loading IP data from {}", IP_DATA_PATH)
        ip_df = pl.read_json(IP_DATA_PATH)
        _ip_data_cache["dataframe"] = ip_df
        _ip_data_cache["last_loaded"] = ip_data_file.stat().st_mtime
        return ip_df
    else:
        logger.warning("IP data file not found: {}", IP_DATA_PATH)
        # Return empty dataframe with expected schema
        return pl.DataFrame({
            "ip": [],
            "port_info": [],
            "os_info": [],
            "ip_type": [],
            "domain": [],
        })


def invalidate_ip_cache():
    """Invalidate the IP data cache (call after update)"""
    global _ip_data_cache
    _ip_data_cache["dataframe"] = None
    _ip_data_cache["last_loaded"] = None
    logger.info("IP data cache invalidated")


def process_asset_data(asset_data: list[dict]) -> list[dict]:
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
    # Use cached IP data
    ip_df_agg = get_ip_data_cache()
    asset_df = asset_df.join(ip_df_agg, on="ip", how="left")
    return asset_df.to_dicts()  # Convert Polars DataFrame back to list of dicts


def aggregate_ip_entities(ip_items: list[dict]):
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
                pl.element().flatten().unique().drop_nulls()
            ),
            port_info=pl.col("port_info").list.eval(
                pl.element().flatten().unique().drop_nulls().sort()
            ),
            os_info=pl.col("os_info").list.eval(
                pl.element().flatten().unique().drop_nulls()
            ),
            ip_type=pl.col("ip_type")
            .list.eval(pl.element().flatten().unique())
            .list.get(0),
        )
    )

    ip_df_agg.write_json("./api/data/aggregated_ip_entities.json")
    # Invalidate cache after update so next query loads fresh data
    invalidate_ip_cache()
