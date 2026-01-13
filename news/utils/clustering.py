from sklearn.cluster import DBSCAN
import numpy as np
from collections import defaultdict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class NewsClusteringService:
    def __init__(self, eps=0.1, min_samples=2):
        """
        eps: 코사인 거리 임계값 (0.1은 유사도 약 0.9 이상을 의미)
        min_samples: 하나의 이슈로 묶기 위한 최소 기사 수
        """
        self.dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")

    def cluster_news(self, embeddings):
        """
        embeddings: EmbeddingService에서 받은 벡터 리스트 (N, 768)
        return: 클러스터 레이블 리스트 (-1은 노이즈, 0 이상은 클러스터 ID)
        """
        if not embeddings:
            return []

        if len(embeddings) < 2:
            # 단일 항목은 클러스터를 형성할 수 없으므로 노이즈(-1)로 처리
            return [-1]

        # 1. 벡터 데이터셋 준비
        X = np.array(embeddings)

        # 2. 클러스터링 실행
        labels = self.dbscan.fit_predict(X)

        return labels.tolist()

    def deduplicate_by_cluster(self, labels, news_items, strategy="latest"):
        """
        클러스터링 결과를 기반으로 중복 뉴스 제거

        Args:
            labels: cluster_news()에서 반환된 클러스터 레이블 리스트
            news_items: 뉴스 정보 리스트. 각 항목은 다음 키를 포함:
                - index: 원본 리스트에서의 인덱스
                - published_at: 발행일 (datetime 또는 None)
                - content_length: 본문 길이 (int, 선택적)
            strategy: 대표 기사 선택 전략
                - "latest": 가장 최신 기사 선택 (published_at 기준)
                - "longest": 가장 긴 본문 기사 선택 (content_length 기준)
                - "latest_longest": 최신 기사 중 가장 긴 본문 선택

        Returns:
            keep_indices: 유지할 뉴스의 인덱스 리스트 (set)
            duplicate_indices: 제거할 뉴스의 인덱스 리스트 (set)
        """
        if not labels or not news_items:
            return set(range(len(news_items))), set()

        if len(labels) != len(news_items):
            logger.warning(
                f"Labels length ({len(labels)}) != news_items length ({len(news_items)})"
            )
            return set(range(len(news_items))), set()

        # 클러스터별로 그룹화
        cluster_groups = defaultdict(list)
        noise_items = []  # 노이즈(-1)는 각각 독립적으로 처리

        for idx, label in enumerate(labels):
            if label == -1:
                # 노이즈는 모두 유지
                noise_items.append(idx)
            else:
                cluster_groups[label].append(idx)

        keep_indices = set(noise_items)  # 노이즈는 모두 유지
        duplicate_indices = set()

        # 각 클러스터에서 대표 기사 선택
        for cluster_id, indices in cluster_groups.items():
            if len(indices) <= 1:
                # 클러스터에 1개만 있으면 모두 유지
                keep_indices.update(indices)
                continue

            # 대표 기사 선택
            representative_idx = self._select_representative(
                indices, news_items, strategy
            )

            # 대표 기사는 유지, 나머지는 중복으로 표시
            keep_indices.add(representative_idx)
            duplicate_indices.update(
                idx for idx in indices if idx != representative_idx
            )

        return keep_indices, duplicate_indices

    def _select_representative(self, indices, news_items, strategy):
        """
        클러스터 내에서 대표 기사 선택

        Args:
            indices: 클러스터에 속한 뉴스 인덱스 리스트
            news_items: 전체 뉴스 정보 리스트
            strategy: 선택 전략

        Returns:
            대표 기사 인덱스
        """
        if strategy == "latest":
            # 가장 최신 기사 선택
            best_idx = indices[0]
            best_date = self._get_published_at(news_items[best_idx])

            for idx in indices[1:]:
                date = self._get_published_at(news_items[idx])
                if date and (not best_date or date > best_date):
                    best_date = date
                    best_idx = idx

            return best_idx

        elif strategy == "longest":
            # 가장 긴 본문 기사 선택
            best_idx = indices[0]
            best_length = news_items[best_idx].get("content_length", 0)

            for idx in indices[1:]:
                length = news_items[idx].get("content_length", 0)
                if length > best_length:
                    best_length = length
                    best_idx = idx

            return best_idx

        elif strategy == "latest_longest":
            # 최신 기사 중 가장 긴 본문 선택
            # 1단계: 최신 기사들 찾기
            dates = [(idx, self._get_published_at(news_items[idx])) for idx in indices]
            # None인 경우 가장 오래된 날짜로 처리
            min_datetime = datetime.min.replace(tzinfo=timezone.utc)
            dates.sort(key=lambda x: x[1] or min_datetime, reverse=True)
            latest_date = dates[0][1] if dates else None

            # 최신 기사들만 필터링
            latest_indices = [idx for idx, date in dates if date == latest_date]

            # 2단계: 최신 기사 중 가장 긴 본문 선택
            if len(latest_indices) == 1:
                return latest_indices[0]

            best_idx = latest_indices[0]
            best_length = news_items[best_idx].get("content_length", 0)

            for idx in latest_indices[1:]:
                length = news_items[idx].get("content_length", 0)
                if length > best_length:
                    best_length = length
                    best_idx = idx

            return best_idx

        else:
            # 기본값: 첫 번째 기사
            logger.warning(f"Unknown strategy: {strategy}, using first item")
            return indices[0]

    def _get_published_at(self, news_item):
        """뉴스 항목에서 published_at 추출"""
        published_at = news_item.get("published_at")
        if isinstance(published_at, datetime):
            return published_at
        elif published_at is None:
            return None
        else:
            # 문자열 등 다른 형식은 None 반환 (나중에 확장 가능)
            return None
