"""ORM models. Imported so Alembic autogenerate can discover tables."""
from app.db.base import Base  # noqa: F401
from app.models.audit_logs import AuditLog  # noqa: F401
from app.models.challenges import Challenge  # noqa: F401
from app.models.users import User  # noqa: F401