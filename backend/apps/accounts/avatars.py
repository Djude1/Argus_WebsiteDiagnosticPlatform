"""使用者大頭貼的驗證與重新編碼。

上傳的檔案一律用 Pillow 解碼後重新輸出成 256×256 PNG，只保留像素：
EXIF（含 GPS）、ICC、內嵌腳本或多格式混合檔（polyglot）都不會進到儲存區。
檔名用隨機 hex，不沿用使用者提供的檔名。
"""

import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_PIXELS = 25_000_000  # 解碼前先擋超大尺寸，避免解壓縮炸彈
AVATAR_SIZE = 256
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class AvatarError(ValueError):
    """上傳檔不是可接受的大頭貼；訊息可直接回給使用者。"""


def process_avatar(upload) -> ContentFile:
    if upload.size > AVATAR_MAX_BYTES:
        raise AvatarError("圖片不可超過 2 MB。")
    try:
        with Image.open(upload) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise AvatarError("只接受 JPG、PNG 或 WebP 圖片。")
            width, height = probe.size
            if width * height > AVATAR_MAX_PIXELS:
                raise AvatarError("圖片尺寸過大。")
            probe.verify()
        upload.seek(0)
        with Image.open(upload) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGBA")
            img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG", optimize=True)
    except AvatarError:
        raise
    except (
        UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
    ) as exc:
        raise AvatarError("無法讀取這張圖片，請換一張 JPG、PNG 或 WebP。") from exc
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.png")


def avatar_url(user) -> str | None:
    return user.avatar.url if user.avatar else None
