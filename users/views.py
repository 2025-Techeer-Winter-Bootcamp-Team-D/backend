import logging
from django.contrib.auth.models import User
from rest_framework import generics, status, viewsets, mixins
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Favorite
from .serializers import FavoriteSerializer
from companies.models import Company

# 프로젝트 내부 모듈
from .serializers import RegisterSerializer, LoginSerializer

# swagger 관련
from drf_spectacular.utils import extend_schema, extend_schema_view

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


# --즐겨찾기--

# 예외 로깅을 위한 설정
logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="즐겨찾기 목록 조회"),
    create=extend_schema(summary="즐겨찾기 추가"),
    destroy=extend_schema(summary="즐겨찾기 삭제"),
)
class FavoriteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]  # 로그인한 사용자만 접근 가능

    # 목록 가져오기 (is_deleted=False 만 가져오기기)
    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user, is_deleted=False)

    # 즐겨찾기 추가
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(
            {"status": 201, "message": "즐겨찾기 추가 성공", "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        try:
            # get_object()는 get_queryset()을 기반으로 하므로 is_deleted=False 조건이 자동 적용
            instance = self.get_object()
            instance.is_deleted = True
            instance.save()

            return Response(
                {"status": 200, "message": "즐겨찾기 삭제 성공", "data": None},
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception("즐겨찾기 삭제 중 예외 발생")
            return Response(
                {"message": "해당 즐겨찾기 항목을 찾을 수 없거나 이미 삭제되었습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
