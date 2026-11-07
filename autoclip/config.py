from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Paths:
    incoming: Path
    work: Path
    review: Path
    published: Path
    database: Path
    logs: Path


@dataclass(frozen=True)
class TranscriptionConfig:
    model: str
    compute_type: str
    language: str | None
    vad: bool


@dataclass(frozen=True)
class SelectionConfig:
    clips_per_video: int
    min_duration_seconds: float
    max_duration_seconds: float
    min_score: float
    chunk_seconds: float
    provider: str
    gemini_model: str
    ollama_model: str
    ollama_url: str


@dataclass(frozen=True)
class RenderConfig:
    width: int
    height: int
    crf: int
    preset: str
    encoder: str
    face_crop: bool
    face_sample_fps: float
    subtitles: bool
    subtitle_max_chars: int
    subtitle_style: str
    subtitle_language: str
    hook_overlay: bool
    hook_seconds: float
    emoji_hook: bool
    zoom_punch: bool
    loudnorm: bool


@dataclass(frozen=True)
class FocusConfig:
    """Kunci niche: sumber yang diproses dan kata kunci yang menaikkan skor."""

    sources: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    keyword_bonus: float = 0.0


@dataclass(frozen=True)
class UploadConfig:
    hashtags: str
    credit: str
    thumbnail: bool
    schedule_start: str
    schedule_interval_hours: float
    slots: tuple[str, ...] = ()
    utc_offset_hours: float = 7.0
    auto_publish: bool = False
    slots_by_day: dict[str, tuple[str, ...]] = field(default_factory=dict)
    category_id: str = "22"


@dataclass(frozen=True)
class SafetyConfig:
    max_sources_per_run: int
    max_clips_per_source: int
    require_rights_approved: bool
    min_source_age_seconds: int
    retain_work_days: int
    rights_status: str
    rights_reference: str


@dataclass(frozen=True)
class Account:
    id: str
    display_name: str
    niche: str
    enabled: bool
    rights_approved: bool
    approval_required: bool
    youtube_enabled: bool
    youtube_privacy: str
    tiktok_enabled: bool
    tiktok_privacy: str
    auto_publish: bool


@dataclass(frozen=True)
class Campaign:
    id: str
    label: str
    source: str
    platforms: tuple[str, ...]
    mode: str
    cpm: float
    fixed_payout: float
    min_views: int
    max_claim_views: int
    payout_methods: tuple[str, ...]
    hashtags: str
    watermark: str
    watermark_image: str
    required_tag: str
    budget_left_pct: float
    max_videos_per_month: int
    active: bool
    verified: bool
    note: str

    def payout(self, views: int) -> float:
        """Nominal rupiah untuk sejumlah views (0 bila belum memenuhi minimum)."""
        if views < self.min_views:
            return 0.0
        if self.mode == "fixed":
            return round(self.fixed_payout, 2)
        capped = views
        if self.max_claim_views:
            capped = min(capped, self.max_claim_views)
        return round((capped / 1000.0) * self.cpm, 2)

    def views_needed(self) -> int:
        return self.min_views

    def max_payout(self) -> float:
        if self.mode == "fixed":
            return round(self.fixed_payout, 2)
        if self.max_claim_views:
            return round((self.max_claim_views / 1000.0) * self.cpm, 2)
        return 0.0

    def usable(self) -> bool:
        """Campaign bisa dipakai sekarang (aktif + masih ada budget)."""
        return self.active and self.budget_left_pct > 0


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    account_id: str
    enabled: bool
    rights_approved: bool
    rights_risk_accepted: bool
    rights_reference: str
    latest: int
    fallback_popular: bool
    campaign: str
    watermark: str
    hashtags: str = ""
    credit: str = ""


