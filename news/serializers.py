# news/serializers.py
"""
뉴스 데이터 Serializer
"""

from rest_framework import serializers
from .models import News


class NewsSerializer(serializers.ModelSerializer):
    """뉴스 목록 조회용 Serializer"""

    class Meta:
        model = News
        fields = [
            "news_id",
            "title",
            "url",
            "summary",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["news_id", "created_at"]


class NewsDetailSerializer(serializers.ModelSerializer):
    """뉴스 상세 조회용 Serializer"""

    class Meta:
        model = News
        fields = [
            "news_id",
            "title",
            "url",
            "summary",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["news_id", "created_at", "updated_at"]
