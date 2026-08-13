from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JWTUser:
    """
    Stateless user-like object populated from JWT claims.
    No database lookup — all info comes from the validated token payload.
    """
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __init__(self, payload):
        self.id = payload.get("user_id")
        self.pk = self.id
        self.role = payload.get("role", "")
        self.email = payload.get("email", "")
        self.institution_id = payload.get("institution_id")
        self.student_id = payload.get("student_id")
        self.is_profile_completed = payload.get("is_profile_completed", False)
        self.force_password_change = payload.get("force_password_change", False)
        self.token_version = payload.get("token_version", 1)

    def __str__(self):
        return f"JWTUser({self.email or self.student_id}, role={self.role})"


class ServiceJWTAuthentication(JWTAuthentication):
    """
    JWT authentication without database user lookup.
    Validates token signature + expiry using shared JWT_SIGNING_KEY,
    then returns a JWTUser populated from claims.
    All services share the same key — no call to auth-service needed.
    """

    def get_user(self, validated_token):
        return JWTUser(validated_token)
