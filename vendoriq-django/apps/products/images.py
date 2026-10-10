"""
Product photo handling - one small photo per product, by design.

Storage is the thing that grows without bound, so photos are:
  * limited in size on the way IN (PRODUCT_PHOTO_MAX_UPLOAD_BYTES, default 1 MB -
    the web app shrinks phone photos before uploading, so honest users never hit it),
  * limited in pixel count (a tiny file can still decode into a memory bomb),
  * restricted to JPEG / PNG / WebP (no GIF/TIFF/SVG surprises),
  * re-encoded as a small WebP no larger than 800 px on the long edge. That
    typically leaves 20-80 KB per product, and drops all EXIF metadata -
    including the GPS position phones embed in photos.
"""
import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}
MAX_PIXELS = 25_000_000          # ~ a 5000 x 5000 photo; anything bigger is refused before decoding
OUTPUT_MAX_EDGE = 800
OUTPUT_TARGET_BYTES = 250 * 1024


class PhotoError(ValueError):
    """A problem the person can fix; the message is shown to them as-is."""


def max_upload_bytes():
    return int(getattr(settings, 'PRODUCT_PHOTO_MAX_UPLOAD_BYTES', 1024 * 1024))


def _flatten(img):
    """Transparent PNGs would turn black as JPEG/WebP-without-alpha; put them on white."""
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert('RGB')


def optimize_photo(upload):
    limit = max_upload_bytes()
    if upload.size > limit:
        raise PhotoError(f'Photo is too large ({upload.size // 1024} KB). The limit is {limit // 1024} KB - try a smaller picture.')
    try:
        img = Image.open(upload)
        if img.format not in ALLOWED_FORMATS:
            raise PhotoError('Use a JPEG, PNG or WebP photo.')
        width, height = img.size            # lazy: the pixels have not been decoded yet
        if width * height > MAX_PIXELS:
            raise PhotoError('That picture has too many pixels. Please use a smaller photo.')
        img.load()
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise PhotoError('That file is not a valid image.')

    img = ImageOps.exif_transpose(img)      # honour the phone's rotation, then the metadata is dropped on save
    img = _flatten(img)
    img.thumbnail((OUTPUT_MAX_EDGE, OUTPUT_MAX_EDGE), Image.Resampling.LANCZOS)

    data, ext, mime = b'', 'webp', 'image/webp'
    for quality in (80, 70, 60):
        buf = BytesIO()
        try:
            img.save(buf, 'WEBP', quality=quality, method=4)
        except (OSError, KeyError, ValueError):   # this Pillow build lacks WebP: fall back to JPEG
            buf = BytesIO()
            img.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
            ext, mime = 'jpg', 'image/jpeg'
        data = buf.getvalue()
        if len(data) <= OUTPUT_TARGET_BYTES:
            break
    # A random name: never trust (or leak) the uploader's file name, and two
    # products can't overwrite each other's photo.
    return SimpleUploadedFile(f'{uuid.uuid4().hex}.{ext}', data, content_type=mime)
