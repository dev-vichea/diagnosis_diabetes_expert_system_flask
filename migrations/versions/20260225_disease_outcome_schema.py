"""align disease schema to outcome model

Revision ID: 20260225_disease_outcome
Revises: 20260219_assessment_diag_results
Create Date: 2026-02-25 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260225_disease_outcome"
down_revision = "20260219_assessment_diag_results"
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
    if not _table_exists("tbl_diseases"):
        return

    bind = op.get_bind()

    if _column_exists("tbl_diseases", "default_next_steps") and not _column_exists("tbl_diseases", "default_recommendation"):
        op.alter_column(
            "tbl_diseases",
            "default_next_steps",
            new_column_name="default_recommendation",
            existing_type=sa.Text(),
            existing_nullable=True,
        )
    elif not _column_exists("tbl_diseases", "default_recommendation"):
        op.add_column("tbl_diseases", sa.Column("default_recommendation", sa.Text(), nullable=True))
        if _column_exists("tbl_diseases", "advice"):
            bind.execute(
                sa.text(
                    """
                    UPDATE tbl_diseases
                    SET default_recommendation = COALESCE(default_recommendation, advice)
                    """
                )
            )

    if _column_exists("tbl_diseases", "is_active") and not _column_exists("tbl_diseases", "active"):
        op.alter_column(
            "tbl_diseases",
            "is_active",
            new_column_name="active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("1"),
        )
    elif not _column_exists("tbl_diseases", "active"):
        op.add_column(
            "tbl_diseases",
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )

    if not _column_exists("tbl_diseases", "description"):
        op.add_column("tbl_diseases", sa.Column("description", sa.Text(), nullable=True))

    if _column_exists("tbl_diseases", "category"):
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET category = CASE
                    WHEN category IS NULL OR TRIM(category) = '' THEN 'other'
                    WHEN LOWER(TRIM(category)) IN ('type1', 't1dm', 'type_1', 'type-1', 'type 1') THEN 'type1'
                    WHEN LOWER(TRIM(category)) IN ('type2', 't2dm', 'type_2', 'type-2', 'type 2', 'diabetes') THEN 'type2'
                    WHEN LOWER(TRIM(category)) IN ('prediabetes', 'predm', 'pre_diabetes', 'pre-diabetes') THEN 'prediabetes'
                    WHEN LOWER(TRIM(category)) IN ('gestational', 'gdm', 'pregnancy') THEN 'gestational'
                    ELSE 'other'
                END
                """
            )
        )
        op.alter_column(
            "tbl_diseases",
            "category",
            existing_type=sa.String(length=80),
            type_=sa.Enum("type1", "type2", "prediabetes", "gestational", "other", name="disease_category"),
            nullable=False,
            server_default="other",
        )
    else:
        op.add_column(
            "tbl_diseases",
            sa.Column(
                "category",
                sa.Enum("type1", "type2", "prediabetes", "gestational", "other", name="disease_category"),
                nullable=False,
                server_default="other",
            ),
        )

    if _column_exists("tbl_diseases", "severity_level"):
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET severity_level = CASE
                    WHEN severity_level IS NULL OR TRIM(severity_level) = '' THEN 'low'
                    WHEN UPPER(TRIM(severity_level)) IN ('HIGH', 'URGENT') THEN 'high'
                    WHEN UPPER(TRIM(severity_level)) = 'MEDIUM' THEN 'medium'
                    ELSE 'low'
                END
                """
            )
        )
        op.alter_column(
            "tbl_diseases",
            "severity_level",
            existing_type=mysql.ENUM("LOW", "MEDIUM", "HIGH", "URGENT"),
            type_=sa.Enum("low", "medium", "high", name="disease_severity_level"),
            nullable=False,
            server_default="low",
        )
    else:
        op.add_column(
            "tbl_diseases",
            sa.Column(
                "severity_level",
                sa.Enum("low", "medium", "high", name="disease_severity_level"),
                nullable=False,
                server_default="low",
            ),
        )

    bind.execute(sa.text("UPDATE tbl_diseases SET active = 1 WHERE active IS NULL"))
    op.alter_column(
        "tbl_diseases",
        "active",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )

    for col in (
        "patient_label_screening",
        "patient_label_confirmed",
        "red_flag_message",
        "recommendations_json",
        "advice",
        "urgency",
        "severity",
    ):
        if _column_exists("tbl_diseases", col):
            op.drop_column("tbl_diseases", col)


def downgrade():
    if not _table_exists("tbl_diseases"):
        return

    bind = op.get_bind()

    if not _column_exists("tbl_diseases", "patient_label_screening"):
        op.add_column("tbl_diseases", sa.Column("patient_label_screening", sa.String(length=255), nullable=True))
    if not _column_exists("tbl_diseases", "patient_label_confirmed"):
        op.add_column("tbl_diseases", sa.Column("patient_label_confirmed", sa.String(length=255), nullable=True))
    if not _column_exists("tbl_diseases", "red_flag_message"):
        op.add_column("tbl_diseases", sa.Column("red_flag_message", sa.Text(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET patient_label_confirmed = COALESCE(NULLIF(patient_label_confirmed, ''), name),
                patient_label_screening = COALESCE(NULLIF(patient_label_screening, ''), CONCAT('Possible ', name, ' (screening)'))
            """
        )
    )

    if _column_exists("tbl_diseases", "default_recommendation") and not _column_exists("tbl_diseases", "default_next_steps"):
        op.alter_column(
            "tbl_diseases",
            "default_recommendation",
            new_column_name="default_next_steps",
            existing_type=sa.Text(),
            existing_nullable=True,
        )

    if _column_exists("tbl_diseases", "active") and not _column_exists("tbl_diseases", "is_active"):
        op.alter_column(
            "tbl_diseases",
            "active",
            new_column_name="is_active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("1"),
        )

    if _column_exists("tbl_diseases", "category"):
        op.alter_column(
            "tbl_diseases",
            "category",
            existing_type=sa.Enum("type1", "type2", "prediabetes", "gestational", "other", name="disease_category"),
            type_=sa.String(length=80),
            nullable=True,
        )

    if _column_exists("tbl_diseases", "severity_level"):
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET severity_level = CASE
                    WHEN LOWER(TRIM(severity_level)) = 'high' THEN 'HIGH'
                    WHEN LOWER(TRIM(severity_level)) = 'medium' THEN 'MEDIUM'
                    ELSE 'LOW'
                END
                """
            )
        )
        op.alter_column(
            "tbl_diseases",
            "severity_level",
            existing_type=sa.Enum("low", "medium", "high", name="disease_severity_level"),
            type_=mysql.ENUM("LOW", "MEDIUM", "HIGH", "URGENT"),
            nullable=False,
            server_default="LOW",
        )
