from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    allauth's default populate_user() maps a social provider's profile data
    onto Django's standard first_name/last_name fields. This project's User
    model (apps/authentication/models.py) has neither - just a single `name`
    field - so without this override, a brand-new Google sign-up would be
    created with an empty name (silently: CharField allows '' at the DB
    level, so this wouldn't error, just leave the name blank).
    """
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        full_name = data.get('name') or ' '.join(filter(None, [data.get('first_name'), data.get('last_name')]))
        user.name = full_name or (data.get('email', '').split('@')[0] if data.get('email') else 'Google User')
        return user
