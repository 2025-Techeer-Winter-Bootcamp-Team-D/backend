from django.contrib import admin
from news.models import News, CrawlJob, KeywordFrequency, CompanyNews


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ["news_id", "title", "press", "published_at", "created_at"]
    list_filter = ["press", "is_deleted", "published_at"]
    search_fields = ["title", "content"]
    readonly_fields = ["news_id", "created_at", "updated_at"]


@admin.register(KeywordFrequency)
class KeywordFrequencyAdmin(admin.ModelAdmin):
    list_display = [
        "keyword",
        "frequency",
        "doc_count",
        "first_seen_at",
        "last_seen_at",
    ]
    list_filter = ["first_seen_at", "last_seen_at"]
    search_fields = ["keyword"]
    ordering = ["-frequency", "-doc_count"]
    readonly_fields = ["keyword_id", "created_at", "updated_at"]


@admin.register(CrawlJob)
class CrawlJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "total_articles",
        "successful_articles",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    readonly_fields = ["id", "created_at", "started_at", "completed_at"]


@admin.register(CompanyNews)
class CompanyNewsAdmin(admin.ModelAdmin):
    list_display = ["id", "company", "news", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["company__company_name", "news__title"]
