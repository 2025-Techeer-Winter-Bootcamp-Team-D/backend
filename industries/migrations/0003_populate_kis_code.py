# 데이터 마이그레이션: induty_code → kis_code 복사 및 KisIndustry에서 누락된 Industry 생성

from django.db import migrations


def populate_kis_code(apps, schema_editor):
    """기존 induty_code 값을 kis_code로 복사하고, KisIndustry에서 누락된 Industry 생성"""
    Industry = apps.get_model("industries", "Industry")
    KisIndustry = apps.get_model("industries", "KisIndustry")

    # 1. 기존 Industry의 induty_code → kis_code 복사
    for industry in Industry.objects.filter(induty_code__isnull=False):
        if industry.induty_code and not industry.kis_code:
            industry.kis_code = industry.induty_code
            industry.save()

    # 2. KisIndustry에 있지만 Industry에 없는 업종 추가
    # 기본 KOSPI 업종만 추가 (0005~0030)
    existing_kis_codes = set(
        Industry.objects.filter(kis_code__isnull=False).values_list(
            "kis_code", flat=True
        )
    )

    target_codes = [
        "0005",
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
        "0018",
        "0019",
        "0020",
        "0021",
        "0024",
        "0025",
        "0026",
        "0027",
        "0028",
        "0029",
        "0030",
    ]

    for kis_code in target_codes:
        if kis_code not in existing_kis_codes:
            kis_industry = KisIndustry.objects.filter(kis_code=kis_code).first()
            if kis_industry:
                Industry.objects.create(
                    kis_code=kis_code,
                    induty_code=kis_code,  # 기존 필드도 설정 (호환성)
                    name=kis_industry.name,
                    is_deleted=False,
                )


def reverse_populate(apps, schema_editor):
    """롤백: kis_code 제거"""
    Industry = apps.get_model("industries", "Industry")
    Industry.objects.update(kis_code=None)


class Migration(migrations.Migration):
    dependencies = [
        ("industries", "0002_add_kis_code_to_industry"),
    ]

    operations = [
        migrations.RunPython(populate_kis_code, reverse_populate),
    ]
