import os


class Config:
	"""Basic configuration for the Flask app.

	Reads common settings from environment variables with sensible defaults
	so the app can start locally without extra configuration.
	"""

	SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
	SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
	SQLALCHEMY_TRACK_MODIFICATIONS = False
	JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)

