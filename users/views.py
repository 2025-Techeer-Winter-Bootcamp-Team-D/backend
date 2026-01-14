from django.contrib.auth.models import User
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import Favorite
from .serializers import FavoriteSerializer
from companies.models import Company
# 프로젝트 내부 모듈듈 
from .serializers import RegisterSerializer, LoginSerializer
# swagger 관련련
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
        responses={201: RegisterSerializer})
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

# --로그인--
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    
    @extend_schema(summary="로그인", request=LoginSerializer)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email,
            'username': user.username
        }, status=status.HTTP_200_OK)


 # --로그아웃--
class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="로그아웃 (Refresh 토큰 필요)",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "refresh": {"type": "string"}
                },
                "required": ["refresh"]
            }
        }
    )
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        
        if not refresh_token:
            return Response(
                {"message": "Refresh token is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"message": "Successfully logged out."}, 
                status=status.HTTP_205_RESET_CONTENT
            )
        except TokenError:
            return Response(
                {"message": "Invalid token or already logged out."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    # --즐겨찾기--
class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated] # 로그인한 사용자만 접근 가능
   
    #목록 가져오기 (is_deleted=False 만 가져오기기)
    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user, is_deleted=False)
    #즐겨찾기 추가 
    def create(self, request):
        stock_code = request.data.get('companyId') # 프론트에서 보낸 종목코드
        
        if not stock_code:
            return Response({"message": "companyId(종목코드)가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. 기업 존재 확인
            company = Company.objects.get(stock_code=stock_code)
            
            # 2. 유저와 기업 조합으로 기존 데이터가 있는지 확인 (없으면 생성)
            favorite, created = Favorite.objects.get_or_create(
                user=request.user,
                company=company
            )
            
            # 3. 상태 업데이트 (Soft delete 해제제)
            favorite.is_deleted = False
            favorite.save()
            
            serializer = self.get_serializer(favorite)
            return Response({
                "status": 201,
                "message": "즐겨찾기 추가 성공",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)

        except Company.DoesNotExist:
            return Response({"message": "존재하지 않는 기업 종목코드입니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"message": "서버 내부 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    #즐겨찾기 삭제(is_deleted 를 True 로)
    def destroy(self, request, pk=None):
        try:
            # favorite_id(pk)로 해당 유저의 즐겨찾기를 찾음
            favorite = Favorite.objects.get(favorite_id=pk, user=request.user)
            favorite.is_deleted = True
            favorite.save()
            
            return Response({
                "status": 200,
                "message": "즐겨찾기 삭제 성공",
                "data": None
            }, status=status.HTTP_200_OK)
            
        except Favorite.DoesNotExist:
            return Response({"message": "해당 즐겨찾기 항목을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)