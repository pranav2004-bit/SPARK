# Single source of truth for upload validation — shared by the Company-upload
# flow (resources/views.py UploadPresignedUrlView etc.) and the Module-upload
# flow (AdminModuleUploadPresignedUrlView etc.), which both reuse the same
# PresignedUploadRequestSerializer / ConfirmUploadSerializer.
#
# Mirrors frontend/src/lib/constants.ts — keep both in sync when changing.
#
# Format choices are deliberately narrower than "every format users might
# have": .svg is excluded (inline <script>/event-handler payloads make it a
# stored-XSS vector when served back via a raw link), .wav is excluded
# (uncompressed audio blows through any single audio size cap in minutes),
# and .avi/.mov/.mkv are excluded for video (none of them play in an HTML5
# <video>/browser tab the way this app serves files — only .mp4/.webm do).

MAX_FILE_SIZES = {
    "pdf": 25 * 1024 * 1024,     # 25 MB
    "audio": 100 * 1024 * 1024,  # 100 MB
    "video": 500 * 1024 * 1024,  # 500 MB — matches the MinIO/R2 proxy's own cap
    "image": 5 * 1024 * 1024,    # 5 MB
}

ALLOWED_EXTENSIONS = {
    "pdf": [".pdf"],
    "audio": [".mp3", ".aac", ".m4a", ".ogg"],
    "video": [".mp4", ".webm"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
}

ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "audio": [
        "audio/mpeg", "audio/mp3", "audio/aac",
        "audio/x-m4a", "audio/mp4", "audio/ogg", "audio/vorbis",
    ],
    "video": ["video/mp4", "video/webm"],
    "image": ["image/jpeg", "image/png", "image/gif", "image/webp"],
}

# (byte_offset, expected_prefix) pairs checked against the first bytes of the
# object actually sitting in storage. Any single match for the upload_type
# passes. This catches a renamed/mislabelled file — extension and
# Content-Type are both attacker-controlled at presign time; these bytes
# are not (they're read back from the object the browser actually wrote).
MAGIC_BYTES = {
    "pdf": [(0, b"%PDF")],
    "image": [
        (0, b"\xff\xd8\xff"),          # JPEG
        (0, b"\x89PNG\r\n\x1a\n"),     # PNG
        (0, b"GIF87a"),                # GIF
        (0, b"GIF89a"),                # GIF
        (8, b"WEBP"),                  # WEBP (RIFF....WEBP)
    ],
    "audio": [
        (0, b"ID3"),        # MP3 with ID3 tag
        (0, b"\xff\xfb"),   # MP3 (MPEG-1 Layer 3)
        (0, b"\xff\xf3"),
        (0, b"\xff\xf2"),
        (4, b"ftyp"),       # M4A/AAC (MP4 container)
        (0, b"OggS"),       # OGG
    ],
    "video": [
        (4, b"ftyp"),               # MP4
        (0, b"\x1a\x45\xdf\xa3"),   # WEBM/MKV (EBML header)
    ],
}

# Total confirmed bytes allowed per section — protects against unbounded
# storage growth even when every individual upload is within its own cap.
MAX_BYTES_PER_SECTION = 2 * 1024 * 1024 * 1024  # 2 GB

# How many leading bytes to read back from storage for the magic-byte check.
MAGIC_BYTES_READ_LEN = 16
