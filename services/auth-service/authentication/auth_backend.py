from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class TokenVersionJWTAuthentication(JWTAuthentication):
    """
    Extends SimpleJWT to validate token_version against the DB.
    If the user's token_version was incremented (e.g. password change, institution_id fix),
    all previously issued tokens are immediately rejected — even before they expire.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        token_version = validated_token.get("token_version", 1)
        if user.token_version != token_version:
            raise InvalidToken(
                "Token is no longer valid. Please log in again.",
                code="token_version_mismatch",
            )
        return user
