from app.extensions import db
from app.models import User, Role, UserRole
from app.utils.security import hash_password


def seed_default_users():
    print("🌱 Seeding default users (safe/idempotent)...")

    admin_role = Role.query.filter_by(name="ADMIN").first()
    user_role = Role.query.filter_by(name="USER").first()
    if not admin_role or not user_role:
        raise RuntimeError("Roles not found. Run seed_roles_permissions() first.")

    def assign_role(user_id: int, role_id: int):
        exists = UserRole.query.filter_by(user_id=user_id, role_id=role_id).first()
        if not exists:
            db.session.add(UserRole(user_id=user_id, role_id=role_id))
            db.session.commit()

    # Admin user
    admin_email = "admin@example.com"
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            name="System Admin",
            email=admin_email,
            password_hash=hash_password("Admin123!"),
            status="ACTIVE",
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Created admin: admin@example.com / Admin123!")
    else:
        print("ℹ️ Admin already exists:", admin_email)

    assign_role(admin.id, admin_role.id)

    # Normal user
    user_email = "user@example.com"
    user = User.query.filter_by(email=user_email).first()
    if not user:
        user = User(
            name="Test User",
            email=user_email,
            password_hash=hash_password("User123!"),
            status="ACTIVE",
        )
        db.session.add(user)
        db.session.commit()
        print("✅ Created user: user@example.com / User123!")
    else:
        print("ℹ️ User already exists:", user_email)

    assign_role(user.id, user_role.id)

    print("✅ User seed done.")
