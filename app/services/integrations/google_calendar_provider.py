from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration
from app.models.mixins import utc_now


class GoogleCalendarProvider(BaseIntegrationProvider):
    id = "google-calendar"
    name = "Google Calendar"
    category = "productivity"
    description = "Read calendars, events, upcoming schedule, and event details."
    scopes = ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/calendar.events.readonly"]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    @property
    def redirect_uri(self) -> str:
        return settings.google_calendar_oauth_redirect_uri

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        calendars_payload = self.google_get(
            integration,
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            {"maxResults": 10, "minAccessRole": "reader"},
        )
        events_payload = self.google_get(
            integration,
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            {
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": utc_now().isoformat(),
                "maxResults": 10,
            },
        )
        events = [
            {
                "id": item.get("id"),
                "title": item.get("summary", "Untitled event"),
                "start": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date"),
                "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date"),
                "location": item.get("location"),
                "link": item.get("htmlLink"),
            }
            for item in events_payload.get("items", [])
        ]
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "permissions": self.permissions,
            "summary": {
                "calendar_count": len(calendars_payload.get("items", [])),
                "upcoming_events": len(events),
            },
            "items": events,
        }
