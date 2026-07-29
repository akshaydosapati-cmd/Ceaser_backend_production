import httpx
from urllib.parse import urlencode

from app.core.config.settings import settings


class SupabaseAuth:
    @property
    def supabase_url(self) -> str | None:
        return settings.supabase_url

    @property
    def anon_key(self) -> str | None:
        return settings.supabase_anon_key

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.anon_key)

    async def signup(self, email: str, password: str) -> dict:
        payload: dict = {"email": email, "password": password}
        redirect_to = self._email_redirect_to()
        if redirect_to:
            payload["options"] = {"emailRedirectTo": redirect_to}
        return await self._post("/auth/v1/signup", payload)

    async def login(self, email: str, password: str) -> dict:
        return await self._post("/auth/v1/token?grant_type=password", {"email": email, "password": password})

    async def refresh_session(self, refresh_token: str) -> dict:
        return await self._post("/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token})

    async def recover_password(self, email: str, redirect_to: str | None = None) -> dict:
        path = "/auth/v1/recover"
        redirect_target = redirect_to or self._email_redirect_to()
        if redirect_target:
            path = f"{path}?{urlencode({'redirect_to': redirect_target})}"
        return await self._post(path, {"email": email})

    async def update_password(self, access_token: str, password: str) -> dict:
        return await self._put("/auth/v1/user", {"password": password}, access_token=access_token)

    async def resend_verification(self, email: str, verification_type: str = "signup") -> dict:
        payload: dict = {"type": verification_type, "email": email}
        redirect_to = self._email_redirect_to()
        if redirect_to:
            payload["options"] = {"emailRedirectTo": redirect_to}
        return await self._post("/auth/v1/resend", payload)

    def _email_redirect_to(self) -> str | None:
        base = (settings.frontend_app_url or "").strip()
        if not base:
            return None
        return f"{base.rstrip('/')}/auth/verified/"

    async def enroll_totp(self, access_token: str, friendly_name: str) -> dict:
        return await self._post(
            "/auth/v1/factors",
            {"factor_type": "totp", "friendly_name": friendly_name},
            access_token=access_token,
        )

    async def list_factors(self, access_token: str) -> dict:
        return await self._get("/auth/v1/factors", access_token=access_token)

    async def challenge_factor(self, access_token: str, factor_id: str) -> dict:
        return await self._post(f"/auth/v1/factors/{factor_id}/challenge", {}, access_token=access_token)

    async def verify_factor(self, access_token: str, factor_id: str, challenge_id: str, code: str) -> dict:
        return await self._post(
            f"/auth/v1/factors/{factor_id}/verify",
            {"challenge_id": challenge_id, "code": code},
            access_token=access_token,
        )

    async def unenroll_factor(self, access_token: str, factor_id: str) -> dict:
        return await self._delete(f"/auth/v1/factors/{factor_id}", access_token=access_token)

    async def get_user(self, access_token: str) -> dict:
        if not self.configured:
            raise RuntimeError("Supabase Auth is not configured")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": self.anon_key or "",
                },
            )
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: dict, access_token: str | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Supabase Auth is not configured")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.supabase_url}{path}",
                json=payload,
                headers=self._headers(access_token),
            )
            response.raise_for_status()
            return response.json()

    async def _put(self, path: str, payload: dict, access_token: str | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Supabase Auth is not configured")
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.supabase_url}{path}",
                json=payload,
                headers=self._headers(access_token),
            )
            response.raise_for_status()
            return response.json()

    async def _get(self, path: str, access_token: str | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Supabase Auth is not configured")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.supabase_url}{path}", headers=self._headers(access_token))
            response.raise_for_status()
            return response.json()

    async def _delete(self, path: str, access_token: str | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Supabase Auth is not configured")
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{self.supabase_url}{path}", headers=self._headers(access_token))
            response.raise_for_status()
            return response.json() if response.content else {"status": "ok"}

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.anon_key or ""}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers


supabase_auth = SupabaseAuth()
