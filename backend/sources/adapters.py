"""Provider-specific, read-only source adapter helpers.

All provider responses are treated as untrusted evidence.  They are never
instructions to call a tool or to perform an external action.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import socket
import time
from datetime import datetime, timezone
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import jwt

from backend.config import settings


def split_config(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", " ").split() if item.strip()]


def sha256_payload(value: bytes | str | dict[str, Any]) -> str:
    if isinstance(value, dict):
        raw = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = value
    return hashlib.sha256(raw).hexdigest()


def redact_slack_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep enough proof for audit without storing obsolete verification tokens."""
    out = dict(payload)
    out.pop("token", None)
    authorizations = out.get("authorizations")
    if isinstance(authorizations, list):
        out["authorizations"] = [
            {
                key: item.get(key)
                for key in ("team_id", "user_id", "is_bot", "enterprise_id")
                if key in item
            }
            for item in authorizations
            if isinstance(item, dict)
        ]
    return out


def verify_slack_signature(
    *,
    secret: str,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    now: float | None = None,
) -> bool:
    if not secret or not timestamp or not signature or not signature.startswith("v0="):
        return False
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return False
    current = now if now is not None else time.time()
    if abs(current - timestamp_value) > settings.SLACK_EVENT_MAX_AGE_SECONDS:
        return False
    base = b"v0:" + timestamp.encode("ascii") + b":" + body
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def slack_event_allowed(payload: dict[str, Any]) -> bool:
    team_id = str(payload.get("team_id") or "")
    allowed_team = settings.SLACK_ALLOWED_TEAM_ID.strip()
    if not allowed_team or team_id != allowed_team:
        return False
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    if event.get("type") != "message" or event.get("bot_id") or event.get("subtype"):
        return False
    allowed_channels = set(split_config(settings.SLACK_ALLOWED_CHANNEL_IDS))
    return bool(allowed_channels) and str(event.get("channel") or "") in allowed_channels


