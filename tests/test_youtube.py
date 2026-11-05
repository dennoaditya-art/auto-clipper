from __future__ import annotations

import json

import httpx

from autoclip import youtube


def test_upload_video_resumable(settings, monkeypatch, tmp_path):
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"fake-video-bytes")
    clip = {
        "file_path": str(clip_file),
        "title": "Judul klip",
        "topic": "bisnis",
    }
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["init"] = request
            body = json.loads(request.content)
            assert body["status"]["privacyStatus"] == "private"
            assert body["snippet"]["title"] == "Judul klip"
            return httpx.Response(200, headers={"Location": "https://upload.test/1"})
        assert request.method == "PUT"
        seen["put"] = request
        return httpx.Response(200, json={"id": "video-123"})

    monkeypatch.setattr(youtube, "access_token", lambda settings, account: "token")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        video_id = youtube.upload_video(
            settings, "utama", clip, privacy="private", client=client
        )
    finally:
        client.close()
    assert video_id == "video-123"
    assert seen["init"].url.params["uploadType"] == "resumable"
    assert seen["init"].headers["Authorization"] == "Bearer token"
    assert seen["init"].headers["X-Upload-Content-Length"] == str(len(b"fake-video-bytes"))
    assert seen["put"].headers["Content-Type"] == "video/mp4"


def test_update_video_can_change_title(settings, monkeypatch):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {"title": "lama", "categoryId": "24"},
                            "status": {"privacyStatus": "private"},
                        }
                    ]
                },
            )
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc"})

    monkeypatch.setattr(youtube, "access_token", lambda settings, account: "token")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        youtube.update_video(
            settings, "utama", "abc", title="Judul Baru", tags=["a"], client=client
        )
    finally:
        client.close()
    assert sent["body"]["snippet"]["title"] == "Judul Baru"
    assert sent["body"]["snippet"]["tags"] == ["a"]
