from api.services.postgres_store import ensure_app_tables_async


async def initialize_database() -> None:
    await ensure_app_tables_async()
