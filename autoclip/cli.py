from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sqlite3
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__, tiktok, youtube
from .config import ConfigError, load_settings
from .db import (
    DbError,
    connect,
    find_source,
    future_scheduled_slots,
    get_clip,
    get_publication,
    init_db,
    list_clips,
    list_sources,
)
from .pipeline import (
    AlreadyRunning,
    RunLock,
    account_for_source,
    campaign_for_media,
    longcut_source,
    process_source,
    resqueeze_source,
    run,
)
from .publish import (
    PublishError,
    publish_approved,
    publish_clip,
    release_clip,
    schedule_slot,
)
from .render import make_thumbnail
from .review import ReviewError, approve, reject, write_review_html
from .scan import scan
from .sources import sync_sources
from .youtube import AuthError

ROOT = Path(__file__).resolve().parents[1]


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        log_dir / "autoclip.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoclip", description="Auto-clipper lokal")
    parser.add_argument("--root", default=str(ROOT), help="folder proyek")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="scan + proses sumber baru")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--account", default=None, help="hanya akun/channel ini")

    sub.add_parser("scan", help="pindai folder incoming")
    sync_parser = sub.add_parser("sync", help="unduh upload baru dari channel sumber")
    sync_parser.add_argument("--source", default=None, help="id sumber saja")
    sync_parser.add_argument("--account", default=None, help="hanya sumber akun ini")

    auth_parser = sub.add_parser("auth", help="hubungkan akun platform")
    auth_parser.add_argument("platform", choices=["youtube", "tiktok"])
    auth_parser.add_argument("--account", default="utama")

    publish_parser = sub.add_parser("publish", help="unggah klip approved")
    publish_parser.add_argument("clip_id", nargs="?", type=int)
    publish_parser.add_argument("--all-approved", action="store_true")
    publish_parser.add_argument("--platform", default="youtube")
    publish_parser.add_argument("--account", default=None)
    publish_parser.add_argument(
        "--schedule", action="store_true", help="jadwalkan rilis sesuai config upload"
    )

    release_parser = sub.add_parser(
        "release", help="isi deskripsi+hashtag lalu jadikan public"
    )
    release_parser.add_argument("clip_id", nargs="?", type=int)
    release_parser.add_argument("--all-published", action="store_true")
    release_parser.add_argument("--account", default=None)
    release_parser.add_argument("--privacy", default="public")

    thumb_parser = sub.add_parser("thumbnail", help="pasang thumbnail klip terunggah")
    thumb_parser.add_argument("clip_id", type=int)
    thumb_parser.add_argument("--account", default=None)

    process_parser = sub.add_parser("process", help="proses satu sumber")
    process_parser.add_argument("source", help="path atau id sumber")
    process_parser.add_argument("--force", action="store_true")

    resqueeze_parser = sub.add_parser(
        "resqueeze", help="cari klip tambahan dari sumber yang sudah diproses"
    )
    resqueeze_parser.add_argument("source", help="id sumber")
    resqueeze_parser.add_argument(
        "--clips", type=int, default=5, help="target klip tambahan (default 5)"
    )
    resqueeze_parser.add_argument(
        "--min-score", type=float, default=None, help="turunan ambang skor"
    )

    longcut_parser = sub.add_parser(
        "longcut", help="render satu video panjang 16:9 dari sumber"
    )
    longcut_parser.add_argument("source", help="id sumber")
    longcut_parser.add_argument(
        "--minutes", type=int, default=10, help="durasi target (default 10)"
    )
    longcut_parser.add_argument("--start", type=float, default=None)

    list_parser = sub.add_parser("list", help="daftar klip")
    list_parser.add_argument("--status", default=None)
    list_parser.add_argument("--sources", action="store_true")
    list_parser.add_argument("--account", default=None)

    approve_parser = sub.add_parser("approve", help="setujui klip")
    approve_parser.add_argument("clip_id", type=int)
    approve_parser.add_argument("--reviewer", default=None)
    approve_parser.add_argument("--publish", action="store_true")

    reject_parser = sub.add_parser("reject", help="tolak klip")
    reject_parser.add_argument("clip_id", type=int)
    reject_parser.add_argument("--reviewer", default=None)

    review_parser = sub.add_parser("review", help="tulis ulang halaman review")
    review_parser.add_argument("--account", default=None)

    campaign_parser = sub.add_parser("campaign", help="campaign MotionKlip")
    campaign_sub = campaign_parser.add_subparsers(dest="campaign_command")
    campaign_sub.add_parser("list", help="daftar campaign")
    claim_parser = campaign_sub.add_parser("claim", help="catat klaim campaign")
    claim_parser.add_argument("clip_id", type=int)
    claim_parser.add_argument("--campaign", required=True)
    claim_parser.add_argument("--url", required=True)
    claim_parser.add_argument("--views", type=int, required=True)
    claim_parser.add_argument("--platform", default="tiktok")
    claim_parser.add_argument("--note", default=None)
    caption_parser = campaign_sub.add_parser("caption", help="cetak caption siap-tempel")
    caption_parser.add_argument("clip_id", type=int)
    caption_parser.add_argument("--campaign", default=None)
    render_parser = campaign_sub.add_parser(
        "render", help="render ulang klip dengan watermark campaign"
    )
    render_parser.add_argument("clip_id", type=int)
    render_parser.add_argument("--campaign", default=None)
    status_parser = campaign_sub.add_parser("status", help="status klaim")
    status_parser.add_argument("--status", default=None)
    paid_parser = campaign_sub.add_parser("paid", help="tandai klaim sudah dibayar")
    paid_parser.add_argument("claim_id", type=int)

    sub.add_parser("doctor", help="periksa dependensi dan konfigurasi")
    return parser


