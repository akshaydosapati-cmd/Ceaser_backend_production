from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration


class GoogleClassroomProvider(BaseIntegrationProvider):
    id = "google-classroom"
    name = "Google Classroom"
    category = "learning"
    description = "Read courses, coursework, assignments, and due dates."
    scopes = [
        "https://www.googleapis.com/auth/classroom.courses.readonly",
        "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    ]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    @property
    def redirect_uri(self) -> str:
        return settings.google_classroom_oauth_redirect_uri

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        courses_payload = self.google_get(
            integration,
            "https://classroom.googleapis.com/v1/courses",
            {"pageSize": 10, "courseStates": "ACTIVE"},
        )
        coursework = []
        for course in courses_payload.get("courses", [])[:6]:
            try:
                work_payload = self.google_get(
                    integration,
                    f"https://classroom.googleapis.com/v1/courses/{course.get('id')}/courseWork",
                    {"pageSize": 10, "orderBy": "updateTime desc"},
                )
            except Exception:
                work_payload = {"courseWork": []}
            for work in work_payload.get("courseWork", [])[:10]:
                coursework.append(
                    {
                        "id": work.get("id"),
                        "title": work.get("title"),
                        "course": course.get("name"),
                        "state": work.get("state"),
                        "due_date": work.get("dueDate"),
                        "link": work.get("alternateLink"),
                    }
                )
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "permissions": self.permissions,
            "summary": {
                "active_courses": len(courses_payload.get("courses", [])),
                "coursework_items": len(coursework),
            },
            "items": coursework[:30],
            "courses": [{"id": course.get("id"), "name": course.get("name"), "section": course.get("section")} for course in courses_payload.get("courses", [])],
        }
