"""Procedure registry (Build Guideline, Section 2 and Section 5).

Every analysis request is checked against this registry. Phase and tool
labels, display names, and colors come from the active model version, never
from code.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import db
from app.auth import AuthUser, get_current_user

router = APIRouter(prefix="/procedures", tags=["procedures"])


class Label(BaseModel):
    code: str
    name: str
    color: str
    order: int = 0


class ModelVersion(BaseModel):
    id: uuid.UUID
    name: str
    architecture: str | None = None
    phase_labels: list[Label]
    tool_labels: list[Label]
    metrics: dict[str, Any]
    thresholds: dict[str, Any]


class Procedure(BaseModel):
    code: str
    name: str
    modality: str
    analysis_enabled: bool
    model_version: ModelVersion | None = None


def _row_to_procedure(row: dict[str, Any]) -> Procedure:
    mv = None
    if row.get("mv_id"):
        mv = ModelVersion(
            id=row["mv_id"],
            name=row["mv_name"],
            architecture=row["mv_architecture"],
            phase_labels=[
                Label(**x) for x in sorted(row["phase_labels"], key=lambda x: x.get("order", 0))
            ],
            tool_labels=[
                Label(**x) for x in sorted(row["tool_labels"], key=lambda x: x.get("order", 0))
            ],
            metrics=row["metrics"] or {},
            thresholds=row["thresholds"] or {},
        )
    return Procedure(
        code=row["code"],
        name=row["name"],
        modality=row["modality"],
        analysis_enabled=row["analysis_enabled"],
        model_version=mv,
    )


_QUERY = """
select p.code, p.name, p.modality, p.analysis_enabled, p.display_order,
       mv.id as mv_id, mv.name as mv_name, mv.architecture as mv_architecture,
       mv.phase_labels, mv.tool_labels, mv.metrics, mv.thresholds
from public.procedures p
left join public.model_versions mv on mv.id = p.model_version_id
"""


@router.get("", response_model=list[Procedure])
def list_procedures(user: AuthUser = Depends(get_current_user)) -> list[Procedure]:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(_QUERY + " order by p.display_order, p.name")
        rows = cur.fetchall()
    return [_row_to_procedure(r) for r in rows]


@router.get("/{code}", response_model=Procedure)
def get_procedure(code: str, user: AuthUser = Depends(get_current_user)) -> Procedure:
    with db.user_connection(user) as conn, conn.cursor() as cur:
        cur.execute(_QUERY + " where p.code = %s", (code,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown procedure")
    return _row_to_procedure(row)
