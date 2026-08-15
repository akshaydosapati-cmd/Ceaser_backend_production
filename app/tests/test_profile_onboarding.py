from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.auth.routes import current_user_payload, update_profile
from app.core.database.base import Base
from app.models.profile import Profile
from app.models.user import User
from app.schemas.auth import ProfileUpdateRequest


def test_onboarding_profile_is_persisted(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="new-user@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        monkeypatch.setattr("app.api.auth.routes.AuditService.record", lambda *args, **kwargs: None)
        result = update_profile(
            ProfileUpdateRequest(
                display_name="New User",
                use_case="Student",
                onboarding_data={"student_profile": {"course": "Computer Science"}},
                onboarding_completed=True,
            ),
            user,
            db,
        )

        saved = db.query(Profile).filter(Profile.user_id == user.id).one()
        assert saved.display_name == "New User"
        assert saved.use_case == "Student"
        assert saved.onboarding_data["student_profile"]["course"] == "Computer Science"
        assert saved.onboarding_completed is True
        assert result.onboarding_completed is True
        assert current_user_payload(user).display_name == "New User"
