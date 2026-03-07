"""enforce single disease target per rule

Revision ID: 20260212_rule_single_target
Revises: 20260212_add_rule_type_to_rules
Create Date: 2026-02-12 12:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_rule_single_target"
down_revision = "20260212_add_rule_type_to_rules"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    actions = sa.table(
        "tbl_rule_actions",
        sa.column("id", sa.Integer),
        sa.column("rule_id", sa.Integer),
        sa.column("confidence", sa.Numeric(4, 3)),
    )

    rows = bind.execute(
        sa.select(actions.c.id, actions.c.rule_id, actions.c.confidence)
        .order_by(
            actions.c.rule_id.asc(),
            actions.c.confidence.desc(),
            actions.c.id.desc(),
        )
    ).fetchall()

    keep_by_rule = {}
    delete_ids = []
    for row in rows:
        if row.rule_id in keep_by_rule:
            delete_ids.append(row.id)
            continue
        keep_by_rule[row.rule_id] = row.id

    if delete_ids:
        bind.execute(sa.delete(actions).where(actions.c.id.in_(delete_ids)))

    constraint_exists = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) AS count_value
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = 'tbl_rule_actions'
              AND CONSTRAINT_TYPE = 'UNIQUE'
              AND CONSTRAINT_NAME = 'uq_rule_single_disease'
            """
        )
    ).scalar()

    if not constraint_exists:
        op.create_unique_constraint(
            "uq_rule_single_disease",
            "tbl_rule_actions",
            ["rule_id"],
        )


def downgrade():
    bind = op.get_bind()
    constraint_exists = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) AS count_value
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = 'tbl_rule_actions'
              AND CONSTRAINT_TYPE = 'UNIQUE'
              AND CONSTRAINT_NAME = 'uq_rule_single_disease'
            """
        )
    ).scalar()
    if constraint_exists:
        op.drop_constraint("uq_rule_single_disease", "tbl_rule_actions", type_="unique")
