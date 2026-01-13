from django.contrib.auth.models import User 
from django.contrib.auth.password_validation import validate_password # Django의 기본 pw 검증 도구
from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.validators import UniqueValidator # 이메일 중복 방지를 위한 검증 도구


# 회원가입 시리얼라이저
class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())], # 이메일에 대한 중복 검증
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password], # 비밀번호에 대한 검증
    )
    password2 = serializers.CharField( # 비밀번호 확인을 위한 필드
        write_only=True,
        required=True,
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, data): # password과 password2의 일치 여부 확인
        if data['password'] != data['password2']:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."})
        return data

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

# --- 로그인 시리얼라이저 ---
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get("request"), 
                username=email,                     
                password=password
            )

            if not user:
                raise serializers.ValidationError("이메일 또는 비밀번호가 틀렸습니다.")
        else:
            raise serializers.ValidationError("이메일과 비밀번호를 모두 입력해주세요.")
        
        data['user'] = user
        return data