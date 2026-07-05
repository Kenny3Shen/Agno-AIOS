from __future__ import annotations

from hashlib import md5
from typing import Any

from agno.filters import FilterExpr
from agno.knowledge.document import Document
from agno.utils.log import log_error, log_info, log_warning
from agno.vectordb.distance import Distance
from agno.vectordb.pgvector import PgVector
from agno.vectordb.pgvector.index import HNSW, Ivfflat
from agno.vectordb.score import normalize_score, score_to_distance_threshold
from agno.vectordb.search import SearchType
from anyio import to_thread
from sqlalchemy import and_, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.schema import CreateSchema
from sqlalchemy.sql.expression import desc, func, literal_column, select


_async_pgvector_engines: dict[str, AsyncEngine] = {}


def _async_postgres_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg_async://"):
        return db_url
    if db_url.startswith("postgresql+psycopg://"):
        return db_url.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+psycopg_async://", 1)
    return db_url


def get_async_pgvector_engine(db_url: str) -> AsyncEngine:
    async_db_url = _async_postgres_url(db_url)
    engine = _async_pgvector_engines.get(async_db_url)
    if engine is None:
        engine = create_async_engine(async_db_url, pool_pre_ping=True)
        _async_pgvector_engines[async_db_url] = engine
    return engine


async def dispose_async_pgvector_engines() -> None:
    engines = list(_async_pgvector_engines.values())
    _async_pgvector_engines.clear()
    for engine in engines:
        await engine.dispose()


