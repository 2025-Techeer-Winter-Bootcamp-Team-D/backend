import django.db.models.deletion
from django.db import migrations, models

def migrate_old_data(apps, schema_editor):
    OldModel = apps.get_model('sankeys', 'SankeyFinancialData')
    NewModel = apps.get_model('sankeys', 'SankeyData')
    
    for old in OldModel.objects.all():
        # 기존 모델의 필드명을 새 모델의 구조에 맞게 매핑
        NewModel.objects.create(
            company=old.company,
            fiscal_year=old.year,  # old.year로 수정 완료
            nodes=[],  
            links=[],  
            is_loss=old.net_income < 0 if old.net_income else False,
            raw_values={
                'total_revenue': old.revenue,
                'cogs': old.cost_of_sales,
                'sg_a': old.sg_and_a,
                'net_income': old.net_income,
            },
        )

class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0001_initial'),
        ('sankeys', '0001_initial'),
    ]

    operations = [
        # 1. 새 모델 생성
        migrations.CreateModel(
            name='SankeyData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fiscal_year', models.IntegerField()),
                ('nodes', models.JSONField(default=list)),
                ('links', models.JSONField(default=list)),
                ('is_loss', models.BooleanField(default=False)),
                ('raw_values', models.JSONField(default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sankey_data', to='companies.company')),
            ],
            options={
                'unique_together': {('company', 'fiscal_year')},
            },
        ),
        
        # 2. 데이터 이관 (CreateModel 이후, DeleteModel 이전)
        migrations.RunPython(migrate_old_data),

        # 3. 기존 모델 삭제
        migrations.DeleteModel(
            name='SankeyFinancialData',
        ),
    ]