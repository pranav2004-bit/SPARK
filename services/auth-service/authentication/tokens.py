from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    """
    Generate access + refresh token pair with custom claims.
    Injects: user_id, role, email, institution_id, student_id,
             is_profile_completed, force_password_change, token_version.
    All services share JWT_SIGNING_KEY and can validate tokens without calling auth-service.
    token_version allows invalidating all tokens for a user by incrementing the DB field.
    """
    refresh = RefreshToken.for_user(user)

    refresh["role"] = user.role
    refresh["email"] = user.email
    refresh["institution_id"] = str(user.institution_id) if user.institution_id else None
    refresh["student_id"] = user.student_id
    refresh["fullname"] = user.name or ""
    refresh["is_profile_completed"] = user.is_profile_completed
    refresh["force_password_change"] = user.force_password_change
    refresh["token_version"] = user.token_version

    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }
