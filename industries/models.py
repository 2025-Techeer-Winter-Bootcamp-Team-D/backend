# industries/models.py
from django.db import models


class Industry(models.Model):
    # ERD상 산업 아이디 (PK)
    industry_id = models.BigAutoField(primary_key=True)
    # 산업 이름
    name = models.CharField(max_length=255)
    # 업종코드 (KSIC 코드, 예: "264", "26", "C26")
    induty_code = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True
    )
    # 산업 설명
    description = models.TextField(null=True, blank=True)
    # 생성/수정/삭제 필드 (공통)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "industry"  # 실제 DB 테이블명 고정