@dataclass(frozen=True)
class Settings:
    root: Path
    paths: Paths
    transcription: TranscriptionConfig
    selection: SelectionConfig
    render: RenderConfig
    upload: UploadConfig
    safety: SafetyConfig
    accounts: tuple[Account, ...]
    sources: tuple[Source, ...]
    campaigns: tuple[Campaign, ...] = ()
    focus: FocusConfig = field(default_factory=FocusConfig)

    def enabled_accounts(self) -> tuple[Account, ...]:
        return tuple(a for a in self.accounts if a.enabled)

    def focus_active_sources(self) -> tuple[Source, ...]:
        """Sumber aktif yang lolos kunci niche (kosong = semua sumber aktif)."""
        sources = self.active_sources()
        if not self.focus.sources:
            return sources
        return tuple(s for s in sources if s.id in self.focus.sources)

    def campaign(self, campaign_id: str) -> Campaign | None:
        for item in self.campaigns:
            if item.id == campaign_id:
                return item
        return None

    def campaigns_for_source(self, source_id: str) -> tuple[Campaign, ...]:
        return tuple(c for c in self.campaigns if c.source == source_id)

    def source_by_key(self, key: str) -> Source | None:
        """Cocokkan prefix nama file ke source config.

        File sumber sering bernama `windah3-xxxx.mp4` padahal id source di
        config hanya `windah`; pencocokan persis membuat hashtag/credit/kampanye
        sumber tidak ketemu dan jatuh ke metadata global channel lain.
        """
        for source in self.sources:
            if source.id == key or key.startswith(source.id):
                return source
        return None

    def usable_campaigns(self, source_id: str | None = None) -> tuple[Campaign, ...]:
        items = self.campaigns_for_source(source_id) if source_id else self.campaigns
        return tuple(c for c in items if c.usable())

    def best_campaign(self, source_id: str | None = None) -> Campaign | None:
        """Campaign aktif dengan payout maksimum per video."""
        pool = self.usable_campaigns(source_id)
        if not pool:
            return None
        return max(pool, key=lambda c: (c.max_payout(), c.budget_left_pct))

    def campaign_for_media(self, media_path: Path) -> Campaign | None:
        """Campaign terpakai (aktif + ada budget) untuk sumber, prefix nama file."""
        key = media_path.name.split("-", 1)[0]
        source = self.source_by_key(key)
        if source is not None and source.campaign:
            pinned = self.campaign(source.campaign)
            if pinned is not None and pinned.usable():
                return pinned
        return self.best_campaign(source.id if source is not None else key)

    def active_sources(self) -> tuple[Source, ...]:
        return tuple(
            s
            for s in self.sources
            if s.enabled and (s.rights_approved or s.rights_risk_accepted)
        )

    def validate_for_run(self) -> None:
        if self.safety.require_rights_approved:
            if self.safety.rights_status not in {"approved", "risk_accepted"}:
                raise ConfigError(
                    "rights.status harus 'approved' atau 'risk_accepted' "
                    "sebelum memproses video"
                )
            if not self.safety.rights_reference.strip():
                raise ConfigError("rights.reference wajib diisi")
        if not self.enabled_accounts():
            raise ConfigError("tidak ada akun enabled di config/accounts.yaml")
        if not any(a.rights_approved for a in self.enabled_accounts()):
            raise ConfigError("akun enabled belum rights_approved")
        by_id = {a.id: a for a in self.accounts}
        for source in self.active_sources():
            account = by_id[source.account_id]
            if not account.enabled or not account.rights_approved:
                raise ConfigError(
                    f"source {source.id}: akun {account.id} belum enabled/rights_approved"
                )


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} harus berupa objek")
    return value


def _str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} harus string tidak kosong")
    return value


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} harus string atau null")
    return value


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f"{key} harus string")
    return value.strip()


def _slots(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(f"{key} harus list jam HH:MM")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(f"{key} hanya berisi string HH:MM")
        try:
            datetime.strptime(item, "%H:%M")
        except ValueError as exc:
            raise ConfigError(f"{key}: {item} bukan HH:MM") from exc
        result.append(item)
    return tuple(sorted(result))


def _slots_by_day(data: dict[str, Any], key: str) -> dict[str, tuple[str, ...]]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} harus objek hari -> list jam")
    allowed = {
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    }
    result: dict[str, tuple[str, ...]] = {}
    for day, hours in value.items():
        if day not in allowed:
            raise ConfigError(f"{key}: hari tidak valid '{day}'")
        if not isinstance(hours, list):
            raise ConfigError(f"{key}.{day} harus list jam HH:MM")
        result[day] = _slots({key: hours}, key)
    return result


def _int(data: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} harus integer")
    if not low <= value <= high:
        raise ConfigError(f"{key} harus di antara {low} dan {high}")
    return value


def _float(
    data: dict[str, Any], key: str, default: float, low: float, high: float
) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} harus angka")
    value = float(value)
    if not low <= value <= high:
        raise ConfigError(f"{key} harus di antara {low} dan {high}")
    return value


