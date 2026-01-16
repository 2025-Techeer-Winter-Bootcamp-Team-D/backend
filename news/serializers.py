# news/serializers.py
"""
뉴스 데이터 Serializer
"""

from rest_framework import serializers
from .models import News, CompanyNews


class NewsSerializer(serializers.ModelSerializer):
    """뉴스 목록 조회용 Serializer (메타데이터 포함)"""

    class Meta:
        model = News
        fields = [
            "news_id",
            "title",
            "url",
            "summary",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["news_id", "created_at"]


class NewsDetailSerializer(serializers.ModelSerializer):
    """뉴스 상세 조회용 Serializer (본문 포함)"""

    class Meta:
        model = News
        fields = [
            "news_id",
            "title",
            "url",
            "summary",
            "content",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["news_id", "created_at", "updated_at"]


class CompanyNewsSerializer(serializers.ModelSerializer):
    """
    기업 뉴스 목록용 Serializer (매핑 테이블 + News 조인)

    API 응답 형식은 기존과 동일하게 유지 (하위 호환)
    """

    # News 테이블에서 데이터 가져오기
    news_id = serializers.IntegerField(source="news.news_id", read_only=True)
    title = serializers.CharField(source="news.title", read_only=True)
    summary = serializers.CharField(source="news.summary", read_only=True)
    url = serializers.CharField(source="news.url", read_only=True)
    author = serializers.CharField(source="news.author", read_only=True)
    press = serializers.CharField(source="news.press", read_only=True)
    keywords = serializers.JSONField(source="news.keywords", read_only=True)
    published_at = serializers.DateTimeField(source="news.published_at", read_only=True)

    class Meta:
        model = CompanyNews
        fields = [
            "news_id",
            "title",
            "summary",
            "url",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["news_id", "created_at"]


class CompanyNewsDetailSerializer(serializers.ModelSerializer):
    """
    기업 뉴스 상세용 Serializer (본문 포함)

    API 응답 형식은 기존과 동일하게 유지 (하위 호환)
    """

    # News 테이블에서 데이터 가져오기
    news_id = serializers.IntegerField(source="news.news_id", read_only=True)
    title = serializers.CharField(source="news.title", read_only=True)
    summary = serializers.CharField(source="news.summary", read_only=True)
    content = serializers.CharField(source="news.content", read_only=True)
    url = serializers.CharField(source="news.url", read_only=True)
    author = serializers.CharField(source="news.author", read_only=True)
    press = serializers.CharField(source="news.press", read_only=True)
    keywords = serializers.JSONField(source="news.keywords", read_only=True)
    published_at = serializers.DateTimeField(source="news.published_at", read_only=True)
    updated_at = serializers.DateTimeField(source="news.updated_at", read_only=True)

    class Meta:
        model = CompanyNews
        fields = [
            "news_id",
            "title",
            "summary",
            "content",
            "url",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["news_id", "created_at", "updated_at"]