class AsyncPgVector(PgVector):
    """PgVector adapter that keeps Agno's table contract but uses AsyncEngine I/O."""

    def __init__(self, *args: Any, async_db_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        db_url = async_db_url or self.db_url or str(self.db_engine.url)
        self.async_engine = get_async_pgvector_engine(db_url)

    async def _query_embedding(self, query: str) -> list[float] | None:
        async_get_embedding = getattr(self.embedder, "async_get_embedding", None)
        if async_get_embedding is not None:
            return await async_get_embedding(query)
        return await to_thread.run_sync(self.embedder.get_embedding, query)

    def _record_for_document(
        self,
        document: Document,
        content_hash: str,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        try:
            cleaned_content = self._clean_content(document.content)
            base_id = document.id or md5(cleaned_content.encode()).hexdigest()
            record_id = md5(f"{base_id}_{content_hash}".encode()).hexdigest()
            meta_data = dict(document.meta_data or {})
            if filters:
                meta_data.update(filters)
            return {
                "id": record_id,
                "name": document.name,
                "meta_data": meta_data,
                "filters": filters,
                "content": cleaned_content,
                "embedding": document.embedding,
                "usage": document.usage,
                "content_hash": content_hash,
                "content_id": document.content_id,
            }
        except Exception as exc:
            log_error(f"Error processing document '{document.name}': {str(exc)}")
            return None

    async def _records_for_batch(
        self,
        documents: list[Document],
        content_hash: str,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        await self._async_embed_documents(documents)
        records: dict[str, dict[str, Any]] = {}
        for idx, document in enumerate(documents):
            if document.embedding is not None and isinstance(document.embedding, list) and len(document.embedding) == 0:
                log_warning(f"Document {idx} '{document.name}' has empty embedding (length 0)")
            record = self._record_for_document(document, content_hash, filters)
            if record is not None:
                records[record["id"]] = record
        return list(records.values())

    async def async_create(self) -> None:
        async with self.async_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            if self.create_schema and self.schema is not None:
                await conn.execute(CreateSchema(self.schema, if_not_exists=True))
            await conn.run_sync(lambda sync_conn: self.table.create(sync_conn, checkfirst=True))

    async def async_insert(
        self,
        content_hash: str,
        documents: list[Document],
        filters: dict[str, Any] | None = None,
        batch_size: int = 100,
    ) -> None:
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i : i + batch_size]
            records = await self._records_for_batch(batch_docs, content_hash, filters)
            if not records:
                continue
            async with self.async_engine.begin() as conn:
                await conn.execute(postgresql.insert(self.table), records)
            log_info(f"Inserted batch of {len(records)} documents.")

    async def _async_upsert(
        self,
        content_hash: str,
        documents: list[Document],
        filters: dict[str, Any] | None = None,
        batch_size: int = 100,
    ) -> None:
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i : i + batch_size]
            records = await self._records_for_batch(batch_docs, content_hash, filters)
            if not records:
                log_info("No valid records to upsert in this batch.")
                continue
            insert_stmt = postgresql.insert(self.table).values(records)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": insert_stmt.excluded.name,
                    "meta_data": insert_stmt.excluded.meta_data,
                    "filters": insert_stmt.excluded.filters,
                    "content": insert_stmt.excluded.content,
                    "embedding": insert_stmt.excluded.embedding,
                    "usage": insert_stmt.excluded.usage,
                    "content_hash": insert_stmt.excluded.content_hash,
                    "content_id": insert_stmt.excluded.content_id,
                },
            )
            async with self.async_engine.begin() as conn:
                await conn.execute(upsert_stmt)
            log_info(f"Upserted batch of {len(records)} documents.")

    async def async_upsert(
        self,
        content_hash: str,
        documents: list[Document],
        filters: dict[str, Any] | None = None,
        batch_size: int = 100,
    ) -> None:
        async with self.async_engine.begin() as conn:
            await conn.execute(self.table.delete().where(self.table.c.content_hash == content_hash))
        await self._async_upsert(content_hash, documents, filters, batch_size)

    def _where_filters(
        self,
        stmt: Any,
        filters: dict[str, Any] | list[FilterExpr] | None,
    ) -> Any:
        if filters is None:
            return stmt
        if isinstance(filters, dict):
            return stmt.where(self.table.c.meta_data.contains(filters))
        conditions = [
            self._dsl_to_sqlalchemy(item.to_dict() if hasattr(item, "to_dict") else item, self.table)
            for item in filters
        ]
        return stmt.where(and_(*conditions))

    async def _set_vector_index_options(self, conn: Any) -> None:
        if self.vector_index is None:
            return
        if isinstance(self.vector_index, Ivfflat):
            await conn.execute(text(f"SET LOCAL ivfflat.probes = {self.vector_index.probes}"))
        elif isinstance(self.vector_index, HNSW):
            await conn.execute(text(f"SET LOCAL hnsw.ef_search = {self.vector_index.ef_search}"))

    def _document_from_row(
        self,
        row: Any,
        *,
        score_key: str | None = None,
        score_value: float | None = None,
    ) -> Document:
        meta_data = dict(row.meta_data) if row.meta_data else {}
        if score_key is not None and score_value is not None:
            meta_data[score_key] = score_value
        return Document(
            id=row.id,
            name=row.name,
            meta_data=meta_data,
            content=row.content,
            embedder=self.embedder,
            embedding=row.embedding,
            usage=row.usage,
        )

    async def _rerank_async(self, query: str, documents: list[Document]) -> list[Document]:
        reranker = self.reranker
        if not reranker:
            return documents
        return await to_thread.run_sync(lambda: reranker.rerank(query=query, documents=documents))

    async def async_vector_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | list[FilterExpr] | None = None,
    ) -> list[Document]:
        query_embedding = await self._query_embedding(query)
        if query_embedding is None:
            log_error(f"Error getting embedding for Query: {query}")
            return []

        if self.distance == Distance.l2:
            distance_expr = self.table.c.embedding.l2_distance(query_embedding)
        elif self.distance == Distance.cosine:
            distance_expr = self.table.c.embedding.cosine_distance(query_embedding)
        elif self.distance == Distance.max_inner_product:
            distance_expr = self.table.c.embedding.max_inner_product(query_embedding)
        else:
            log_error(f"Unknown distance metric: {self.distance}")
            return []

        stmt = select(
            self.table.c.id,
            self.table.c.name,
            self.table.c.meta_data,
            self.table.c.content,
            self.table.c.embedding,
            self.table.c.usage,
            distance_expr.label("distance"),
        )
        stmt = self._where_filters(stmt, filters)
        if self.similarity_threshold is not None:
            distance_threshold = score_to_distance_threshold(self.similarity_threshold, self.distance)
            stmt = stmt.where(
                distance_expr <= -distance_threshold
                if self.distance == Distance.max_inner_product
                else distance_expr <= distance_threshold
            )
        stmt = stmt.order_by(distance_expr).limit(limit)

        try:
            async with self.async_engine.begin() as conn:
                await self._set_vector_index_options(conn)
                rows = (await conn.execute(stmt)).all()
        except Exception as exc:
            log_error(f"Error performing semantic search: {str(exc)}")
            await self.async_create()
            return []

        documents = []
        for row in rows:
            raw_distance = -row.distance if self.distance == Distance.max_inner_product else row.distance
            documents.append(
                self._document_from_row(
                    row,
                    score_key="similarity_score",
                    score_value=normalize_score(raw_distance, self.distance),
                )
            )
        return await self._rerank_async(query, documents)

    async def async_keyword_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | list[FilterExpr] | None = None,
    ) -> list[Document]:
        ts_vector = func.to_tsvector(self.content_language, self.table.c.content)
        ts_query = self._build_ts_query(query)
        if ts_query is None:
            return []
        text_rank = func.ts_rank_cd(ts_vector, ts_query)
        stmt = select(
            self.table.c.id,
            self.table.c.name,
            self.table.c.meta_data,
            self.table.c.content,
            self.table.c.embedding,
            self.table.c.usage,
        )
        stmt = self._where_filters(stmt, filters).order_by(text_rank.desc()).limit(limit)

        try:
            async with self.async_engine.begin() as conn:
                rows = (await conn.execute(stmt)).all()
        except Exception as exc:
            log_error(f"Error performing keyword search: {str(exc)}")
            await self.async_create()
            return []
        return [self._document_from_row(row) for row in rows]

    async def async_hybrid_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | list[FilterExpr] | None = None,
    ) -> list[Document]:
        query_embedding = await self._query_embedding(query)
        if query_embedding is None:
            log_error(f"Error getting embedding for Query: {query}")
            return []

        ts_vector = func.to_tsvector(self.content_language, self.table.c.content)
        ts_query = self._build_ts_query(query) or literal_column("''::tsquery")
        raw_text_rank = func.ts_rank_cd(ts_vector, ts_query)
        text_rank = raw_text_rank / (raw_text_rank + 0.1)

        if self.distance == Distance.l2:
            vector_distance = self.table.c.embedding.l2_distance(query_embedding)
            vector_score = 1 / (1 + vector_distance)
        elif self.distance == Distance.cosine:
            vector_distance = self.table.c.embedding.cosine_distance(query_embedding)
            vector_score = func.greatest(0.0, 1 - vector_distance)
        elif self.distance == Distance.max_inner_product:
            negative_ip = self.table.c.embedding.max_inner_product(query_embedding)
            inner_product = -negative_ip
            vector_score = func.greatest(0.0, func.least(1.0, (inner_product + 1) / 2))
        else:
            log_error(f"Unknown distance metric: {self.distance}")
            return []

        if not 0 <= self.vector_score_weight <= 1:
            raise ValueError("vector_score_weight must be between 0 and 1")
        hybrid_score = (self.vector_score_weight * vector_score) + ((1 - self.vector_score_weight) * text_rank)

        stmt = select(
            self.table.c.id,
            self.table.c.name,
            self.table.c.meta_data,
            self.table.c.content,
            self.table.c.embedding,
            self.table.c.usage,
            hybrid_score.label("hybrid_score"),
        )
        stmt = self._where_filters(stmt, filters)
        if self.similarity_threshold is not None:
            stmt = stmt.where(hybrid_score >= self.similarity_threshold)
        stmt = stmt.order_by(desc("hybrid_score")).limit(limit)

        try:
            async with self.async_engine.begin() as conn:
                await self._set_vector_index_options(conn)
                rows = (await conn.execute(stmt)).all()
        except Exception as exc:
            log_error(f"Error performing hybrid search: {str(exc)}")
            return []

        documents = [
            self._document_from_row(row, score_key="similarity_score", score_value=float(row.hybrid_score))
            for row in rows
        ]
        return await self._rerank_async(query, documents)

    async def async_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | list[FilterExpr] | None = None,
    ) -> list[Document]:
        if self.search_type == SearchType.vector:
            return await self.async_vector_search(query=query, limit=limit, filters=filters)
        if self.search_type == SearchType.keyword:
            return await self.async_keyword_search(query=query, limit=limit, filters=filters)
        if self.search_type == SearchType.hybrid:
            return await self.async_hybrid_search(query=query, limit=limit, filters=filters)
        log_error(f"Invalid search type '{self.search_type}'.")
        return []