def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} harus boolean")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"file tidak ditemukan: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML tidak valid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"isi YAML harus objek: {path}")
    return data


def _path(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p).resolve()


def load_accounts(root: Path) -> tuple[Account, ...]:
    data = _load_yaml(root / "config" / "accounts.yaml")
    raw = data.get("accounts")
    if not isinstance(raw, list) or not raw:
        raise ConfigError("accounts harus list tidak kosong")
    accounts: list[Account] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"accounts[{i}] harus objek")
        platforms = item.get("platforms", {})
        if not isinstance(platforms, dict):
            raise ConfigError(f"accounts[{i}].platforms harus objek")
        youtube = platforms.get("youtube", {})
        tiktok = platforms.get("tiktok", {})
        if not isinstance(youtube, dict) or not isinstance(tiktok, dict):
            raise ConfigError(f"accounts[{i}].platforms.* harus objek")
        youtube_privacy = _str(youtube, "privacy", "private")
        tiktok_privacy = _str(tiktok, "privacy", "SELF_ONLY")
        if youtube_privacy not in {"private", "unlisted", "public"}:
            raise ConfigError(
                "platforms.youtube.privacy harus private, unlisted, atau public"
            )
        if tiktok_privacy not in {
            "SELF_ONLY",
            "PUBLIC_TO_EVERYONE",
            "MUTUAL_FOLLOW_FRIENDS",
            "FOLLOWER_OF_CREATOR",
        }:
            raise ConfigError("platforms.tiktok.privacy tidak valid")
        accounts.append(
            Account(
                id=_str(item, "id", f"akun-{i + 1}"),
                display_name=_str(item, "display_name", f"Akun {i + 1}"),
                niche=_str(item, "niche", "umum"),
                enabled=_bool(item, "enabled", True),
                rights_approved=_bool(item, "rights_approved", False),
                approval_required=_bool(item, "approval_required", True),
                youtube_enabled=_bool(youtube, "enabled", False),
                youtube_privacy=youtube_privacy,
                tiktok_enabled=_bool(tiktok, "enabled", False),
                tiktok_privacy=tiktok_privacy,
                auto_publish=_bool(item, "auto_publish", False),
            )
        )
    ids = [a.id for a in accounts]
    if len(ids) != len(set(ids)):
        raise ConfigError("id akun duplikat")
    return tuple(accounts)


def load_sources(
    root: Path, account_ids: set[str]
) -> tuple[Source, ...]:
    path = root / "config" / "sources.yaml"
    if not path.exists():
        return ()
    data = _load_yaml(path)
    raw = data.get("sources", [])
    if not isinstance(raw, list):
        raise ConfigError("sources harus list")
    sources: list[Source] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"sources[{i}] harus objek")
        source_id = _str(item, "id", f"sumber-{i + 1}")
        if not all(ch.isalnum() or ch in "-_" for ch in source_id):
            raise ConfigError(f"source {source_id}: id hanya huruf/angka/-/_")
        url = _str(item, "url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
        }:
            raise ConfigError(f"source {source_id}: url harus https YouTube")
        account_id = _str(item, "account", "")
        if account_id not in account_ids:
            raise ConfigError(f"source {source_id}: akun {account_id} tidak ada")
        rights_approved = _bool(item, "rights_approved", False)
        rights_risk_accepted = _bool(item, "rights_risk_accepted", False)
        rights_reference = item.get("rights_reference", "")
        if not isinstance(rights_reference, str):
            raise ConfigError(f"source {source_id}: rights_reference harus string")
        if (rights_approved or rights_risk_accepted) and not rights_reference.strip():
            raise ConfigError(f"source {source_id}: rights_reference wajib diisi")
        sources.append(
            Source(
                id=source_id,
                url=url,
                account_id=account_id,
                enabled=_bool(item, "enabled", True),
                rights_approved=rights_approved,
                rights_risk_accepted=rights_risk_accepted,
                rights_reference=rights_reference,
                latest=_int(item, "latest", 3, 1, 10),
                fallback_popular=_bool(item, "fallback_popular", False),
                campaign=_opt_str(item, "campaign") or "",
                watermark=_opt_str(item, "watermark") or "",
                hashtags=_opt_str(item, "hashtags") or "",
                credit=_opt_str(item, "credit") or "",
            )
        )
    ids = [s.id for s in sources]
    if len(ids) != len(set(ids)):
        raise ConfigError("id source duplikat")
    return tuple(sources)


