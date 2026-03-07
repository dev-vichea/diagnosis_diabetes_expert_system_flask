"""add disease profile fields

Revision ID: 20260212_disease_profile
Revises: 20260212_add_rule_target_fields
Create Date: 2026-02-12 22:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_disease_profile"
down_revision = "20260212_add_rule_target_fields"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    query = sa.text(
        """
        SELECT COUNT(*) AS count_value
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND COLUMN_NAME = :column_name
        """
    )
    return bool(
        bind.execute(
            query,
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
    )


def upgrade():
    if not _column_exists("tbl_diseases", "description"):
        op.add_column("tbl_diseases", sa.Column("description", sa.Text(), nullable=True))
    if not _column_exists("tbl_diseases", "category"):
        op.add_column("tbl_diseases", sa.Column("category", sa.String(length=80), nullable=True))
    if not _column_exists("tbl_diseases", "severity_level"):
        op.add_column(
            "tbl_diseases",
            sa.Column(
                "severity_level",
                sa.Enum("LOW", "MEDIUM", "HIGH", "URGENT", name="disease_severity_level"),
                nullable=False,
                server_default="LOW",
            ),
        )
    if not _column_exists("tbl_diseases", "patient_label_screening"):
        op.add_column("tbl_diseases", sa.Column("patient_label_screening", sa.String(length=255), nullable=True))
    if not _column_exists("tbl_diseases", "patient_label_confirmed"):
        op.add_column("tbl_diseases", sa.Column("patient_label_confirmed", sa.String(length=255), nullable=True))
    if not _column_exists("tbl_diseases", "default_next_steps"):
        op.add_column("tbl_diseases", sa.Column("default_next_steps", sa.Text(), nullable=True))
    if not _column_exists("tbl_diseases", "red_flag_message"):
        op.add_column("tbl_diseases", sa.Column("red_flag_message", sa.Text(), nullable=True))

    bind = op.get_bind()
    diseases = sa.table(
        "tbl_diseases",
        sa.column("id", sa.Integer),
        sa.column("urgency", sa.String(20)),
        sa.column("advice", sa.Text),
        sa.column("severity_level", sa.String(20)),
        sa.column("description", sa.Text),
        sa.column("default_next_steps", sa.Text),
    )

    rows = bind.execute(
        sa.select(
            diseases.c.id,
            diseases.c.urgency,
            diseases.c.advice,
        )
    ).fetchall()

    for row in rows:
        urgency = str(row.urgency or "LOW").upper()
        if urgency not in {"LOW", "MEDIUM", "HIGH"}:
            urgency = "LOW"
        severity_level = "HIGH" if urgency == "HIGH" else urgency

        values = {
            "severity_level": severity_level,
        }
        if row.advice:
            values["default_next_steps"] = row.advice
        bind.execute(
            sa.update(diseases)
            .where(diseases.c.id == row.id)
            .values(**values)
        )


def downgrade():
    if _column_exists("tbl_diseases", "red_flag_message"):
        op.drop_column("tbl_diseases", "red_flag_message")
    if _column_exists("tbl_diseases", "default_next_steps"):
        op.drop_column("tbl_diseases", "default_next_steps")
    if _column_exists("tbl_diseases", "patient_label_confirmed"):
        op.drop_column("tbl_diseases", "patient_label_confirmed")
    if _column_exists("tbl_diseases", "patient_label_screening"):
        op.drop_column("tbl_diseases", "patient_label_screening")
    if _column_exists("tbl_diseases", "severity_level"):
        op.drop_column("tbl_diseases", "severity_level")
    if _column_exists("tbl_diseases", "category"):
        op.drop_column("tbl_diseases", "category")
    if _column_exists("tbl_diseases", "description"):
        op.drop_column("tbl_diseases", "description")
