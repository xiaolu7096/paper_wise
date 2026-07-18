import json
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import Annotation, AnnotationCreate
from app.db.database import Database
from app.services.papers import utc_now


class AnnotationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self, paper_id: str) -> list[Annotation]:
        self._paper(paper_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM annotations WHERE paper_id = ?
                   ORDER BY page IS NULL ASC, page ASC, created_at ASC, annotation_id ASC""",
                (paper_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def create(self, paper_id: str, value: AnnotationCreate) -> Annotation:
        paper = self._paper(paper_id)
        if value.page is not None and value.page > paper.page_count:
            raise AppError(422, "PAGE_OUT_OF_RANGE", "Page is outside the paper")
        if value.asset_id is not None:
            with self.database.connect() as connection:
                asset = connection.execute(
                    "SELECT 1 FROM assets WHERE paper_id = ? AND asset_id = ?",
                    (paper_id, value.asset_id),
                ).fetchone()
            if asset is None:
                raise AppError(404, "ASSET_NOT_FOUND", "Asset not found")
        annotation_id = str(uuid4())
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO annotations (
                       annotation_id, paper_id, kind, page, bbox_json,
                       viewport_rotation, selected_text, asset_id,
                       ai_explanation, note, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    annotation_id,
                    paper_id,
                    value.kind,
                    value.page,
                    json.dumps(value.bbox) if value.bbox else None,
                    value.viewport_rotation,
                    value.selected_text,
                    value.asset_id,
                    value.ai_explanation,
                    value.note,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM annotations WHERE annotation_id = ?", (annotation_id,)
            ).fetchone()
        return self._from_row(row)

    def delete(self, paper_id: str, annotation_id: str) -> None:
        self._paper(paper_id)
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM annotations WHERE paper_id = ? AND annotation_id = ?",
                (paper_id, annotation_id),
            )
        if cursor.rowcount == 0:
            raise AppError(404, "ANNOTATION_NOT_FOUND", "Annotation not found")

    def _paper(self, paper_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
        if row is None:
            raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")
        from app.api.schemas import Paper
        return Paper(**dict(row))

    @staticmethod
    def _from_row(row) -> Annotation:
        return Annotation(
            annotation_id=row["annotation_id"],
            paper_id=row["paper_id"],
            kind=row["kind"],
            page=row["page"],
            bbox=json.loads(row["bbox_json"]) if row["bbox_json"] else None,
            viewport_rotation=row["viewport_rotation"],
            selected_text=row["selected_text"],
            asset_id=row["asset_id"],
            ai_explanation=row["ai_explanation"],
            note=row["note"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