def load_campaigns(root: Path) -> tuple[Campaign, ...]:
    path = root / "config" / "campaigns.yaml"
    if not path.exists():
        return ()
    data = _load_yaml(path)
    raw = data.get("campaigns", [])
    if not isinstance(raw, list):
        raise ConfigError("campaigns harus list")
    out: list[Campaign] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"campaigns[{i}] harus objek")
        cid = _str(item, "id", f"campaign-{i + 1}")
        platforms = item.get("platforms") or []
        methods = item.get("payout_methods") or []
        if not isinstance(platforms, list) or not isinstance(methods, list):
            raise ConfigError(f"campaign {cid}: platforms/payout_methods harus list")
        out.append(
            Campaign(
                id=cid,
                label=_str(item, "label", cid),
                source=_str(item, "source", ""),
                platforms=tuple(str(p) for p in platforms),
                mode=_str(item, "mode", "per_video"),
                cpm=_float(item, "cpm", 0.0, 0.0, 1_000_000.0),
                fixed_payout=_float(item, "fixed_payout", 0.0, 0.0, 1_000_000_000.0),
                min_views=_int(item, "min_views", 0, 0, 1_000_000_000),
                max_claim_views=_int(item, "max_claim_views", 0, 0, 1_000_000_000),
                payout_methods=tuple(str(m) for m in methods),
                hashtags=_opt_str(item, "hashtags") or "",
                watermark=_opt_str(item, "watermark") or "",
                watermark_image=_opt_str(item, "watermark_image") or "",
                required_tag=_opt_str(item, "required_tag") or "",
                budget_left_pct=_float(item, "budget_left_pct", 0.0, 0.0, 100.0),
                max_videos_per_month=_int(
                    item, "max_videos_per_month", 0, 0, 1000
                ),
                active=_bool(item, "active", True),
                verified=_bool(item, "verified", False),
                note=_opt_str(item, "note") or "",
            )
        )
    ids = [c.id for c in out]
    if len(ids) != len(set(ids)):
        raise ConfigError("id campaign duplikat")
    return tuple(out)


