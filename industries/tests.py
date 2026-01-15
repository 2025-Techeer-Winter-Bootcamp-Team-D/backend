from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from industries.models import Industry, IndustryRanking
from companies.models import Company
from django.core.management import call_command # 명령어를 실행하기 위해 필수
from datetime import date

class IndustryRankingLogicTestCase(APITestCase):
    def setUp(self):
        """
        순위 계산 로직 검증을 위해 '원천 데이터(Company)'만 생성합니다.
        """
        # 1. 산업 생성
        self.semi = Industry.objects.create(name="반도체")
        self.auto = Industry.objects.create(name="자동차")
        self.bio = Industry.objects.create(name="바이오")

        # 2. 기업 데이터 생성 (이 금액들이 합산되어 순위가 결정됨)
        # [반도체] 합계: 300조 (예상 1위)
        Company.objects.create(stock_code="S1", company_name="삼성", industry=self.semi, market_amount=200000000000000)
        Company.objects.create(stock_code="S2", company_name="하이닉스", industry=self.semi, market_amount=100000000000000)
        
        # [자동차] 합계: 150조 (예상 2위)
        Company.objects.create(stock_code="A1", company_name="현대", industry=self.auto, market_amount=100000000000000)
        Company.objects.create(stock_code="A2", company_name="기아", industry=self.auto, market_amount=50000000000000)

        # [바이오] 합계: 50조 (예상 3위)
        Company.objects.create(stock_code="B1", company_name="셀트리온", industry=self.bio, market_amount=50000000000000)

        self.url = reverse('industry_rankings')

    def test_ranking_generation_and_api_response(self):
        """
        로직 검증: 시가총액 기반으로 순위가 매겨지고 API에 반영되는지 통합 테스트
        """
        # 1. 산업 순위 업데이트 명령어 실행 (우리가 만든 명령어 호출)
        # 이 시점에 IndustryRanking 테이블에 데이터가 자동으로 채워집니다.
        call_command('update_industry_rankings')

        # 2. API 호출
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data['data']
        
        # 3. 시가총액 순서대로 순위가 매겨졌는지 검증
        # 1위: 반도체 (300조)
        self.assertEqual(data[0]['name'], "반도체")
        self.assertEqual(data[0]['rank'], 1)
        self.assertEqual(data[0]['amount'], 300000000000000)
        
        # 2위: 자동차 (150조)
        self.assertEqual(data[1]['name'], "자동차")
        self.assertEqual(data[1]['rank'], 2)
        self.assertEqual(data[1]['amount'], 150000000000000)

        # 3위: 바이오 (50조)
        self.assertEqual(data[2]['name'], "바이오")
        self.assertEqual(data[2]['rank'], 3)
        
class IndustryRankingExceptionTestCase(APITestCase):
    def setUp(self):
        self.url = reverse('industry-rankings')

    def test_api_returns_404_when_no_rankings_exist(self):
        """
        예외 상황 1: IndustryRanking 테이블이 비어있을 때 API 응답 확인
        """
        response = self.client.get(self.url)
        
        # 데이터가 없으므로 404를 반환해야 함
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['message'], "industry_rankings not found")

    def test_ranking_ignores_deleted_companies(self):
        """
        예외 상황 2: 삭제 처리된(is_deleted=True) 기업은 합산에서 제외되는가?
        """
        # 1. 산업 생성
        semi = Industry.objects.create(name="반도체")
        
        # 2. 기업 생성 (하나는 정상, 하나는 삭제됨)
        # 정상 기업: 100조
        Company.objects.create(stock_code="S1", company_name="정상기업", industry=semi, market_amount=100_000_000_000_000, is_deleted=False)
        # 삭제된 기업: 200조 (합산되면 안 됨)
        Company.objects.create(stock_code="S2", company_name="삭제기업", industry=semi, market_amount=200_000_000_000_000, is_deleted=True)

        # 3. 명령어 실행
        call_command('update_industry_rankings')

        # 4. 검증
        ranking = IndustryRanking.objects.get(industry=semi)
        # 삭제된 기업의 200조는 제외되고 100조만 기록되어야 함
        self.assertEqual(ranking.amount, 100_000_000_000_000)

    def test_ranking_ignores_zero_amount_industries(self):
        """
        예외 상황 3: 기업은 있으나 시가총액 합계가 0인 산업은 순위에서 제외되는가?
        """
        # 1. 산업 생성
        zero_industry = Industry.objects.create(name="유령산업")
        
        # 2. 시가총액이 0원인 기업 생성
        Company.objects.create(stock_code="Z1", company_name="빵원기업", industry=zero_industry, market_amount=0)

        # 3. 명령어 실행
        call_command('update_industry_rankings')

        # 4. 검증: IndustryRanking에 해당 산업 데이터가 없어야 함
        exists = IndustryRanking.objects.filter(industry=zero_industry).exists()
        self.assertFalse(exists)