from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user, student=None):
    """
    Generate access + refresh token pair with custom claims.
    Injects: user_id, role, email, student_id, is_profile_completed.
    """
    refresh = RefreshToken.for_user(user)

    refresh["role"] = user.role
    refresh["email"] = user.email

    if student is not None:
        refresh["student_id"] = student.student_id
        refresh["is_profile_completed"] = student.is_profile_completed
    else:
        refresh["student_id"] = None
        refresh["is_profile_completed"] = None

    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }
