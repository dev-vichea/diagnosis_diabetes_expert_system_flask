"""add rule target fields on rules

Revision ID: 20260212_add_rule_target_fields
Revises: 20260212_rule_single_target
Create Date: 2026-02-12 20:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_add_rule_target_fields"
down_revision = "20260212_rule_single_target"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tbl_rules", sa.Column("disease_id", sa.Integer(), nullable=True))
    op.add_column(
        "tbl_rules",
        sa.Column("base_confidence", sa.Numeric(4, 3), nullable=False, server_default="0.500"),
    )
    op.add_column(
        "tbl_rules",
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="rule_risk_level"),
            nullable=True,
            server_default="LOW",
        ),
    )

    op.create_foreign_key(
        "fk_rules_disease_id",
        "tbl_rules",
        "tbl_diseases",
        ["disease_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_tbl_rules_disease_id", "tbl_rules", ["disease_id"])

    bind = op.get_bind()
    rules = sa.table(
        "tbl_rules",
        sa.column("id", sa.Integer),
        sa.column("disease_id", sa.Integer),
        sa.column("base_confidence", sa.Numeric(4, 3)),
        sa.column("risk_level", sa.String(20)),
    )
    actions = sa.table(
        "tbl_rule_actions",
        sa.column("id", sa.Integer),
        sa.column("rule_id", sa.Integer),
        sa.column("disease_id", sa.Integer),
        sa.column("confidence", sa.Numeric(4, 3)),
    )
    diseases = sa.table(
        "tbl_diseases",
        sa.column("id", sa.Integer),
        sa.column("urgency", sa.String(20)),
    )

    rows = bind.execute(
        sa.select(
            actions.c.rule_id,
            actions.c.disease_id,
            actions.c.confidence,
            diseases.c.urgency,
        )
        .select_from(actions.join(diseases, actions.c.disease_id == diseases.c.id))
        .order_by(actions.c.rule_id.asc(), actions.c.confidence.desc(), actions.c.id.desc())
    ).fetchall()

    seen_rules = set()
    for row in rows:
        if row.rule_id in seen_rules:
            continue
        seen_rules.add(row.rule_id)
        confidence = float(row.confidence) if row.confidence is not None else 0.5
        if confidence > 1:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))
        bind.execute(
            sa.update(rules)
            .where(rules.c.id == row.rule_id)
            .values(
                disease_id=row.disease_id,
                base_confidence=confidence,
                risk_level=(str(row.urgency or "LOW").upper()),
            )
        )

    bind.execute(
        sa.update(rules)
        .where(rules.c.risk_level.is_(None))
        .values(risk_level="LOW")
    )


def downgrade():
    op.drop_index("ix_tbl_rules_disease_id", table_name="tbl_rules")
    op.drop_constraint("fk_rules_disease_id", "tbl_rules", type_="foreignkey")
    op.drop_column("tbl_rules", "risk_level")
    op.drop_column("tbl_rules", "base_confidence")
    op.drop_column("tbl_rules", "disease_id")
