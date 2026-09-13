import uuid
from datetime import timedelta
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email


def parse_user_agent(ua_string):
    """
    Deliberately simple, dependency-free device/browser/OS parsing - "good
    enough for a login-history list", not a full user-agent database. Pulling
    in a third-party parsing library was considered and skipped: one more
    exact-version dependency to get wrong is not worth it for what's
    essentially cosmetic detail on a security log.
    """
    ua = (ua_string or '').lower()

    if 'ipad' in ua or 'tablet' in ua:
        device_type = 'Tablet'
    elif any(k in ua for k in ('mobile', 'iphone', 'android')):
        device_type = 'Mobile'
    elif ua:
        device_type = 'Desktop'
    else:
        device_type = 'Unknown'

    if 'edg/' in ua:
        browser = 'Edge'
    elif 'chrome/' in ua and 'chromium' not in ua:
        browser = 'Chrome'
    elif 'firefox/' in ua:
        browser = 'Firefox'
    elif 'safari/' in ua and 'chrome/' not in ua:
        browser = 'Safari'
    elif ua:
        browser = 'Other'
    else:
        browser = 'Unknown'

    if 'windows' in ua:
        os_name = 'Windows'
    elif 'mac os' in ua or 'macintosh' in ua:
        os_name = 'macOS'
    elif 'android' in ua:
        os_name = 'Android'
    elif 'iphone' in ua or 'ipad' in ua or 'ios' in ua:
        os_name = 'iOS'
    elif 'linux' in ua:
        os_name = 'Linux'
    elif ua:
        os_name = 'Other'
    else:
        os_name = 'Unknown'

    return device_type, browser, os_name


def get_client_ip(request):
    """
    Render (and most PaaS providers) terminate the connection at their own
    edge/proxy and forward the real client IP via X-Forwarded-For - reading
    REMOTE_ADDR alone would just record the proxy's IP for every login.
    """
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class LoginEvent(models.Model):
    """
    One row per login attempt - the basis for the login/device history shown
    on a user's admin detail page. Kept intentionally simple: IP, parsed
    device/browser/OS, success/failure, and when. Not a replacement for real
    session/device management (no "log out this device" capability here) -
    that's a bigger feature to build later if it's actually needed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Nullable: a failed attempt against an email that matches no account has
    # no user to attach to, but is still worth recording for visibility into
    # attempted access (e.g. repeated failures against an unknown email).
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_events', null=True, blank=True)
    email_attempted = models.EmailField()
    success = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    os = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['email_attempted', 'created_at']),
        ]

    def __str__(self):
        outcome = 'succeeded' if self.success else 'failed'
        return f'{self.email_attempted} login {outcome} at {self.created_at}'

    @classmethod
    def record(cls, request, email_attempted, user=None, success=True):
        device_type, browser, os_name = parse_user_agent(request.META.get('HTTP_USER_AGENT', ''))
        return cls.objects.create(
            user=user,
            email_attempted=email_attempted,
            success=success,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            device_type=device_type,
            browser=browser,
            os=os_name,
        )

    @classmethod
    def is_locked_out(cls, email):
        """
        True if `email` has racked up settings.LOGIN_LOCKOUT_MAX_ATTEMPTS
        failed login attempts within the last
        settings.LOGIN_LOCKOUT_WINDOW_MINUTES - see the settings.py comment
        for why this is a temporary, self-healing window built from
        existing LoginEvent history, rather than a persistent lockout flag
        needing an admin/support unlock.

        Checked uniformly regardless of whether `email` matches a real
        account. Only locking out REAL accounts (and never nonexistent
        ones) would let an attacker distinguish "no such account" from
        "account exists" purely by whether repeated failures eventually
        trigger a lockout - quietly undermining the same protection
        LoginView's generic "Invalid email or password" message (used for
        both a wrong password AND an unknown email) already provides.
        """
        from django.conf import settings
        window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_WINDOW_MINUTES)
        recent_failures = cls.objects.filter(
            email_attempted__iexact=email,
            success=False,
            created_at__gte=window_start,
        ).count()
        return recent_failures >= settings.LOGIN_LOCKOUT_MAX_ATTEMPTS
