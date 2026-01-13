from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, _request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        email = (kwargs.get("email") or username or "").strip()

        if not email or password is None:
            return None

        try:
            user = UserModel.objects.filter(email__iexact=email).first()
        except Exception:
            return None
        
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None