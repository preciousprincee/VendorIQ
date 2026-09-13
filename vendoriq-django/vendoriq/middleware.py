from django.http import JsonResponse


class MaxBodySizeMiddleware:
    """
    Rejects a request outright, based on its Content-Length header, before
    Django reads or parses the body at all.

    Why this exists: DRF's file/JSON parsers will happily read whatever the
    client sends - a well-behaved 5MB product photo, or (deliberately or by
    a buggy client) a multi-gigabyte body. The serializer-level size check on
    Product.photo only runs *after* that data has already been read into a
    temp file, which under a burst of large concurrent uploads is real disk
    I/O and worker time spent on requests that were always going to be
    rejected. Checking Content-Length up front turns that into an instant
    413 instead.

    This is a coarse, cheap safety net, not a replacement for a reverse
    proxy / CDN request-size limit (Render's edge may already have one) -
    but it costs nothing and doesn't rely on that being configured correctly.
    """
    MAX_BODY_BYTES = 10 * 1024 * 1024  # 10MB - comfortably above the 5MB photo cap, well below "abuse"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length:
            try:
                if int(content_length) > self.MAX_BODY_BYTES:
                    return JsonResponse({'error': 'Request body too large.'}, status=413)
            except (TypeError, ValueError):
                pass
        return self.get_response(request)