def utc_from_epoch(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


class AlibabaOSSAdapter:
    """Read-only Alibaba Cloud OSS adapter for the NexaFlow runbook prefix.

    OSS credentials are loaded from encrypted operator configuration and are
    never returned to browser clients. The adapter only lists and reads
    objects; it does not upload, overwrite, delete, or publish them.
    """

    @staticmethod
    def configured() -> bool:
        return bool(
            settings.ALIBABA_OSS_REGION.strip()
            and settings.ALIBABA_OSS_ENDPOINT.strip()
            and settings.ALIBABA_OSS_BUCKET.strip()
            and settings.ALIBABA_OSS_PREFIX.strip()
            and settings.ALIBABA_OSS_ACCESS_KEY_ID.strip()
            and settings.ALIBABA_OSS_ACCESS_KEY_SECRET.strip()
        )

    @staticmethod
    def _extension_allowed(key: str) -> bool:
        extensions = {
            value.lower().lstrip(".")
            for value in split_config(settings.ALIBABA_OSS_ALLOWED_EXTENSIONS)
        }
        suffix = Path(key).suffix.lower().lstrip(".")
        return bool(suffix and suffix in extensions)

    @staticmethod
    def _endpoint() -> str:
        endpoint = settings.ALIBABA_OSS_ENDPOINT.strip()
        return endpoint if endpoint.startswith("http") else f"https://{endpoint}"

    @staticmethod
    def _bucket() -> Any:
        try:
            import oss2
        except ImportError as exc:  # pragma: no cover - dependency is installed in Docker
            raise RuntimeError("Alibaba OSS SDK is not installed") from exc
        if not AlibabaOSSAdapter.configured():
            raise RuntimeError("Alibaba Cloud OSS is not configured")
        auth = oss2.Auth(
            settings.ALIBABA_OSS_ACCESS_KEY_ID.strip(),
            settings.ALIBABA_OSS_ACCESS_KEY_SECRET.strip(),
        )
        prefix = settings.ALIBABA_OSS_PREFIX.strip()
        if not prefix.endswith("/"):
            settings.ALIBABA_OSS_PREFIX = f"{prefix}/"
        return oss2.Bucket(auth, AlibabaOSSAdapter._endpoint(), settings.ALIBABA_OSS_BUCKET.strip())

    @staticmethod
    def _key(document: dict[str, Any]) -> str:
        key = str(document.get("key") or "").strip()
        prefix = settings.ALIBABA_OSS_PREFIX.strip()
        if not key or key.endswith("/") or not key.startswith(prefix):
            raise RuntimeError("OSS object is outside the configured read-only prefix")
        return key

    def _list_documents_sync(self) -> list[dict[str, Any]]:
        import oss2

        bucket = self._bucket()
        prefix = settings.ALIBABA_OSS_PREFIX.strip()
        documents: list[dict[str, Any]] = []
        for item in oss2.ObjectIterator(bucket, prefix=prefix):
            key = str(getattr(item, "key", "") or "")
            if not key or key.endswith("/") or not self._extension_allowed(key):
                continue
            headers = bucket.head_object(key).headers
            documents.append(
                {
                    "key": key,
                    "etag": str(getattr(item, "etag", "") or "").strip('"'),
                    "size": int(getattr(item, "size", 0) or 0),
                    "last_modified": utc_from_epoch(getattr(item, "last_modified", None)).isoformat(),
                    "content_type": str(headers.get("Content-Type") or headers.get("content-type") or ""),
                    "bucket": settings.ALIBABA_OSS_BUCKET.strip(),
                    "region": settings.ALIBABA_OSS_REGION.strip(),
                }
            )
        documents.sort(key=lambda item: str(item.get("last_modified") or ""))
        return documents

    async def list_documents(self, modified_after: str | None = None) -> list[dict[str, Any]]:
        documents = await asyncio.to_thread(self._list_documents_sync)
        if not modified_after:
            return documents
        cutoff = datetime.fromisoformat(modified_after.replace("Z", "+00:00"))
        return [
            item
            for item in documents
            if datetime.fromisoformat(str(item["last_modified"])) > cutoff
        ]

    def _read_document_sync(self, document: dict[str, Any]) -> bytes:
        bucket = self._bucket()
        key = self._key(document)
        size = int(document.get("size") or 0)
        if size > settings.ALIBABA_OSS_MAX_FILE_BYTES:
            raise RuntimeError("OSS runbook object exceeds ALIBABA_OSS_MAX_FILE_BYTES")
        response = bucket.get_object(key)
        content = response.read(settings.ALIBABA_OSS_MAX_FILE_BYTES + 1)
        if len(content) > settings.ALIBABA_OSS_MAX_FILE_BYTES:
            raise RuntimeError("OSS runbook object exceeds ALIBABA_OSS_MAX_FILE_BYTES")
        return content

    async def read_document(self, document: dict[str, Any]) -> str:
        content = await asyncio.to_thread(self._read_document_sync, document)
        key = self._key(document)
        if Path(key).suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader

                return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)[:20000]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Could not extract text from OSS PDF: {exc}") from exc
        return content.decode("utf-8", errors="replace")[:20000]


