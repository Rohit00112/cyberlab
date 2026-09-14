"""ORM models. Imported so Alembic autogenerate can discover tables."""
from app.db.base import Base  # noqa: F401
from app.models.audit_logs import AuditLog  # noqa: F401
from app.models.badges import Badge, UserBadge  # noqa: F401
from app.models.challenges import Challenge  # noqa: F401
from app.models.competitions import (  # noqa: F401
    Competition,
    CompetitionChallenge,
    CompetitionParticipant,
    Team,
    TeamMember,
)
from app.models.hint_reveals import HintReveal  # noqa: F401
from app.models.labs import LabInstance  # noqa: F401
from app.models.learning_paths import LearningPath, LearningPathStep  # noqa: F401
from app.models.notifications import Announcement, Notification  # noqa: F401
from app.models.research import (  # noqa: F401
    RecommendationLog,
    ResearchDataset,
    ResearchExperiment,
)
from app.models.skill_profiles import UserSkillProfile  # noqa: F401
from app.models.skills import ChallengeSkill, Skill  # noqa: F401
from app.models.submissions import Submission  # noqa: F401
from app.models.users import User  # noqa: F401