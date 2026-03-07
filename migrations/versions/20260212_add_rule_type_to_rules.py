"""add rule_type to rules

Revision ID: 20260212_add_rule_type_to_rules
Revises: 20260201_init_schema
Create Date: 2026-02-12 11:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_add_rule_type_to_rules"
down_revision = "20260201_init_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tbl_rules",
        sa.Column("rule_type", sa.String(length=20), nullable=False, server_default="screening"),
    )


def downgrade():
    op.drop_column("tbl_rules", "rule_type")
