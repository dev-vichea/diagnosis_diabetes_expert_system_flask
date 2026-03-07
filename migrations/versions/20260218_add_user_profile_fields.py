"""add patient profile fields to users

Revision ID: 20260218_user_profile
Revises: 20260212_rule_policy
Create Date: 2026-02-18 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_user_profile"
down_revision = "20260212_rule_policy"
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
    if not _column_exists("tbl_users", "survey_for"):
        op.add_column("tbl_users", sa.Column("survey_for", sa.String(length=20), nullable=True))
    if not _column_exists("tbl_users", "sex_at_birth"):
        op.add_column("tbl_users", sa.Column("sex_at_birth", sa.String(length=20), nullable=True))
    if not _column_exists("tbl_users", "age_years"):
        op.add_column("tbl_users", sa.Column("age_years", sa.Integer(), nullable=True))


def downgrade():
    if _column_exists("tbl_users", "age_years"):
        op.drop_column("tbl_users", "age_years")
    if _column_exists("tbl_users", "sex_at_birth"):
        op.drop_column("tbl_users", "sex_at_birth")
    if _column_exists("tbl_users", "survey_for"):
        op.drop_column("tbl_users", "survey_for")
