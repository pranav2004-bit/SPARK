import logging
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from core.responses import success_response, error_response
from core.permissions import IsAdminUser
from .serializers import AdminLoginSerializer, LogoutSerializer
from .tokens import get_tokens_for_user

User = get_user_model()
logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_MSG = "Invalid credentials"


class AdminLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status_code=400,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning("Admin login failed — unknown email: %s", email)
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        if not user.check_password(password):
            logger.warning("Admin login failed — wrong password for: %s", email)
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        if not user.is_active:
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        if user.role != "admin":
            # Never reveal role mismatch — identical response to wrong credentials
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        tokens = get_tokens_for_user(user)
        return success_response(
            data={
                **tokens,
                "user": {"email": user.email, "role": user.role},
            },
            message="Login successful",
            status_code=200,
        )


class AdminLogoutView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="refresh_token is required",
                status_code=400,
            )

        try:
            token = RefreshToken(serializer.validated_data["refresh_token"])
            token.blacklist()
        except TokenError:
            return error_response(message="Invalid or already blacklisted token", status_code=400)

        return success_response(message="Logged out successfully", status_code=200)
