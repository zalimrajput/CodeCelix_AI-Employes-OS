"""Retrieval of context chunks for the AI engine (documents + knowledge base).

Uses pgvector cosine search when an embedding model/keys are configured,
otherwise falls back to a keyword scan so RAG still works in a demo setup.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_base import KnowledgeArticle

logger = logging.getLogger("app.ai.retriever")


def _vector_ok() -> bool:
    try:
        from app.ai.embeddings import embeddings_available

        return embeddings_available()
    except Exception:
        return False


def _embed_query(query: str):
    from app.ai.embeddings import embed

    vectors = embed([query])
    return vectors[0] if vectors else None


def _vector_param(vector) -> str:
    """pgvector text form ("[0.1,0.2,...]") for raw-SQL binding."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _vector_search_articles(
    db: Session, organization_id, vector, limit: int
) -> list[KnowledgeArticle]:
    from sqlalchemy import text

    sql = text(
        "SELECT id, title, content, source "
        "FROM knowledge_articles WHERE organization_id = :org "
        "AND embedding IS NOT NULL "
        "ORDER BY embedding <=> CAST(:v AS vector) ASC LIMIT :lim"
    )
    rows = db.execute(
        sql,
        {"org": str(organization_id), "v": _vector_param(vector), "lim": limit},
    )
    return [
        KnowledgeArticle(
            id=r[0], title=r[1], content=r[2], source=r[3]
        )
        for r in rows
    ]


def _keyword_score(query_lower: str, haystack: str) -> int:
    """Score text against a query; whole-phrase hits weigh more than words."""
    haystack_l = (haystack or "").lower()
    keywords = [w for w in query_lower.split() if len(w) > 3]
    if not keywords:
        return 1 if query_lower and query_lower in haystack_l else 0
    return haystack_l.count(query_lower) * 3 + sum(
        haystack_l.count(w) for w in keywords
    )


def retrieve_documents(
    db: Session, organization_id, query: str | None, limit: int = 4
) -> list[dict]:
    """Return document text chunks relevant to the query."""
    if not (query or "").strip():
        return []
    vector = _embed_query(query)
    if vector is not None:
        from sqlalchemy import text

        sql = text(
            "SELECT filename, extracted_text "
            "FROM documents WHERE organization_id = :org "
            "AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :limit"
        )
        rows = db.execute(
            sql,
            {"org": str(organization_id), "v": _vector_param(vector), "limit": limit},
        ).fetchall()
        return [
            {"title": r[0] or "Document", "content": (r[1] or "")[:2000], "source": "document"}
            for r in rows
        ]
    # keyword fallback (title + a larger text window, phrase-aware scoring)
    rows = (
        db.query(Document)
        .filter(Document.organization_id == organization_id)
        .order_by(Document.created_at.desc())
        .limit(50)
        .all()
    )
    query_lower = query.lower()
    scored = []
    for doc in rows:
        haystack = f"{doc.filename or ''} {(doc.extracted_text or '')[:12000]}"
        if not (doc.extracted_text or "").strip():
            continue
        score = _keyword_score(query_lower, haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "title": doc.filename,
            "content": (doc.extracted_text or "")[:2000],
            "source": "document",
        }
        for _, doc in scored[:limit]
    ]


def retrieve_articles(
    db: Session, organization_id, query: str | None, limit: int = 4
) -> list[dict]:
    if not (query or "").strip():
        return []
    vector = _embed_query(query)
    if vector is not None:
        rows = _vector_search_articles(db, organization_id, vector, limit)
        return [
            {
                "title": a.title,
                "content": (a.content or "")[:2000],
                "source": a.source or "knowledge_base",
            }
            for a in rows
        ]
    rows = (
        db.query(KnowledgeArticle)
        .filter(KnowledgeArticle.organization_id == organization_id)
        .order_by(KnowledgeArticle.updated_at.desc())
        .limit(50)
        .all()
    )
    query_lower = query.lower()
    scored = []
    for article in rows:
        haystack = f"{article.title or ''} {article.content or ''}"
        score = _keyword_score(query_lower, haystack)
        if score:
            scored.append((score, article))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "title": article.title,
            "content": (article.content or "")[:2000],
            "source": "knowledge_base",
        }
        for _, article in scored[:limit]
    ]


def retrieve_context(
    db: Session,
    organization_id,
    query: str,
    limit: int = 4,
    include_documents: bool = True,
    include_articles: bool = True,
) -> list[dict]:
    """Combined RAG context as plain dicts for ``with_memory_context``."""
    results: list[dict] = []
    if include_documents:
        results.extend(retrieve_documents(db, organization_id, query, limit))
    if include_articles:
        results.extend(retrieve_articles(db, organization_id, query, limit))
    return results[:limit]