READ_ONLY_PERMISSIONS = {
    "google-calendar": ["calendar.events.readonly", "calendar.readonly"],
    "gmail": ["gmail.metadata", "gmail.readonly"],
    "google-drive": ["drive.metadata.readonly", "drive.readonly"],
    "google-tasks": ["tasks.readonly"],
    "google-classroom": ["classroom.courses.readonly", "classroom.coursework.me.readonly"],
    "notion": ["read_content"],
}


def permissions_for(provider: str) -> list[str]:
    return READ_ONLY_PERMISSIONS.get(provider, [])
