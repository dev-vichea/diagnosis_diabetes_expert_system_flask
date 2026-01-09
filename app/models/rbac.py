from sqlalchemy import UniqueConstraint
from app.extensions import db


class UserRole(db.Model):
    __tablename__ = "tbl_user_roles"

    user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="CASCADE"), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("tbl_roles.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )


class RolePermission(db.Model):
    __tablename__ = "tbl_role_permissions"

    role_id = db.Column(db.Integer, db.ForeignKey("tbl_roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("tbl_permissions.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )