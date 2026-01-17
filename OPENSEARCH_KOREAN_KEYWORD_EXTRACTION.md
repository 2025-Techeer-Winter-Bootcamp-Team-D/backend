# OpenSearch 한국어 키워드 추출 가이드

OpenSearch에서 의미 있는 키워드(기업명, 기술명, 산업 키워드 등)를 추출하기 위한 방법들을 정리합니다.

---

## 1. OpenSearch Nori 형태소 분석기에서 불용어(stopwords) 설정 방법

### 1.1 nori_part_of_speech 필터를 통한 불용어 제거

한국어에서 문법적 역할을 하는 조사, 접속사, 동사 등을 제거하여 의미 있는 명사 중심의 토큰을 추출합니다.

```json
PUT /korean_index
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "korean_analyzer": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": [
              "korean_pos_filter",
              "lowercase"
            ]
          }
        },
        "tokenizer": {
          "nori_tokenizer": {
            "type": "nori_tokenizer",
            "decompound_mode": "mixed",
            "discard_punctuation": true
          }
        },
        "filter": {
          "korean_pos_filter": {
            "type": "nori_part_of_speech",
            "stoptags": [
              "E",       "IC",      "J",
              "MAG",     "MAJ",     "MM",
              "SP",      "SSC",     "SSO",
              "SC",      "SE",
              "XPN",     "XSA",     "XSN",     "XSV",
              "UNA",     "NA",      "VSV"
            ]
          }
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "korean_analyzer"
      }
    }
  }
}
```

### 1.2 품사 태그 설명

| 태그 | 의미 | 제거 권장 |
|------|------|----------|
| E | 조사 | ✓ |
| J | 접미사 | ✓ |
| MAG, MAJ | 부사 | ✓ |
| VV, VA | 동사/형용사 원형 | ✓ |
| XPN, XSA, XSN, XSV | 접사 | ✓ |
| NNG, NNP | 일반/고유 명사 | ✗ |
| NNB | 의존 명사 | △ |

### 1.3 분석 테스트

```bash
POST /korean_index/_analyze
{
  "analyzer": "korean_analyzer",
  "text": "삼성전자가 인공지능半导体 기술을 개발하고 있습니다"
}
```

---

## 2. OpenSearch에서 복합명사(noun-phrase) 추출 방법

### 2.1 Decompound Mode 설정

복합명사를 적절히 분리하거나 유지하는 설정입니다.

```json
PUT /company_index
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "company_analyzer": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": ["lowercase"]
          }
        },
        "tokenizer": {
          "nori_tokenizer": {
            "type": "nori_tokenizer",
            "decompound_mode": "mixed"
          }
        }
      }
    }
  }
}
```

### 2.2 Decompound Mode 옵션

| 모드 | 설명 | 예시 |
|------|------|------|
| `none` | 분해하지 않음 | 가곡역 → 가곡역 |
| `discard` | 분해하고 원형 제거 (기본값) | 가곡역 → 가곡, 역 |
| `mixed` | 분해하고 원형 유지 | 가곡역 → 가곡역, 가곡, 역 |

### 2.3 복합명사 추출을 위한 custom analyzer

```json
PUT /news_index
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "keyword_analyzer": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": [
              "noun_compound_filter",
              "korean_pos_filter",
              "lowercase"
            ]
          }
        },
        "tokenizer": {
          "nori_tokenizer": {
            "type": "nori_tokenizer",
            "decompound_mode": "mixed"
          }
        },
        "filter": {
          "korean_pos_filter": {
            "type": "nori_part_of_speech",
            "stoptags": ["E", "J", "MAG", "XPN", "XSA", "XSN", "XSV"]
          }
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "company_name": {
        "type": "text",
        "analyzer": "keyword_analyzer",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "industry": {
        "type": "text",
        "analyzer": "keyword_analyzer"
      }
    }
  }
}
```

---

## 3. OpenSearch significant_terms 집계 사용법

### 3.1 기본 significant_terms 집계

특정 조건에서 자주 등장하는 키워드를 자동으로 발견합니다.

```json
GET /news/_search
{
  "size": 0,
  "query": {
    "match": {
      "content": "반도체"
    }
  },
  "aggs": {
    "significant_keywords": {
      "significant_terms": {
        "field": "content",
        "size": 20,
        "background_filter": {
          "match_all": {}
        }
      }
    }
  }
}
```

### 3.2 특정 기간/카테고리 대비 키워드 추출

```json
GET /news/_search
{
  "size": 0,
  "query": {
    "range": {
      "date": {
        "gte": "2024-01-01",
        "lte": "2024-12-31"
      }
    }
  },
  "aggs": {
    "tech_keywords": {
      "significant_terms": {
        "field": "content",
        "size": 30,
        "background_filter": {
          "range": {
            "date": {
              "lt": "2024-01-01"
            }
          }
        },
        "min_doc_count": 5,
        "shard_min_doc_count": 3
      }
    },
    "company_keywords": {
      "significant_terms": {
        "field": "company_name.keyword",
        "size": 10
      }
    }
  }
}
```

### 3.3 significant_text 집계 (원문 텍스트용)

```json
GET /news/_search
{
  "size": 0,
  "aggs": {
    "important_terms": {
      "significant_text": {
        "field": "content",
        "size": 50,
        "filter_duplicate_text": true
      }
    }
  }
}
```

### 3.4 집계 결과 예시

```json
{
  "aggregations": {
    "significant_keywords": {
      "doc_count": 150,
      "bg_count": 10000,
      "buckets": [
        {
          "key": "삼성전자",
          "doc_count": 45,
          "bg_count": 500,
          "score": 8.5,
          "key_hash": 12345
        },
        {
          "key": "AI 반도체",
          "doc_count": 30,
          "bg_count": 200,
          "score": 12.3,
          "key_hash": 67890
        }
      ]
    }
  }
}
```

---

## 4. OpenSearch 분석기에 사용자 사전(user dictionary) 추가 방법

### 4.1 사용자 사전 파일 생성

```bash
# config/analysis/user_dictionary.txt 생성
$ cat > config/analysis/user_dictionary.txt << 'EOF'
삼성전자,삼성,전자,NNG
LG에너지솔루션,LG,에너지솔루션,NNG
SK하이닉스,SK,하이닉스,NNG
현대자동차,현대,자동차,NNG
인공지능,인공지능,NNG
반도체,반도체,NNG
플라스틱,플라스틱,NNG
정유,정유,NNG
EOF
```

### 4.2 사용자 사전이 적용된 analyzer 생성

```json
PUT /tech_index
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "custom_korean_analyzer": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": [
              "korean_pos_filter",
              "lowercase"
            ]
          }
        },
        "tokenizer": {
          "nori_tokenizer": {
            "type": "nori_tokenizer",
            "decompound_mode": "mixed",
            "user_dictionary": "analysis/user_dictionary.txt",
            "user_dictionary_rules": [
              "삼성전자 > 삼성, 전자",
              "LG에너지솔루션 > LG, 에너지솔루션",
              "SK하이닉스 > SK, 하이닉스"
            ]
          }
        },
        "filter": {
          "korean_pos_filter": {
            "type": "nori_part_of_speech",
            "stoptags": ["E", "J", "MAG", "XPN", "XSA", "XSN", "XSV"]
          }
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "tech_name": {
        "type": "text",
        "analyzer": "custom_korean_analyzer"
      }
    }
  }
}
```

### 4.3 AWS OpenSearch Service용 커스텀 패키지

```json
POST _package/upload
{
  "package_source": {
    "location": {
      "s3": {
        "bucket_name": "my-bucket",
        "key": "packages/user_dictionary.txt"
      }
    }
  },
  "package_name": "korean_dictionary",
  "package_type": "TXT-DICTIONARY"
}

POST _package/associate
{
  "package_id": "korean_dictionary",
  "domain_name": "my-domain"
}
```

### 4.4 사용자 사전 형식

```text
# 형식: 단어 > 토큰화결과, 품사
삼성전자 > 삼성/NNG, 전자/NNG
인공지능 > 인공지능/NNG

# 복합명사 예시
서울특별시 > 서울/NNG, 특별시/NNG
삼성갤러리 > 삼성/NNG, 갤러리/NNG
```

---

## 5. OpenSearch ingest-attachment 프로세서 활용법

### 5.1 ingest-attachment 플러그인 설치

```bash
./bin/opensearch-plugin install ingest-attachment
```

### 5.2 파이프라인 생성

```json
PUT /_ingest/pipeline/attachment_pipeline
{
  "description": "Extract text from attachments",
  "processors": [
    {
      "attachment": {
        "field": "base64_content",
        "target_field": "attachment",
        "indexed_chars": 100000,
        "ignore_missing": true
      }
    },
    {
      "set": {
        "field": "extracted_text",
        "copy_from": "attachment.content"
      }
    },
    {
      "nori_part_of_speech": {
        "field": "extracted_text",
        "target_field": "keywords",
        "stoptags": ["E", "J", "MAG", "XPN", "XSA", "XSN", "XSV"]
      }
    }
  ]
}
```

### 5.3 문서 색인 파이프라인 적용

```json
PUT /documents
{
  "settings": {
    "default_pipeline": "attachment_pipeline"
  },
  "mappings": {
    "properties": {
      "base64_content": {
        "type": "binary"
      },
      "attachment": {
        "type": "object",
        "properties": {
          "content": {
            "type": "text"
          },
          "title": {
            "type": "text"
          },
          "author": {
            "type": "keyword"
          }
        }
      },
      "extracted_text": {
        "type": "text",
        "analyzer": "nori_analyzer"
      }
    }
  }
}
```

### 5.4 Python으로 base64 인코딩 및 색인

```python
import base64
from opensearchpy import OpenSearch

client = OpenSearch([{'host': 'localhost', 'port': 9200}])

def index_document(file_path, metadata):
    with open(file_path, 'rb') as f:
        base64_content = base64.b64encode(f.read()).decode('utf-8')
    
    doc = {
        'base64_content': base64_content,
        'file_name': metadata['file_name'],
        'upload_date': metadata['upload_date']
    }
    
    client.index(
        index='documents',
        body=doc,
        refresh=True
    )
```

### 5.5 지원 형식

- PDF
- Microsoft Office (DOC, DOCX, XLS, XLSX, PPT, PPTX)
- RTF
- ODF
- HTML
- XML
- JSON
- Plain text

---

## 6. 한국어 키워드 추출을 위한 OpenSearch 최적화 설정

### 6.1 종합적인 키워드 추출 analyzer

```json
PUT /keyword_extraction_index
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "keyword_extractor": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": [
              "noun_only_filter",
              "compound_keep_filter",
              "lowercase"
            ]
          },
          "search_analyzer": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": [
              "noun_only_filter",
              "lowercase"
            ]
          }
        },
        "tokenizer": {
          "nori_tokenizer": {
            "type": "nori_tokenizer",
            "decompound_mode": "mixed",
            "user_dictionary": "analysis/company_dictionary.txt",
            "user_dictionary_rules": [
              "삼성전자 > 삼성/NNG, 전자/NNG",
              "SK하이닉스 > SK/NNG, 하이닉스/NNG",
              "LG에너지솔루션 > LG/NNG, 에너지솔루션/NNG",
              "현대자동차 > 현대/NNG, 자동차/NNG"
            ]
          }
        },
        "filter": {
          "noun_only_filter": {
            "type": "nori_part_of_speech",
            "stoptags": [
              "E", "IC", "J",
              "MAG", "MAJ", "MM",
              "SP", "SSC", "SSO", "SC", "SE",
              "XPN", "XSA", "XSN", "XSV",
              "UNA", "NA", "VSV",
              "VV", "VA", "VX"
            ]
          },
          "compound_keep_filter": {
            "type": "keep",
            "keywords": [
              "반도체",
              "인공지능",
              "플라스틱",
              "정유",
              "에너지"
            ]
          }
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "keyword_extractor",
        "search_analyzer": "search_analyzer"
      },
      "content": {
        "type": "text",
        "analyzer": "keyword_extractor",
        "search_analyzer": "search_analyzer"
      },
      "company_names": {
        "type": "text",
        "analyzer": "keyword_extractor"
      },
      "industry_keywords": {
        "type": "text",
        "analyzer": "keyword_extractor"
      }
    }
  }
}
```

### 6.2 동의어 사전 설정

