from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
import logging
import os
import re
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import Settings, UploadConfig
from .secure import SecureError, protect, unprotect

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
CATEGORY_ID = "22"


class AuthError(RuntimeError):
    pass


class UploadError(RuntimeError):
    pass


def client_secret_path(settings: Settings) -> Path:
    override = os.environ.get("AUTOCLIP_GOOGLE_CLIENT_SECRET")
    return Path(override) if override else settings.root / "config" / "client_secret.json"


def token_path(settings: Settings, account_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", account_id)
    return settings.root / "data" / "tokens" / f"youtube-{safe}.bin"


def _client_config(settings: Settings) -> dict[str, str]:
    path = client_secret_path(settings)
    if not path.exists():
        raise AuthError(
            f"client secret tidak ditemukan: {path}. "
            "Buat OAuth client Desktop di Google Cloud lalu simpan JSON-nya di sana."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthError(f"client secret tidak valid: {exc}") from exc
    raw = data.get("installed") or data.get("web") or data
    if not isinstance(raw, dict):
        raise AuthError("client secret tidak berisi objek installed/web")
    client_id = raw.get("client_id")
    client_secret = raw.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise AuthError("client secret tidak punya client_id/client_secret")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": raw.get("auth_uri") or AUTH_URL,
        "token_uri": raw.get("token_uri") or TOKEN_URL,
    }


def _load_token(settings: Settings, account_id: str) -> dict[str, Any]:
    path = token_path(settings, account_id)
    if not path.exists():
        raise AuthError(
            f"token YouTube untuk akun {account_id} belum ada. "
            f"Jalankan: python -m autoclip auth youtube --account {account_id}"
        )
    try:
        return json.loads(unprotect(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError, SecureError) as exc:
        raise AuthError(f"token YouTube tidak bisa dibaca: {exc}") from exc


def _save_token(settings: Settings, account_id: str, token: dict[str, Any]) -> Path:
    path = token_path(settings, account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = protect(json.dumps(token).encode("utf-8"))
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(payload)
    os.replace(temp, path)
    return path


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _callback_server(state: str):
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                body = b"state OAuth tidak cocok"
                self.send_response(400)
            elif query.get("error"):
                result["error"] = query["error"][0]
                body = b"OAuth ditolak"
                self.send_response(400)
            elif query.get("code"):
                result["code"] = query["code"][0]
                body = b"OAuth berhasil. Tutup tab ini."
                self.send_response(200)
            else:
                self.send_response(404)
                body = b"not found"
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    return server, int(server.server_address[1]), result


def authorize(
    settings: Settings,
    account_id: str,
    *,
    open_browser: bool = True,
    url_callback: Callable[[str], None] | None = None,
) -> Path:
    secret = _client_config(settings)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    server, port, result = _callback_server(state)
    redirect_uri = f"http://127.0.0.1:{port}/"
    params = {
        "client_id": secret["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{secret['auth_uri']}?{urlencode(params)}"
    if url_callback:
        url_callback(auth_url)
    if open_browser:
        webbrowser.open(auth_url)
    deadline = time.time() + 300
    try:
        while not result and time.time() < deadline:
            server.timeout = max(1.0, min(5.0, deadline - time.time()))
            server.handle_request()
    finally:
        server.server_close()
    if result.get("error"):
        raise AuthError(f"OAuth ditolak: {result['error']}")
    code = result.get("code")
    if not code:
        raise AuthError("OAuth timeout: tidak ada callback dari browser")
    response = httpx.post(
        secret["token_uri"],
        data={
            "client_id": secret["client_id"],
            "client_secret": secret["client_secret"],
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise AuthError(f"tukar code gagal: {response.status_code} {response.text[:300]}")
    token = response.json()
    if not token.get("refresh_token"):
        raise AuthError(
            "Google tidak memberi refresh_token. Cabut akses aplikasi di akun Google "
            "lalu ulangi auth."
        )
    token["expires_at"] = time.time() + float(token.get("expires_in", 3600)) - 60
    return _save_token(settings, account_id, token)


def access_token(settings: Settings, account_id: str) -> str:
    token = _load_token(settings, account_id)
    current = token.get("access_token")
    expires = float(token.get("expires_at") or 0)
    if isinstance(current, str) and current and expires > time.time() + 60:
        return current
    refresh = token.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise AuthError("refresh token hilang; ulangi autoclip auth youtube")
    secret = _client_config(settings)
    response = httpx.post(
        secret["token_uri"],
        data={
            "client_id": secret["client_id"],
            "client_secret": secret["client_secret"],
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise AuthError(f"refresh token gagal: {response.status_code} {response.text[:300]}")
    payload = response.json()
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthError("refresh token tidak mengembalikan access_token")
    token["access_token"] = access
    token["expires_at"] = time.time() + float(payload.get("expires_in", 3600)) - 60
    if payload.get("refresh_token"):
        token["refresh_token"] = payload["refresh_token"]
    _save_token(settings, account_id, token)
    return access


def _hashtag_list(text: str) -> list[str]:
    return [word for word in text.split() if word.startswith("#") and len(word) > 1]


def _description(
    clip, upload: UploadConfig | None, extra_hashtags: str = ""
) -> str:
    parts: list[str] = []
    topic = str(clip["topic"]).strip()
    if topic and topic != "umum":
        parts.append(topic)
    if upload is not None:
        if upload.credit:
            parts.append(upload.credit)
        if upload.hashtags:
            parts.append(upload.hashtags)
    if extra_hashtags:
        parts.append(extra_hashtags)
    return "\n\n".join(parts)[:4900]


def _metadata(
    clip,
    privacy: str,
    upload: UploadConfig | None = None,
    publish_at: str | None = None,
    extra_hashtags: str = "",
) -> dict[str, Any]:
    title = str(clip["title"]).replace("<", "").replace(">", "").strip()[:100] or "Klip"
    tags = _hashtag_list(extra_hashtags)
    if not tags and upload is not None:
        tags = _hashtag_list(upload.hashtags)
    category = upload.category_id if upload is not None else CATEGORY_ID
    snippet: dict[str, Any] = {
        "title": title,
        "description": _description(clip, upload, extra_hashtags),
        "categoryId": category,
    }
    if tags:
        snippet["tags"] = [tag.lstrip("#") for tag in tags][:15]
    status: dict[str, Any] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    return {"snippet": snippet, "status": status}


def _check_publish_at(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UploadError(f"publish_at bukan ISO-8601: {value}") from exc
    if moment.tzinfo is None:
        raise UploadError("publish_at harus menyertakan zona waktu (mis. Z)")
    if moment <= datetime.now(timezone.utc):
        raise UploadError(f"publish_at harus di masa depan: {value}")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_thumbnail(
    settings: Settings,
    account_id: str,
    video_id: str,
    image: Path,
    *,
    client: httpx.Client | None = None,
) -> None:
    if not image.exists():
        raise UploadError(f"thumbnail tidak ditemukan: {image}")
    token = access_token(settings, account_id)
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(120.0))
    try:
        response = client.post(
            THUMBNAIL_URL,
            params={"videoId": video_id, "uploadType": "media"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "image/jpeg",
            },
            content=image.read_bytes(),
        )
        if response.status_code not in {200, 201}:
            raise UploadError(
                f"set thumbnail gagal: {response.status_code} {response.text[:300]}"
            )
    finally:
        if owns_client:
            client.close()


def fetch_video(
    settings: Settings,
    account_id: str,
    video_id: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    token = access_token(settings, account_id)
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0))
    try:
        response = client.get(
            VIDEO_URL,
            params={"part": "snippet,status", "id": video_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise UploadError(
                f"ambil video gagal: {response.status_code} {response.text[:300]}"
            )
        items = response.json().get("items") or []
        if not items:
            raise UploadError(f"video tidak ditemukan: {video_id}")
        return items[0]
    finally:
        if owns_client:
            client.close()


def update_video(
    settings: Settings,
    account_id: str,
    video_id: str,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy: str | None = None,
    publish_at: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if privacy is not None and privacy not in {"private", "unlisted", "public"}:
        raise UploadError(f"privacy tidak valid: {privacy}")
    current = fetch_video(settings, account_id, video_id, client=client)
    snippet = dict(current.get("snippet") or {})
    body: dict[str, Any] = {"id": video_id}
    parts: list[str] = []
    has_snippet = description is not None or tags is not None
    if has_snippet:
        if description is not None:
            snippet["description"] = description[:4900]
        if tags is not None:
            snippet["tags"] = tags[:15]
        snippet.setdefault(
            "categoryId", upload.category_id if upload else CATEGORY_ID
        )
        body["snippet"] = snippet
        parts.append("snippet")
    if privacy is not None or publish_at is not None:
        status = dict(current.get("status") or {})
        if publish_at is not None:
            status["publishAt"] = publish_at
            status["privacyStatus"] = "private"
        if privacy is not None:
            status["privacyStatus"] = privacy
        status.setdefault("selfDeclaredMadeForKids", False)
        body["status"] = status
        parts.append("status")
    if not parts:
        return current
    token = access_token(settings, account_id)
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60.0))
    try:
        response = client.put(
            VIDEO_URL,
            params={"part": ",".join(parts)},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if response.status_code != 200:
            raise UploadError(
                f"update video gagal: {response.status_code} {response.text[:500]}"
            )
        return response.json()
    finally:
        if owns_client:
            client.close()


def upload_video(
    settings: Settings,
    account_id: str,
    clip,
    privacy: str = "private",
    *,
    upload: UploadConfig | None = None,
    publish_at: str | None = None,
    extra_hashtags: str = "",
    client: httpx.Client | None = None,
) -> str:
    path = Path(clip["file_path"])
    if not path.exists():
        raise UploadError(f"file klip hilang: {path}")
    if privacy not in {"private", "unlisted", "public"}:
        raise UploadError(f"privacy tidak valid: {privacy}")
    if publish_at:
        publish_at = _check_publish_at(publish_at)
    token = access_token(settings, account_id)
    size = path.stat().st_size
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Upload-Content-Length": str(size),
        "X-Upload-Content-Type": "video/mp4",
    }
    owns_client = client is None
    client = client or httpx.Client(
        timeout=httpx.Timeout(120.0, read=600.0, write=600.0)
    )
    try:
        init = client.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers=headers,
            json=_metadata(clip, privacy, upload, publish_at, extra_hashtags),
        )
        if init.status_code not in {200, 201}:
            raise UploadError(
                f"inisialisasi upload gagal: {init.status_code} {init.text[:500]}"
            )
        location = init.headers.get("Location")
        if not location:
            raise UploadError("YouTube tidak mengembalikan URL upload")
        with path.open("rb") as handle:
            response = client.put(
                location,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(size),
                },
                content=handle,
            )
        if response.status_code not in {200, 201}:
            raise UploadError(
                f"upload gagal: {response.status_code} {response.text[:500]}"
            )
        payload = response.json()
        video_id = payload.get("id")
        if not isinstance(video_id, str) or not video_id:
            raise UploadError("respons YouTube tidak berisi video id")
        thumb = path.with_suffix(".jpg")
        if upload is not None and upload.thumbnail and thumb.exists():
            try:
                set_thumbnail(settings, account_id, video_id, thumb, client=client)
                log.info("thumbnail terpasang untuk %s", video_id)
            except (UploadError, httpx.HTTPError) as exc:
                log.warning("thumbnail %s gagal: %s", video_id, exc)
        return video_id
    finally:
        if owns_client:
            client.close()

