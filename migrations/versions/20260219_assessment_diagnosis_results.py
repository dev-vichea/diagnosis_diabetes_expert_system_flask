"""add assessment diagnosis results table

Revision ID: 20260219_assessment_diag_results
Revises: 20260218_user_profile
Create Date: 2026-02-19 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260219_assessment_diag_results"
down_revision = "20260218_user_profile"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    if not _table_exists("tbl_assessment_diagnosis_results"):
        op.create_table(
            "tbl_assessment_diagnosis_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assessment_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
            sa.Column(
                "evidence_level",
                sa.Enum("HIGH", "MODERATE", "LOW", name="diagnosis_evidence_level"),
                nullable=False,
            ),
            sa.Column(
                "risk_level",
                sa.Enum("LOW", "MEDIUM", "HIGH", name="diagnosis_candidate_risk_level"),
                nullable=False,
            ),
            sa.Column("trace_json", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["assessment_id"], ["tbl_assessments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["tbl_diseases.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("assessment_id", "disease_id", name="uq_assessment_diagnosis_disease"),
            mysql_engine="InnoDB",
        )
        op.create_index(
            "ix_assessment_diag_results_assessment",
            "tbl_assessment_diagnosis_results",
            ["assessment_id"],
        )
        op.create_index(
            "ix_assessment_diag_results_disease",
            "tbl_assessment_diagnosis_results",
            ["disease_id"],
        )
        op.create_index(
            "ix_assessment_diag_results_evidence",
            "tbl_assessment_diagnosis_results",
            ["evidence_level"],
        )

    if _table_exists("tbl_diagnosis_runs"):
        if not _column_exists("tbl_diagnosis_runs", "facts_json"):
            op.add_column("tbl_diagnosis_runs", sa.Column("facts_json", sa.JSON(), nullable=True))
        if not _column_exists("tbl_diagnosis_runs", "engine_version"):
            op.add_column("tbl_diagnosis_runs", sa.Column("engine_version", sa.String(length=40), nullable=True))
        if not _column_exists("tbl_diagnosis_runs", "final_message"):
            op.add_column("tbl_diagnosis_runs", sa.Column("final_message", sa.String(length=255), nullable=True))

    # Backfill one candidate per legacy diagnosis run row.
    bind = op.get_bind()
    runs = sa.table(
        "tbl_diagnosis_runs",
        sa.column("id", sa.Integer),
        sa.column("assessment_id", sa.Integer),
        sa.column("disease_id", sa.Integer),
        sa.column("risk_level", sa.String(20)),
        sa.column("confidence", sa.Numeric(4, 3)),
        sa.column("trace_json", sa.JSON),
        sa.column("created_at", sa.DateTime),
    )
    results = sa.table(
        "tbl_assessment_diagnosis_results",
        sa.column("assessment_id", sa.Integer),
        sa.column("disease_id", sa.Integer),
        sa.column("score", sa.Integer),
        sa.column("confidence", sa.Numeric(4, 3)),
        sa.column("evidence_level", sa.String(20)),
        sa.column("risk_level", sa.String(20)),
        sa.column("trace_json", sa.JSON),
        sa.column("created_at", sa.DateTime),
    )
    if _table_exists("tbl_diagnosis_runs") and _table_exists("tbl_assessment_diagnosis_results"):
        rows = bind.execute(
            sa.select(
                runs.c.id,
                runs.c.assessment_id,
                runs.c.disease_id,
                runs.c.risk_level,
                runs.c.confidence,
                runs.c.trace_json,
                runs.c.created_at,
            ).order_by(runs.c.created_at.desc(), runs.c.id.desc())
        ).fetchall()
        seen_pairs = set()
        for row in rows:
            key = (row.assessment_id, row.disease_id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            confidence = float(row.confidence) if row.confidence is not None else 0.0
            evidence_level = "LOW"
            if confidence >= 0.8:
                evidence_level = "HIGH"
            elif confidence >= 0.47:
                evidence_level = "MODERATE"
            score = int(round(confidence * 150))

            bind.execute(
                sa.insert(results).values(
                    assessment_id=row.assessment_id,
                    disease_id=row.disease_id,
                    score=score,
                    confidence=confidence,
                    evidence_level=evidence_level,
                    risk_level=(str(row.risk_level or "LOW").upper()),
                    trace_json=row.trace_json or {},
                    created_at=row.created_at,
                )
            )


def downgrade():
    if _table_exists("tbl_diagnosis_runs"):
        if _column_exists("tbl_diagnosis_runs", "final_message"):
            op.drop_column("tbl_diagnosis_runs", "final_message")
        if _column_exists("tbl_diagnosis_runs", "engine_version"):
            op.drop_column("tbl_diagnosis_runs", "engine_version")
        if _column_exists("tbl_diagnosis_runs", "facts_json"):
            op.drop_column("tbl_diagnosis_runs", "facts_json")

    if _table_exists("tbl_assessment_diagnosis_results"):
        op.drop_index("ix_assessment_diag_results_evidence", table_name="tbl_assessment_diagnosis_results")
        op.drop_index("ix_assessment_diag_results_disease", table_name="tbl_assessment_diagnosis_results")
        op.drop_index("ix_assessment_diag_results_assessment", table_name="tbl_assessment_diagnosis_results")
        op.drop_table("tbl_assessment_diagnosis_results")
