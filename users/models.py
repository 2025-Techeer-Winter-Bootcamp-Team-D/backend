from django.db import models
from django.conf import settings
from companies.models import Company

class Favorite(models.Model):
    favorite_id=models.AutoField(primary_key=True)
    # 유저 연결
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='favorites'
    )
    
    # 2. 기업 연결
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='favorited_by'
    )
    
    # 3. 삭제 여부 (소프트 삭제용)
    is_deleted = models.BooleanField(default=False)
    # 4. 날짜 기록
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 동일 유저가 동일 기업을 중복 즐겨찾기 하는 것 방지
        unique_together = ('user', 'company')
        # DB 테이블 이름을 명시적으로 지정 
        db_table = 'favorite_company'

    def __str__(self):
        return f"{self.user.username} - {self.company.company_name}"