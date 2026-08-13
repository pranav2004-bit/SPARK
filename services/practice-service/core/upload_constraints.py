# Single source of truth for question/explanation image upload validation.
# Mirrors services/resource-service/core/upload_constraints.py — keep both in
# sync in spirit (practice-service only ever handles images, so this is a
# subset). .svg is deliberately excluded: it can carry inline
# <script>/event-handler payloads, making it a stored-XSS vector when the
# CDN URL is opened directly or rendered as an <img src>.

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB — question/explanation images only

ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"]

ALLOWED_IMAGE_MIME = (
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
)

# (byte_offset, expected_prefix) — any single match passes. Read back from
# the object actually sitting in storage, not the client-declared type.
MAGIC_BYTES = [
    (0, b"\xff\xd8\xff"),          # JPEG
    (0, b"\x89PNG\r\n\x1a\n"),     # PNG
    (0, b"GIF87a"),                # GIF
    (0, b"GIF89a"),                # GIF
    (8, b"WEBP"),                  # WEBP (RIFF....WEBP)
    (4, b"ftypavif"),              # AVIF
]

MAGIC_BYTES_READ_LEN = 16

# Total confirmed image bytes allowed per section (across every question's
# body + explanation image) — protects against unbounded storage growth
# even though each individual image is already capped at MAX_IMAGE_SIZE.
MAX_BYTES_PER_SECTION = 200 * 1024 * 1024  # 200 MB