def load_settings(root: Path | str = ".") -> Settings:
    root = Path(root).resolve()
    data = _load_yaml(root / "config" / "settings.yaml")
    paths_raw = _section(data, "paths")
    paths = Paths(
        incoming=_path(root, _str(paths_raw, "incoming", "storage/incoming")),
        work=_path(root, _str(paths_raw, "work", "storage/work")),
        review=_path(root, _str(paths_raw, "review", "storage/review")),
        published=_path(root, _str(paths_raw, "published", "storage/published")),
        database=_path(root, _str(paths_raw, "database", "data/autoclip.db")),
        logs=_path(root, _str(paths_raw, "logs", "logs")),
    )

    tx_raw = _section(data, "transcription")
    transcription = TranscriptionConfig(
        model=_str(tx_raw, "model", "small"),
        compute_type=_str(tx_raw, "compute_type", "int8"),
        language=_opt_str(tx_raw, "language"),
        vad=_bool(tx_raw, "vad", True),
    )

    sel_raw = _section(data, "selection")
    selection = SelectionConfig(
        clips_per_video=_int(sel_raw, "clips_per_video", 3, 1, 10),
        min_duration_seconds=_float(sel_raw, "min_duration_seconds", 20, 3, 600),
        max_duration_seconds=_float(sel_raw, "max_duration_seconds", 60, 5, 600),
        min_score=_float(sel_raw, "min_score", 60, 0, 100),
        chunk_seconds=_float(sel_raw, "chunk_seconds", 480, 60, 3600),
        provider=_str(sel_raw, "provider", "auto"),
        gemini_model=_str(sel_raw, "gemini_model", "gemini-2.0-flash"),
        ollama_model=_str(sel_raw, "ollama_model", "qwen2.5:3b"),
        ollama_url=_str(sel_raw, "ollama_url", "http://127.0.0.1:11434"),
    )
    if selection.min_duration_seconds >= selection.max_duration_seconds:
        raise ConfigError("min_duration_seconds harus lebih kecil dari max_duration_seconds")
    if selection.provider not in {"auto", "gemini", "ollama", "heuristic"}:
        raise ConfigError("selection.provider harus auto, gemini, ollama, atau heuristic")
    if selection.chunk_seconds < selection.max_duration_seconds:
        raise ConfigError("chunk_seconds harus >= max_duration_seconds")

    rnd_raw = _section(data, "render")
    render = RenderConfig(
        width=_int(rnd_raw, "width", 1080, 240, 4096),
        height=_int(rnd_raw, "height", 1920, 240, 4096),
        crf=_int(rnd_raw, "crf", 21, 0, 51),
        preset=_str(rnd_raw, "preset", "veryfast"),
        encoder=_str(rnd_raw, "encoder", "auto"),
        face_crop=_bool(rnd_raw, "face_crop", True),
        face_sample_fps=_float(rnd_raw, "face_sample_fps", 1.0, 0.1, 10.0),
        subtitles=_bool(rnd_raw, "subtitles", True),
        subtitle_max_chars=_int(rnd_raw, "subtitle_max_chars", 32, 10, 120),
        subtitle_style=_str(
            rnd_raw,
            "subtitle_style",
            "FontName=Arial,FontSize=8,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=0.7,Shadow=0,"
            "Alignment=2,MarginV=45",
        ),
        subtitle_language=_opt_str(rnd_raw, "subtitle_language") or "",
        hook_overlay=_bool(rnd_raw, "hook_overlay", True),
        hook_seconds=_float(rnd_raw, "hook_seconds", 4.0, 0.0, 10.0),
        emoji_hook=_bool(rnd_raw, "emoji_hook", True),
        zoom_punch=_bool(rnd_raw, "zoom_punch", True),
        loudnorm=_bool(rnd_raw, "loudnorm", True),
    )
    if render.width % 2 or render.height % 2:
        raise ConfigError("render width/height harus genap")
    if render.encoder not in {"auto", "qsv", "libx264"}:
        raise ConfigError("render.encoder harus auto, qsv, atau libx264")

    upload_raw = _section(data, "upload")
    upload = UploadConfig(
        hashtags=_text(upload_raw, "hashtags"),
        credit=_text(upload_raw, "credit"),
        thumbnail=_bool(upload_raw, "thumbnail", True),
        schedule_start=_text(upload_raw, "schedule_start"),
        schedule_interval_hours=_float(
            upload_raw, "schedule_interval_hours", 6.0, 0.25, 168.0
        ),
        slots=_slots(upload_raw, "slots"),
        utc_offset_hours=_float(upload_raw, "utc_offset_hours", 7.0, -12.0, 14.0),
        auto_publish=_bool(upload_raw, "auto_publish", False),
        slots_by_day=_slots_by_day(upload_raw, "slots_by_day"),
        category_id=_str(upload_raw, "category_id", "22"),
    )

    rights_raw = _section(data, "rights")
    safety_raw = _section(data, "safety")
    safety = SafetyConfig(
        max_sources_per_run=_int(safety_raw, "max_sources_per_run", 1, 1, 20),
        max_clips_per_source=_int(safety_raw, "max_clips_per_source", 3, 1, 20),
        require_rights_approved=_bool(safety_raw, "require_rights_approved", True),
        min_source_age_seconds=_int(safety_raw, "min_source_age_seconds", 30, 0, 86400),
        retain_work_days=_int(safety_raw, "retain_work_days", 14, 0, 3650),
        rights_status=_str(rights_raw, "status", "pending"),
        rights_reference=_str(rights_raw, "reference", ""),
    )

    accounts = load_accounts(root)
    campaigns = load_campaigns(root)
    focus_raw = _section(data, "focus")
    focus = FocusConfig(
        sources=tuple(str(x).strip() for x in (focus_raw.get("sources") or []) if x),
        keywords=tuple(str(x).strip() for x in (focus_raw.get("keywords") or []) if x),
        keyword_bonus=_float(focus_raw, "keyword_bonus", 0.0, 0.0, 50.0),
    )
    settings = Settings(
        root=root,
        paths=paths,
        transcription=transcription,
        selection=selection,
        render=render,
        upload=upload,
        safety=safety,
        accounts=accounts,
        sources=load_sources(root, {a.id for a in accounts}),
        campaigns=campaigns,
        focus=focus,
    )
    for directory in (
        paths.incoming,
        paths.work,
        paths.review,
        paths.published,
        paths.logs,
        paths.database.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return settings




