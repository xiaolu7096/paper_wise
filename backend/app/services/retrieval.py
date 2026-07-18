from dataclasses import dataclass

import numpy as np

from app.db.database import Database
from app.services.embeddings import Embedder
from app.services.text_index import is_han, search_terms


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    page: int
    text: str
    token_count: int
    score: float


def rrf(rankings: list[list[str]], constant: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def fts_match_query(question: str) -> str | None:
    stripped = question.strip()
    if len(stripped) == 1 and is_han(stripped):
        return None
    tokens = search_terms(question).split()
    if not tokens:
        return None
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


class RetrievalService:
    def __init__(self, database: Database, embedder: Embedder) -> None:
        self.database = database
        self.embedder = embedder

    def retrieve(
        self,
        paper_id: str,
        question: str,
        *,
        recall_limit: int = 12,
        result_limit: int = 6,
        token_limit: int = 4000,
    ) -> list[RetrievedChunk]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, page, text, token_count, embedding
                FROM chunks WHERE paper_id = ? ORDER BY chunk_id
                """,
                (paper_id,),
            ).fetchall()
            if not rows:
                return []

            query_vector = np.asarray(self.embedder.encode_query(question), dtype=np.float32)
            query_norm = float(np.linalg.norm(query_vector))
            if not np.isfinite(query_norm) or query_norm == 0:
                raise ValueError("Query embedding is invalid")
            query_vector /= query_norm
            matrix = np.vstack(
                [np.frombuffer(row["embedding"], dtype="<f4") for row in rows]
            )
            if matrix.shape[1] != query_vector.shape[0]:
                raise ValueError("Query and passage embedding dimensions do not match")
            similarities = matrix @ query_vector
            vector_order = np.argsort(-similarities, kind="stable")[:recall_limit]
            vector_ranking = [rows[int(index)]["chunk_id"] for index in vector_order]

            sparse_ranking: list[str] = []
            match = fts_match_query(question)
            if match:
                sparse_ranking = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT chunk_id FROM chunks_fts
                        WHERE chunks_fts MATCH ? AND paper_id = ?
                        ORDER BY bm25(chunks_fts), chunk_id LIMIT ?
                        """,
                        (match, paper_id, recall_limit),
                    )
                ]

        by_id = {row["chunk_id"]: row for row in rows}
        selected: list[RetrievedChunk] = []
        tokens = 0
        for chunk_id, score in rrf([vector_ranking, sparse_ranking]):
            row = by_id[chunk_id]
            if selected and tokens + row["token_count"] > token_limit:
                continue
            selected.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    page=row["page"],
                    text=row["text"],
                    token_count=row["token_count"],
                    score=score,
                )
            )
            tokens += row["token_count"]
            if len(selected) >= result_limit:
                break
        return selected
