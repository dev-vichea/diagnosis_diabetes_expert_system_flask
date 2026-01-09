from sqlalchemy.orm import relationship
from app.extensions import db


class Role(db.Model):
    __tablename__ = "tbl_roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)  # Admin, User

    users = relationship("User", secondary="tbl_user_roles", back_populates="roles")
    permissions = relationship("Permission", secondary="tbl_role_permissions", back_populates="roles")

    def __repr__(self) -> str:
        return f"<Role {self.id} {self.name}>"
