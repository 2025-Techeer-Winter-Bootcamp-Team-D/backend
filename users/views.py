from django.contrib.auth.models import User
from rest_framework import generics
from django.http import HttpResponse
from .serializers import RegisterSerializer
from drf_spectacular.utils import extend_schema 

class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer

   
    @extend_schema(
        summary="회원가입",
        description="사용자 정보를 입력받아 회원가입을 진행합니다.",
        request=RegisterSerializer,  
        responses={201: RegisterSerializer},
    )
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

# 로그인
def login_account(request):
    return HttpResponse('로그인')

# 로그아웃
def logout_account(request):
    return HttpResponse('로그아웃')
