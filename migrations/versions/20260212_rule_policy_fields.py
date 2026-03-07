"""add rule policy and template fields

Revision ID: 20260212_rule_policy
Revises: 20260212_disease_replace
Create Date: 2026-02-12 23:58:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_rule_policy"
down_revision = "20260212_disease_replace"
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
    if not _column_exists("tbl_rules", "version"):
        op.add_column("tbl_rules", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    if not _column_exists("tbl_rules", "confidence_cap_if_unconfirmed"):
        op.add_column("tbl_rules", sa.Column("confidence_cap_if_unconfirmed", sa.Numeric(4, 3), nullable=True))
    if not _column_exists("tbl_rules", "confidence_bonus_max"):
        op.add_column("tbl_rules", sa.Column("confidence_bonus_max", sa.Numeric(4, 3), nullable=True))
    if not _column_exists("tbl_rules", "min_required_matches"):
        op.add_column("tbl_rules", sa.Column("min_required_matches", sa.Integer(), nullable=True))
    if not _column_exists("tbl_rules", "stop_on_match"):
        op.add_column("tbl_rules", sa.Column("stop_on_match", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    if not _column_exists("tbl_rules", "patient_summary_template"):
        op.add_column("tbl_rules", sa.Column("patient_summary_template", sa.Text(), nullable=True))
    if not _column_exists("tbl_rules", "doctor_response_template"):
        op.add_column("tbl_rules", sa.Column("doctor_response_template", sa.Text(), nullable=True))
    if not _column_exists("tbl_rules", "advice_template"):
        op.add_column("tbl_rules", sa.Column("advice_template", sa.Text(), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE tbl_rules
            SET doctor_response_template = COALESCE(NULLIF(doctor_response_template, ''), explanation_text)
            WHERE explanation_text IS NOT NULL AND explanation_text <> ''
            """
        )
    )


def downgrade():
    if _column_exists("tbl_rules", "advice_template"):
        op.drop_column("tbl_rules", "advice_template")
    if _column_exists("tbl_rules", "doctor_response_template"):
        op.drop_column("tbl_rules", "doctor_response_template")
    if _column_exists("tbl_rules", "patient_summary_template"):
        op.drop_column("tbl_rules", "patient_summary_template")
    if _column_exists("tbl_rules", "stop_on_match"):
        op.drop_column("tbl_rules", "stop_on_match")
    if _column_exists("tbl_rules", "min_required_matches"):
        op.drop_column("tbl_rules", "min_required_matches")
    if _column_exists("tbl_rules", "confidence_bonus_max"):
        op.drop_column("tbl_rules", "confidence_bonus_max")
    if _column_exists("tbl_rules", "confidence_cap_if_unconfirmed"):
        op.drop_column("tbl_rules", "confidence_cap_if_unconfirmed")
    if _column_exists("tbl_rules", "version"):
        op.drop_column("tbl_rules", "version")
