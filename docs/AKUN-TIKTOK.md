# Akun TikTok @saint.gabrieldesign

Diubah 2026-11-02 menjadi tema clipper (pivot penuh, permintaan pemilik akun).

| Field | Nilai |
|---|---|
| Username | `saint.gabrieldesign` (tidak diubah) |
| Nama tampilan | **Windah Clips ID** (dikonfirmasi via oEmbed) |
| Foto profil | `assets/pfp-windah-clips.png` — W besar kuning, "CLIPS", label "WINDAH" |
| Bio | `Klip Windah tiap hari \| MotionKlip \| Desain: lynk.id/saintgabriel` |
| Link jualan desain | tetap `lynk.id/saintgabriel` |

## Catatan operasional

- **Nama terkunci 1× per 7 hari** — jangan diubah lagi sebelum 2026-11-09.
- Foto profil & bio bisa diubah kapan saja.
- Username sengaja tidak diganti: semua link video/TikTok Studio sudah menunjuk
  `@saint.gabrieldesign`, dan mengganti username memutus link tersebut.
- Setelah menekan Save, TikTok memunculkan dialog konfirmasi
  **"Set nickname? You can only change your nickname once every 7 days"** —
  wajib klik **Confirm**, kalau tidak nama tidak tersimpan (gagal diam-diam).
- Saat mengganti username, TikTok sempat menolak semua kandidat dengan
  "This username isn't available" termasuk nama acak → rate limit sementara,
  bukan berarti semua nama terpakai.

## Regenerate foto profil

```powershell
cd D:\clipper
# filter script harus ditulis dengan newline Unix (CRLF merusak parser ffmpeg)
$lines = @(
"color=c=0x111111:s=1080x1080:d=1[base];",
"[base]drawbox=x=60:y=60:w=iw-120:h=ih-120:color=0xFFD400@1:t=14[b];",
"[b]drawtext=fontfile='C\:/Windows/Fonts/impact.ttf':text='W':fontsize=520:fontcolor=0xFFD400:x=(w-text_w)/2:y=170[c];",
"[c]drawtext=fontfile='C\:/Windows/Fonts/impact.ttf':text='CLIPS':fontsize=170:fontcolor=0xFFFFFF:x=(w-text_w)/2:y=690[d];",
"[d]drawtext=fontfile='C\:/Windows/Fonts/arialbd.ttf':text='WINDAH':fontsize=70:fontcolor=0xFFD400:x=(w-text_w)/2:y=910[out]"
)
[System.IO.File]::WriteAllText("storage\work\pfp.txt", ($lines -join "`n"), [System.Text.UTF8Encoding]::new($false))
ffmpeg -y -hide_banner -loglevel error -filter_complex_script storage\work\pfp.txt -map "[out]" -frames:v 1 assets/pfp-windah-clips.png
```
