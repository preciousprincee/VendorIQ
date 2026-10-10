import secrets
import string
import uuid
from datetime import timedelta
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from .phone import normalize_phone

REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
# Excludes visually-confusable characters (0/O, 1/I/L) since this code gets
# read aloud, typed by hand, and put on marketing links - not just
# copy-pasted.
REFERRAL_CODE_ALPHABET = ''.join(c for c in REFERRAL_CODE_ALPHABET if c not in 'O0I1L')


def generate_referral_code():
    return ''.join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(7))


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
    # The user's phone number IS their referral code (canonical 0XXXXXXXXXX
    # form - see apps/authentication/phone.py). It is kept in sync by
    # save() below rather than being independently editable, so the two can
    # never drift apart. NULL (not '') when the user has no valid phone yet,
    # because a unique column can hold many NULLs but only one ''. A phone
    # number can only be edited while phone_verified is False - see
    # UpdateProfileSerializer.
    referral_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    phone_verified = models.BooleanField(
        default=False,
        help_text='Set when the user proves they own the number by entering the SMS code we send (see '
                   'apps/authentication/verification.py). Once True they can no longer change the number themselves '
                   '(it is their referral code and a free-trial anti-abuse key).',
    )
    email_verified = models.BooleanField(
        default=False,
        help_text='Set when the user enters the code we email them, or automatically for Google sign-in (Google has '
                   'already verified that address).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email

    @property
    def is_fully_verified(self):
        """Both contact details proven - required before a free trial or a paid checkout."""
        return bool(self.email_verified and self.phone_verified)

    def save(self, *args, **kwargs):
        # Keep referral_code == canonical phone. Skipped for update_fields
        # saves that don't touch phone (e.g. Django's own last_login update
        # on every login) so those don't pay for an extra query.
        update_fields = kwargs.get('update_fields')
        if update_fields is None or 'phone' in update_fields:
            canonical = normalize_phone(self.phone)
            if canonical:
                self.phone = canonical
            code = canonical or None
            if code and User.objects.filter(referral_code=code).exclude(pk=self.pk).exists():
                # Another account already holds this number. The serializers
                # reject this case with a clear message before it gets here;
                # this is just a last line of defence so a duplicate can
                # never crash a save with an IntegrityError or steal
                # someone else's code.
                code = None
            self.referral_code = code
            if update_fields is not None:
                kwargs['update_fields'] = list(update_fields) + ['referral_code']
        super().save(*args, **kwargs)

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
    from django.conf import settings
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    num_proxies = settings.REST_FRAMEWORK.get('NUM_PROXIES', 1)
    if forwarded_for and num_proxies:
        # X-Forwarded-For is client-editable: a client can prepend anything
        # it likes, and only the entries appended by OUR proxies can be
        # trusted. Taking the LEFT-most value (as this used to) let anyone
        # spoof the IP recorded in login history / trial abuse signals.
        # The trusted client IP is `num_proxies` entries from the right.
        addrs = [a.strip() for a in forwarded_for.split(',') if a.strip()]
        if addrs:
            return addrs[-num_proxies] if len(addrs) >= num_proxies else addrs[0]
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
            # Explicit names: they must match migration 0005 exactly.
            models.Index(fields=['user', 'created_at'], name='login_event_user_id_df2f7e_idx'),
            models.Index(fields=['email_attempted', 'created_at'], name='login_event_email_a_037f5e_idx'),
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


class VerificationCode(models.Model):
    """
    One outstanding email/SMS one-time code. Only a keyed hash of the code is
    stored (a DB leak must not hand out live codes), it expires quickly, and
    it locks after a handful of wrong guesses - a 6-digit code is only safe
    because of those two limits. See apps/authentication/verification.py.
    """
    class Channel(models.TextChoices):
        EMAIL = 'EMAIL', 'Email'
        PHONE = 'PHONE', 'Phone'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_codes')
    channel = models.CharField(max_length=5, choices=Channel.choices)
    # The exact address / canonical number this code was sent to - a code
    # for an OLD number must never verify a NEW one the user swapped in.
    target = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'verification_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'channel', 'created_at']),
            models.Index(fields=['channel', 'target', 'created_at']),
        ]

    def __str__(self):
        return f'{self.channel} code for {self.target}'
