from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

# 프로젝트 내부 모듈
from .serializers import RegisterSerializer, LoginSerializer

# swagger 관련
from drf_spectacular.utils import extend_schema

# jwt 관련
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


# --회원가입--
class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer

    @extend_schema(
        summary="회원가입",
        request=RegisterSerializer,
        responses={201: RegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


# --로그인--
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer

    @extend_schema(summary="로그인", request=LoginSerializer)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "email": user.email,
                "username": user.username,
            },
            status=status.HTTP_200_OK,
        )


# --로그아웃--
class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="로그아웃 (Refresh 토큰 필요)",
        request={
            "application/json": {
                "type": "object",
                "properties": {"refresh": {"type": "string"}},
                "required": ["refresh"],
            }
        },
    )
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"message": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"message": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except TokenError:
            return Response(
                {"message": "Invalid token or already logged out."},
                status=status.HTTP_400_BAD_REQUEST,
            )
