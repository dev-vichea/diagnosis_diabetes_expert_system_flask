from datetime import datetime
from sqlalchemy.orm import relationship
from app.extensions import db


class User(db.Model):
    __tablename__ = "tbl_users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    status = db.Column(db.String(20), default="ACTIVE", nullable=False)  # ACTIVE, DISABLED
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    roles = relationship("Role", secondary="tbl_user_roles", back_populates="users")
    assessments = relationship("Assessment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"