def _campaign_command(settings, conn, args) -> int:
    from .db import claim_totals, list_claims, record_claim, set_claim_status

    action = args.campaign_command or "list"
    if action == "list":
        if not settings.campaigns:
            print("tidak ada campaign di config/campaigns.yaml")
            return 0
        best = settings.best_campaign("windah")
        for c in settings.campaigns:
            usable = c.usable()
            state = "SIAP" if usable else "MATI"
            print(
                f"{c.id:<28} {state:<5} budget {c.budget_left_pct:>6.2f}%  "
                f"min {c.min_views:>7,} views  max Rp{c.max_payout():>10,.0f}"
            )
            print(f"{'':28} {c.label} | {c.mode} | {', '.join(c.platforms) or '-'}")
            if c.note:
                print(f"{'':28} {c.note[:100]}")
        if best is not None:
            print(f"\nREKOMENDASI: {best.id} (budget {best.budget_left_pct:.2f}%)")
        return 0

    if action == "caption":
        from .db import get_clip

        clip = get_clip(conn, args.clip_id)
        if clip is None:
            print(f"error: clip {args.clip_id} tidak ada", file=sys.stderr)
            return 2
        campaign = (
            settings.campaign(args.campaign)
            if args.campaign
            else settings.best_campaign("windah")
        )
        if campaign is None:
            print("error: tidak ada campaign aktif", file=sys.stderr)
            return 2
        print(f"{clip['title']}\n\n{campaign.hashtags}")
        return 0

    if action == "render":
        from pathlib import Path

        from .db import get_clip, get_source
        from .media import probe
        from .render import render_clip
        from .transcribe import ensure_transcript

        clip = get_clip(conn, args.clip_id)
        if clip is None:
            print(f"error: clip {args.clip_id} tidak ada", file=sys.stderr)
            return 2
        source = get_source(conn, int(clip["source_id"]))
        media = Path(str(source["path"]))
        if not media.exists():
            print(f"error: file sumber hilang: {media}", file=sys.stderr)
            return 2
        campaign = (
            settings.campaign(args.campaign)
            if args.campaign
            else campaign_for_media(settings, media)
        )
        if campaign is None:
            print("error: tidak ada campaign aktif", file=sys.stderr)
            return 2
        image = settings.root / campaign.watermark_image
        transcript = ensure_transcript(settings, source)
        rendered = render_clip(
            media,
            probe(media),
            float(clip["start"]),
            float(clip["end"]),
            str(clip["title"]),
            settings,
            transcript,
            settings.paths.review / "clips",
            int(clip["source_id"]),
            watermark=campaign.watermark,
            watermark_image=image if image.exists() else None,
        )
        conn.execute(
            "UPDATE clips SET file_path = ?, file_hash = ?, status = 'approved' "
            "WHERE id = ?",
            (str(rendered.path), rendered.sha256, int(clip["id"])),
        )
        conn.commit()
        print(f"clip {clip['id']} dirender ulang: {rendered.path}")
        print(f"campaign: {campaign.id}")
        return 0

    if action == "claim":
        campaign = settings.campaign(args.campaign)
        if campaign is None:
            print(f"error: campaign {args.campaign} tidak ada", file=sys.stderr)
            return 2
        payout = campaign.payout(args.views)
        claim_id = record_claim(
            conn,
            args.clip_id,
            campaign.id,
            args.platform,
            args.url,
            args.views,
            payout,
            args.note,
        )
        eligible = "ELIGIBLE" if payout > 0 else f"BELUM (min {campaign.min_views:,})"
        print(
            f"claim #{claim_id} klip {args.clip_id} {campaign.id}: "
            f"{args.views:,} views -> Rp{payout:,.0f} [{eligible}]"
        )
        return 0

    if action == "status":
        rows = list_claims(conn, args.status)
        if not rows:
            print("tidak ada klaim")
            return 0
        print(f"{'ID':>4}  {'KLIP':>5}  {'CAMPAIGN':<26} {'VIEWS':>10} {'PAYOUT':>10}  STATUS")
        for row in rows:
            print(
                f"{int(row['id']):>4}  {int(row['clip_id']):>5}  "
                f"{row['campaign_id']:<26} {int(row['views']):>10,} "
                f"{float(row['payout']):>10,.0f}  {row['status']}"
            )
        totals = claim_totals(conn)
        print(
            f"\ntotal: {int(totals['count'])} klaim, "
            f"{int(totals['views']):,} views, "
            f"Rp{totals['payout']:,.0f} (dibayar Rp{totals['paid']:,.0f})"
        )
        return 0

    if action == "paid":
        set_claim_status(conn, args.claim_id, "paid")
        print(f"claim {args.claim_id} ditandai dibayar")
        return 0

    print(f"error: aksi campaign tidak dikenal: {action}", file=sys.stderr)
    return 2


