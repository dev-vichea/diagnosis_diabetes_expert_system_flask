from sqlalchemy.orm import relationship
from app.extensions import db


class Permission(db.Model):
    __tablename__ = "tbl_permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)  # KB_MANAGE, DIAGNOSIS_START ...
    description = db.Column(db.String(255))

    roles = relationship("Role", secondary="tbl_role_permissions", back_populates="permissions")

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"
