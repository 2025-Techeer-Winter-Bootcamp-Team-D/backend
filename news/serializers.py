# news/serializers.py
"""
뉴스 데이터 Serializer
"""

from rest_framework import serializers
from .models import News, CompanyNews


# === 기본 필드 정의 ===

# 뉴스 목록용 공통 필드
NEWS_LIST_FIELDS = [
    "news_id",
    "title",
    "url",
    "summary",
    "author",
    "press",
    "keywords",
    "sentiment",
    "published_at",
]

# 뉴스 상세용 추가 필드
NEWS_DETAIL_EXTRA_FIELDS = ["content", "updated_at"]


# === News 모델 Serializer ===


class NewsSerializer(serializers.ModelSerializer):
    """뉴스 목록 조회용 Serializer (메타데이터 포함)"""

    class Meta:
        model = News
        fields = NEWS_LIST_FIELDS + ["created_at"]
        read_only_fields = ["news_id", "created_at"]


class NewsDetailSerializer(NewsSerializer):
    """뉴스 상세 조회용 Serializer (본문 포함)"""

    class Meta(NewsSerializer.Meta):
        fields = NEWS_LIST_FIELDS + NEWS_DETAIL_EXTRA_FIELDS + ["created_at"]
        read_only_fields = ["news_id", "created_at", "updated_at"]


# === CompanyNews 관계 Serializer ===


class CompanyNewsSerializer(serializers.Serializer):
    """
    기업 뉴스 목록용 Serializer (CompanyNews → News 필드 매핑)

    API 응답 형식은 기존과 동일하게 유지 (하위 호환)
    """

    news_id = serializers.IntegerField(source="news.news_id", read_only=True)
    title = serializers.CharField(source="news.title", read_only=True)
    summary = serializers.CharField(source="news.summary", read_only=True)
    url = serializers.CharField(source="news.url", read_only=True)
    author = serializers.CharField(source="news.author", read_only=True)
    press = serializers.CharField(source="news.press", read_only=True)
    keywords = serializers.JSONField(source="news.keywords", read_only=True)
    sentiment = serializers.CharField(source="news.sentiment", read_only=True)
    published_at = serializers.DateTimeField(source="news.published_at", read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class CompanyNewsDetailSerializer(CompanyNewsSerializer):
    """
    기업 뉴스 상세용 Serializer (본문 포함)

    API 응답 형식은 기존과 동일하게 유지 (하위 호환)
    """

    content = serializers.CharField(source="news.content", read_only=True)
    updated_at = serializers.DateTimeField(source="news.updated_at", read_only=True)


class IndustryNewsSerializer(serializers.Serializer):
    """
    산업 뉴스 목록용 Serializer

    CompanyNews를 통해 조회하며 기업 정보를 함께 반환합니다.
    """

    # News 필드 매핑
    news_id = serializers.IntegerField(source="news.news_id", read_only=True)
    title = serializers.CharField(source="news.title", read_only=True)
    summary = serializers.CharField(source="news.summary", read_only=True)
    url = serializers.CharField(source="news.url", read_only=True)
    author = serializers.CharField(source="news.author", read_only=True)
    press = serializers.CharField(source="news.press", read_only=True)
    keywords = serializers.JSONField(source="news.keywords", read_only=True)
    sentiment = serializers.CharField(source="news.sentiment", read_only=True)
    published_at = serializers.DateTimeField(source="news.published_at", read_only=True)

    # 기업 정보 추가
    stock_code = serializers.CharField(source="company.stock_code", read_only=True)
    company_name = serializers.CharField(source="company.company_name", read_only=True)