class GoogleDriveAdapter:
    """Small read-only Drive client using the service-account JWT flow.

    We intentionally do not use Domain-Wide Delegation or write scopes.  The
    account can see only the folder explicitly shared with it by the demo
    workspace.
    """

    _scope = "https://www.googleapis.com/auth/drive.readonly"

    @staticmethod
    def configured() -> bool:
        return bool(
            settings.GOOGLE_DRIVE_FOLDER_ID.strip()
            and (settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip() or settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip())
        )

    @staticmethod
    def _credentials() -> dict[str, Any]:
        source = settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
        if not source and settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip():
            source = Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE).read_text(encoding="utf-8")
        if not source:
            raise RuntimeError("Google Drive service-account credentials are not configured")
        parsed = json.loads(source)
        required = {"client_email", "private_key", "token_uri"}
        missing = sorted(required - set(parsed))
        if missing:
            raise RuntimeError(f"Google service-account JSON missing: {', '.join(missing)}")
        return parsed

    async def _access_token(self) -> str:
        credentials = self._credentials()
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": credentials["client_email"],
                "scope": self._scope,
                "aud": credentials["token_uri"],
                "iat": now,
                "exp": now + 3600,
            },
            credentials["private_key"],
            algorithm="RS256",
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                credentials["token_uri"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Google token endpoint returned no access token")
        return token

    @staticmethod
    def _allowed_mime_types() -> set[str]:
        return set(split_config(settings.GOOGLE_DRIVE_ALLOWED_MIME_TYPES))

    async def list_documents(self, modified_after: str | None = None) -> list[dict[str, Any]]:
        token = await self._access_token()
        folder_id = settings.GOOGLE_DRIVE_FOLDER_ID.strip()
        query = f"'{folder_id}' in parents and trashed = false"
        if modified_after:
            query += f" and modifiedTime > '{modified_after}'"
        params = {
            "q": query,
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink,md5Checksum,size,parents)",
            "orderBy": "modifiedTime asc",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            response.raise_for_status()
            files = response.json().get("files", [])
        allowed = self._allowed_mime_types()
        return [item for item in files if isinstance(item, dict) and item.get("mimeType") in allowed]

    async def read_document(self, document: dict[str, Any]) -> str:
        token = await self._access_token()
        file_id = str(document.get("id") or "")
        mime = str(document.get("mimeType") or "")
        if not file_id or mime not in self._allowed_mime_types():
            raise RuntimeError("Drive document is missing or outside the allowed MIME types")
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=25.0) as client:
            if mime == "application/vnd.google-apps.document":
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    headers=headers,
                    params={"mimeType": "text/plain"},
                )
            else:
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    headers=headers,
                    params={"alt": "media"},
                )
            response.raise_for_status()
            content = response.content[: settings.GOOGLE_DRIVE_MAX_FILE_BYTES]
        if mime == "application/pdf":
            try:
                from pypdf import PdfReader

                return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)[:20000]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Could not extract text from allowed PDF: {exc}") from exc
        return content.decode("utf-8", errors="replace")[:20000]


def _hostname_is_allowed(hostname: str) -> bool:
    allowed = {value.lower() for value in split_config(settings.WEB_EVIDENCE_ALLOWED_HOSTS)}
    return hostname.lower() in allowed


async def _validate_public_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only absolute HTTPS URLs without credentials are allowed")
    hostname = parsed.hostname.lower()
    if not _hostname_is_allowed(hostname):
        raise ValueError("URL host is not in WEB_EVIDENCE_ALLOWED_HOSTS")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        addresses = {info[4][0] for info in infos}
        if not addresses:
            raise ValueError("URL host did not resolve")
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("URL host resolves to a non-public address")
    else:
        raise ValueError("Literal IP addresses are not accepted")
    return value


def _text_from_html(value: str) -> str:
    # Simple, dependency-free extraction: this is evidence display, not a DOM
    # renderer.  Keep whitespace stable for audit excerpts.
    import re

    without_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", without_scripts))).strip()


async def fetch_verified_web_evidence(url: str) -> dict[str, Any]:
    """Fetch an allowlisted public URL without following SSRF-prone redirects."""
    current = await _validate_public_url(url)
    async with httpx.AsyncClient(
        timeout=settings.WEB_EVIDENCE_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": "Company-Brain-Evidence/1.0"},
    ) as client:
        for _ in range(3):
            response = await client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise RuntimeError("Redirect response had no location")
                current = await _validate_public_url(urljoin(current, location))
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not any(kind in content_type for kind in ("text/", "application/json", "application/xml")):
                raise ValueError("URL content type is not text, JSON, or XML")
            raw = response.content[: settings.WEB_EVIDENCE_MAX_BYTES]
            text = raw.decode(response.encoding or "utf-8", errors="replace")
            if "html" in content_type:
                text = _text_from_html(text)
            return {
                "url": current,
                "content_type": content_type,
                "excerpt": text[:20000],
                "content_sha256": sha256_payload(raw),
            }
    raise RuntimeError("Too many redirects")