def _print_sources(rows) -> None:
    if not rows:
        print("tidak ada sumber")
        return
    print(f"{'ID':>4}  {'STATUS':<10} {'DURASI':>8}  PATH")
    for row in rows:
        print(
            f"{int(row['id']):>4}  {row['status']:<10} "
            f"{float(row['duration']):>7.1f}s  {row['path']}"
        )


def _print_clips(rows) -> None:
    if not rows:
        print("tidak ada klip")
        return
    print(f"{'ID':>4}  {'STATUS':<10} {'SCORE':>6}  {'MULAI':>7}  {'AKHIR':>7}  JUDUL")
    for row in rows:
        print(
            f"{int(row['id']):>4}  {row['status']:<10} "
            f"{float(row['final_score']):>6.1f}  {float(row['start']):>7.1f}  "
            f"{float(row['end']):>7.1f}  {row['title']}"
        )


def _doctor(settings) -> int:
    checks: list[tuple[bool, str]] = []
    checks.append((shutil.which("ffmpeg") is not None, "ffmpeg di PATH"))
    checks.append((shutil.which("ffprobe") is not None, "ffprobe di PATH"))
    for module in ("faster_whisper", "cv2", "httpx", "yaml"):
        checks.append(
            (importlib.util.find_spec(module) is not None, f"modul {module}")
        )
    try:
        settings.validate_for_run()
        checks.append((True, "konfigurasi + rights + akun"))
    except ConfigError as exc:
        checks.append((False, f"konfigurasi: {exc}"))
    if settings.active_sources():
        checks.append((shutil.which("yt-dlp") is not None, "yt-dlp di PATH"))
        risky = [
            s.id
            for s in settings.active_sources()
            if not s.rights_approved and s.rights_risk_accepted
        ]
        if risky:
            checks.append(
                (
                    True,
                    f"izin belum terverifikasi: {', '.join(risky)} "
                    "(risiko pemilik akun)",
                )
            )
    for account in settings.enabled_accounts():
        if not account.youtube_enabled:
            continue
        checks.append(
            (
                youtube.client_secret_path(settings).exists(),
                f"client secret YouTube ({youtube.client_secret_path(settings)})",
            )
        )
        checks.append(
            (
                youtube.token_path(settings, account.id).exists(),
                f"token YouTube akun {account.id}",
            )
        )
    try:
        conn = connect(settings.paths.database)
        init_db(conn)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks.append((True, "database"))
    except (sqlite3.Error, OSError) as exc:
        checks.append((False, f"database: {exc}"))
    for path in (
        settings.paths.incoming,
        settings.paths.review / "clips",
        settings.paths.work,
        settings.paths.logs,
    ):
        checks.append((path.exists(), f"folder {path}"))
    for ok, label in checks:
        print(f"[{'OK' if ok else '!!'}] {label}")
    return 0 if all(ok for ok, _ in checks) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.paths.logs)

    if args.command == "doctor":
        return _doctor(settings)

    if args.command == "auth":
        if args.platform == "tiktok":
            try:
                path = tiktok.authorize(settings)
            except (tiktok.TikTokError, OSError) as exc:
                print(f"auth error: {exc}", file=sys.stderr)
                return 2
            print(f"sesi TikTok tersimpan: {path}")
            return 0
        try:
            path = youtube.authorize(
                settings, args.account, url_callback=lambda url: print(url)
            )
        except AuthError as exc:
            print(f"auth error: {exc}", file=sys.stderr)
            return 2
        print(f"token tersimpan: {path}")
        return 0

    if args.command == "run":
        try:
            summary = run(settings, limit=args.limit, account_id=args.account)
        except (ConfigError, AlreadyRunning, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(
            f"unduh={summary['downloaded']} scan={summary['scanned']} "
            f"diproses={summary['processed']} klip={summary['clips']} "
            f"upload={summary['published']} error={len(summary['errors'])}"
        )
        if summary["errors"]:
            for message in summary["errors"]:
                print(f"  - {message}", file=sys.stderr)
            return 1
        return 0

    conn = connect(settings.paths.database)
    init_db(conn)
    try:
        if args.command == "scan":
            created = scan(settings, conn)
            print(f"{len(created)} sumber baru: {created}")
            return 0

        if args.command == "sync":
            result = sync_sources(settings, only=args.source, account=args.account)
            print(f"{len(result['downloaded'])} video baru: {result['downloaded']}")
            for message in result["errors"]:
                print(f"  - {message}", file=sys.stderr)
            return 1 if result["errors"] else 0

        if args.command == "process":
            source = find_source(conn, args.source)
            if source is None:
                print(f"sumber tidak ditemukan: {args.source}", file=sys.stderr)
                return 2
            settings.validate_for_run()
            accounts = [a for a in settings.enabled_accounts() if a.rights_approved]
            if not accounts:
                print("tidak ada akun siap", file=sys.stderr)
                return 2
            try:
                with RunLock(settings.paths.database.parent / "run.lock"):
                    account = account_for_source(settings, source)
                    clips = process_source(
                        settings, conn, source, account, force=args.force
                    )
            except AlreadyRunning as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            write_review_html(settings, conn)
            print(f"{len(clips)} klip dibuat: {clips}")
            return 0

        if args.command == "resqueeze":
            source = find_source(conn, args.source)
            if source is None:
                print(f"sumber tidak ditemukan: {args.source}", file=sys.stderr)
                return 2
            try:
                with RunLock(settings.paths.database.parent / "run.lock"):
                    clips = resqueeze_source(
                        settings,
                        conn,
                        int(source["id"]),
                        extra_clips=args.clips,
                        min_score=args.min_score,
                    )
            except (AlreadyRunning, RuntimeError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            write_review_html(settings, conn)
            print(f"{len(clips)} klip tambahan: {clips}")
            return 0

        if args.command == "longcut":
            source = find_source(conn, args.source)
            if source is None:
                print(f"sumber tidak ditemukan: {args.source}", file=sys.stderr)
                return 2
            try:
                with RunLock(settings.paths.database.parent / "run.lock"):
                    clip_id = longcut_source(
                        settings,
                        conn,
                        int(source["id"]),
                        minutes=args.minutes,
                        start=args.start,
                    )
            except (AlreadyRunning, RuntimeError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"longcut clip #{clip_id} siap")
            return 0

        if args.command == "list":
            if args.sources:
                _print_sources(list_sources(conn, args.status))
            else:
                rows = list_clips(conn, args.status)
                if args.account:
                    rows = [r for r in rows if str(r["account_id"]) == args.account]
                _print_clips(rows)
            return 0

        if args.command == "approve":
            approve(conn, args.clip_id, args.reviewer)
            write_review_html(settings, conn)
            print(f"clip {args.clip_id} disetujui")
            if args.publish:
                remote_id = publish_clip(settings, conn, args.clip_id)
                print(f"clip {args.clip_id} terunggah: {remote_id}")
            return 0

        if args.command == "publish":
            if args.all_approved:
                result = publish_approved(
                    settings, conn, only_auto=False, schedule=args.schedule
                )
                for clip_id, remote_id in result["published"]:
                    print(f"clip {clip_id} -> {remote_id}")
                for message in result["errors"]:
                    print(f"  - {message}", file=sys.stderr)
                return 1 if result["errors"] else 0
            if args.clip_id is None:
                print("publish butuh CLIP_ID atau --all-approved", file=sys.stderr)
                return 2
            remote_id = publish_clip(
                settings,
                conn,
                args.clip_id,
                platform=args.platform,
                account_id=args.account,
                # slot yang sudah terpakai harus dilewati, kalau tidak semua klip
                # yang dijadwalkan satu per satu jatuh di jam yang sama.
                publish_at=schedule_slot(
                    settings, 0, future_scheduled_slots(conn, args.platform)
                )
                if args.schedule
                else None,
            )
            print(f"clip {args.clip_id} terunggah: {remote_id}")
            return 0

        if args.command == "release":
            targets: list[int] = []
            if args.all_published:
                for row in list_clips(conn, None):
                    publication = get_publication(
                        conn, int(row["id"]), "youtube", str(row["account_id"])
                    )
                    if publication is not None and publication["status"] == "published":
                        targets.append(int(row["id"]))
            elif args.clip_id is not None:
                targets = [args.clip_id]
            if not targets:
                print("release butuh CLIP_ID atau --all-published", file=sys.stderr)
                return 2
            errors = 0
            for clip_id in targets:
                try:
                    result = release_clip(
                        settings,
                        conn,
                        clip_id,
                        account_id=args.account,
                        privacy=args.privacy,
                    )
                except (PublishError, AuthError, OSError) as exc:
                    errors += 1
                    print(f"  - clip #{clip_id}: {exc}", file=sys.stderr)
                    continue
                print(
                    f"clip {clip_id} -> {result['remote_id']} "
                    f"({result['privacy']}, deskripsi+hashtag diisi)"
                )
            return 1 if errors else 0

        if args.command == "thumbnail":
            clip = get_clip(conn, args.clip_id)
            if clip is None:
                print(f"clip {args.clip_id} tidak ditemukan", file=sys.stderr)
                return 2
            account_id = args.account or str(clip["account_id"])
            publication = get_publication(conn, args.clip_id, "youtube", account_id)
            if publication is None or publication["status"] != "published":
                print(f"clip {args.clip_id} belum terunggah", file=sys.stderr)
                return 2
            video = Path(str(clip["file_path"]))
            image = video.with_suffix(".jpg")
            if not image.exists():
                image = make_thumbnail(video) or image
            youtube.set_thumbnail(
                settings, account_id, str(publication["remote_id"]), image
            )
            print(f"thumbnail clip {args.clip_id} terpasang")
            return 0

        if args.command == "reject":
            reject(conn, args.clip_id, args.reviewer)
            write_review_html(settings, conn)
            print(f"clip {args.clip_id} ditolak")
            return 0

        if args.command == "review":
            path = write_review_html(settings, conn, account_id=args.account)
            print(f"review: {path}")
            return 0

        if args.command == "campaign":
            return _campaign_command(settings, conn, args)
    except (ReviewError, DbError, ConfigError, PublishError, AuthError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
