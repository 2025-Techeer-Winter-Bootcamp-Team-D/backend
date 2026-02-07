from django.contrib import admin
from .models import Industry, IndustryChart1d, IndustryChart3d, IndustryChart1w, IndustryChart2w

# 관리자 페이지에서 보고 싶은 모델들을 등록합니다.
@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ('name', 'induty_code', 'is_deleted')

@admin.register(IndustryChart1d)
class IndustryChart1dAdmin(admin.ModelAdmin):
    list_display = ('industry', 'base_date', 'close')

# 나머지 차트 모델들도 동일하게 등록 가능합니다.
admin.site.register(IndustryChart3d)
admin.site.register(IndustryChart1w)
admin.site.register(IndustryChart2w)