from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.conf import settings as django_settings
from unfold.admin import ModelAdmin, TabularInline
from .models import User, LoginEvent
from apps.stores.models import Store, Staff

try:
    # Unfold's own form classes give the password/permission widgets on the
    # user change page the same styling as the rest of the theme. Falls back
    # gracefully if a future Unfold version renames/removes these - the admin
    # still works, just with slightly plainer password fields.
    from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
    _HAS_UNFOLD_FORMS = True
except ImportError:
    _HAS_UNFOLD_FORMS = False


class LockoutAwareAdminAuthForm(AdminAuthenticationForm):
    """
    Django Admin's login form ships with NO brute-force protection at all -
    unlike the customer-facing API login (apps/authentication/views.py::LoginView),
    which has a temporary, email-scoped lockout built on LoginEvent history
    (see the "Login lockout" comment block in settings.py for the full
    reasoning). That gap matters MORE here, not less: this admin panel is
    the single highest-value target in the app - referral commission
    rates, payout account details, AI provider API keys, every user's
    data - sitting at the well-known default /admin/ path, yet it was the
    least defended login surface in the project. This reuses the exact
    same LoginEvent-based lockout so both login surfaces get equal
    protection, rather than inventing a second, parallel mechanism.

    Deliberately does NOT hook Django's global user_login_failed signal for
    this: that signal also fires for the API LoginView's own authenticate()
    call, which already records its own LoginEvent explicitly - a global
    signal receiver would double-count every API login failure. Recording
    failures here, self-contained to the admin form, avoids that entirely.
    """
    def clean(self):
        username = self.cleaned_data.get('username')
        if username and LoginEvent.is_locked_out(username):
            raise ValidationError(
                f'Too many failed login attempts. Try again in {django_settings.LOGIN_LOCKOUT_WINDOW_MINUTES} minutes.',
                code='locked_out',
            )
        try:
            return super().clean()
        except ValidationError:
            if username:
                LoginEvent.record(self.request, email_attempted=username, success=False)
            raise


admin.site.login_form = LockoutAwareAdminAuthForm


class StoreOwnedInline(TabularInline):
    """Shows every store this user owns, right on their user detail page."""
    model = Store
    fk_name = 'owner'
    extra = 0
    fields = ['name', 'location', 'created_at']
    readonly_fields = ['created_at']
    show_change_link = True
    verbose_name = 'Store owned'
    verbose_name_plural = 'Stores owned'


class StaffRoleInline(TabularInline):
    """Shows every store this user works at (as staff) and their role there."""
    model = Staff
    fk_name = 'user'
    extra = 0
    fields = ['store', 'role', 'created_at']
    readonly_fields = ['created_at']
    show_change_link = True
    verbose_name = 'Staff role'
    verbose_name_plural = 'Staff roles (stores this user works at)'


class LoginEventInline(TabularInline):
    """
    Login/device history, right on the user's detail page - the most recent
    25 attempts (success and failure), newest first. Read-only: this is a
    log, not something an admin edits.

    Capped to 25 via `max_num` (the formset's own get_queryset() slices
    AFTER filtering by the parent user - see BaseInlineFormSet.__init__),
    NOT by slicing get_queryset() here. Slicing this admin-level queryset
    used to crash the user's change page with "Cannot filter a query once
    a slice has been taken": Django's BaseInlineFormSet always calls
    `.filter(user=<this user>)` on whatever queryset it's given to narrow
    it to just this user's events, and Django refuses to further filter an
    already-sliced queryset. "Add another" is suppressed separately, by
    has_add_permission below, not by max_num - extra=0 already removes the
    blank row, and max_num=0 would have hidden every EXISTING row too,
    which is why nothing ever showed here even before the crash.
    """
    model = LoginEvent
    fk_name = 'user'
    extra = 0
    max_num = 25
    can_delete = False
    fields = ['created_at', 'success', 'ip_address', 'device_type', 'browser', 'os']
    readonly_fields = fields
    verbose_name = 'Login event'
    verbose_name_plural = 'Recent login/device history (last 25)'
    ordering = ['-created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display = ['email', 'name', 'phone', 'is_staff', 'stores_owned_display', 'staff_roles_display', 'created_at']
    list_filter = ['is_staff', 'is_active', 'is_superuser', 'phone_verified', 'email_verified']
    search_fields = ['email', 'name', 'phone']
    # The referral code is derived from the phone number (User.save()) -
    # shown here for reference, never edited directly.
    readonly_fields = ['referral_code']
    ordering = ['-created_at']
    inlines = [StoreOwnedInline, StaffRoleInline, LoginEventInline]
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {'fields': ('name', 'phone', 'phone_verified', 'email_verified', 'referral_code')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {'fields': ('email', 'name', 'password1', 'password2')}),
    )

    if _HAS_UNFOLD_FORMS:
        form = UserChangeForm
        add_form = UserCreationForm
        change_password_form = AdminPasswordChangeForm

    def get_queryset(self, request):
        # Avoids one extra query per row for the two columns below - without
        # this, a Users list of any real size runs 2N extra queries just to
        # render the list page.
        return super().get_queryset(request).prefetch_related('stores', 'staff_roles__store')

    @admin.display(description='Owns')
    def stores_owned_display(self, obj):
        names = [s.name for s in obj.stores.all()]
        if not names:
            return '—'
        return ', '.join(names) if len(names) <= 2 else f'{names[0]}, {names[1]} +{len(names) - 2} more'

    @admin.display(description='Staff at')
    def staff_roles_display(self, obj):
        roles = [f'{s.store.name} ({s.get_role_display()})' for s in obj.staff_roles.all()]
        if not roles:
            return '—'
        return ', '.join(roles) if len(roles) <= 2 else f'{roles[0]}, {roles[1]} +{len(roles) - 2} more'


@admin.register(LoginEvent)
class LoginEventAdmin(ModelAdmin):
    """
    The full login history across every user, not just one - useful for
    spotting patterns (a burst of failed attempts against one email, logins
    from an unexpected country, etc) that wouldn't be obvious from any single
    user's page.
    """
    list_display = ['email_attempted', 'user', 'success', 'ip_address', 'device_type', 'browser', 'os', 'created_at']
    list_filter = ['success', 'device_type', 'browser', 'os']
    search_fields = ['email_attempted', 'ip_address', 'user__email']
    ordering = ['-created_at']
    readonly_fields = [f.name for f in LoginEvent._meta.fields]

    def has_add_permission(self, request):
        return False  # this is a log - entries are only ever created by the login flow itself