```json
PUT /keyword_extraction_index
{
  "settings": {
    "index": {
      "analysis": {
        "filter": {
          "korean_synonym": {
            "type": "synonym",
            "synonyms": [
              "AI, 인공지능, 머신러닝",
              "반도체, 칩, semiconductor",
              "배터리,电池, battery",
              "전기차, EV, 전기차량"
            ]
          }
        }
      }
    }
  }
}
```

### 6.3 키워드 추출 파이프라인 (전체 예시)

```json
PUT /_ingest/pipeline/keyword_extraction_pipeline
{
  "description": "Extract keywords from Korean text",
  "processors": [
    {
      "attachment": {
        "field": "base64_content",
        "target_field": "attachment",
        "indexed_chars": 50000,
        "ignore_missing": true
      }
    },
    {
      "set": {
        "field": "text",
        "copy_from": "attachment.content",
        "ignore_failure": true
      }
    },
    {
      "nori_part_of_speech": {
        "field": "text",
        "target_field": "raw_keywords",
        "stoptags": ["E", "J", "MAG", "XPN", "XSA", "XSN", "XSV", "VV", "VA"]
      }
    },
    {
      "set": {
        "field": "extracted_keywords",
        "value": "{{_ingest.on_failure_message}}"
      }
    }
  ],
  "on_failure": [
    {
      "set": {
        "field": "extracted_keywords",
        "value": "[]"
      }
    }
  ]
}
```

### 6.4 자동 키워드 색인을 위한 문서 처리

```json
POST /news/_doc?pipeline=keyword_extraction_pipeline
{
  "title": "삼성전자, AI 반도체 투자 확대",
  "content": "삼성전자가 인공지능 반도체를 위한 투자를 확대합니다. 이번 투자는 10조원 규모로, 국내 반도체 산업에 큰 영향을 미칠 것으로 예상됩니다.",
  "company": "삼성전자",
  "industry": "반도체"
}
```

### 6.5 성능 최적화 설정

```json
PUT /keyword_extraction_index
{
  "settings": {
    "index": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "analysis": {
        "analyzer": {
          "keyword_extractor": {
            "type": "custom",
            "tokenizer": "nori_tokenizer",
            "filter": ["noun_only_filter"]
          }
        }
      }
    },
    "index.refresh_interval": "30s",
    "index.translog.flush_threshold_ops": 5000
  },
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "keyword_extractor",
        "norms": false,
        "index_options": "positions"
      }
    }
  }
}
```

---

## 7. 키워드 추출 쿼리 예시

### 7.1 특정 산업 키워드 검색

```json
GET /news/_search
{
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": "반도체 인공지능"
          }
        }
      ],
      "filter": [
        {
          "terms": {
            "industry.keyword": ["반도체", "IT", "전자"]
          }
        }
      ]
    }
  },
  "aggs": {
    "top_companies": {
      "terms": {
        "field": "company.keyword",
        "size": 10
      }
    },
    "keyword_trends": {
      "significant_terms": {
        "field": "content",
        "size": 30
      }
    }
  }
}
```

### 7.2 키워드 기반 자동 태깅

```json
POST /news/_search
{
  "size": 0,
  "aggs": {
    "tech_keywords": {
      "significant_terms": {
        "field": "content",
        "size": 50,
        "min_doc_count": 10
      }
    },
    "company_names": {
      "terms": {
        "field": "company.keyword",
        "size": 20
      }
    }
  }
}
```

---

## 8. 참고 자료

- [OpenSearch Nori Analyzer Documentation](https://opensearch.org/docs/latest/analyzers/tokenizers/nori-tokenizer/)
- [OpenSearch Significant Terms Aggregation](https://docs.opensearch.org/latest/aggregations/bucket/significant-terms/)
- [OpenSearch Ingest Attachment Plugin](https://docs.opensearch.org/latest/install-and-configure/additional-plugins/ingest-attachment-plugin/)
- [Lucene Nori Tokenizer](https://lucene.apache.org/core/9_0_0/analysis/nori/org/apache/lucene/analysis/ko/KoreanTokenizer.html)

---

이 가이드를 통해 OpenSearch에서 한국어 텍스트의 의미 있는 키워드를 효과적으로 추출하고 분석할 수 있습니다.
