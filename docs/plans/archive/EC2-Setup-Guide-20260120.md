# AWS EC2 인스턴스 생성 및 설정 가이드 (Project Tailored)

## 0. 사전 준비
*   **AWS 계정** 및 콘솔 접속 권한.
*   **SSH 키 페어**: 기존 키를 사용하거나 `backend-key.pem` 등으로 새로 생성하여 안전한 곳에 보관(`chmod 400 backend-key.pem`).
*   **VPC**: 기본 VPC를 사용하거나, 사설망 구성이 된 커스텀 VPC 사용. (본 가이드는 기본 VPC 기준)

---

## 1. 인스턴스 생성 (총 2대)

### A. Data Layer 인스턴스 (Stateful)
*데이터베이스, 검색 엔진, 캐시가 실행되는 고사양/안정성 중시 서버.*

1.  **AMI (OS)**: `Ubuntu Server 24.04 LTS (HVM)` (추천) 또는 `Amazon Linux 2023`.
2.  **인스턴스 유형**:
    *   최소: `t3.medium` (vCPU 2, RAM 4GB) - *Elasticsearch/TimescaleDB 구동을 위해 RAM 4GB 이상 필수.*
    *   권장: `t3.large` (vCPU 2, RAM 8GB) - *안정적인 운영을 위함.*
3.  **키 페어**: 준비한 키 페어 선택.
4.  **네트워크 설정**:
    *   **서브넷**: 가급적 **Private Subnet** 권장 (Public 접근 차단). *불가피하게 Public Subnet 사용 시 보안 그룹으로 철저히 제어.*
    *   **퍼블릭 IP 자동 할당**: Private Subnet이면 `비활성화`, Public Subnet이면 `활성화`.
    *   **보안 그룹 (`sg-backend-data`)** 생성:
        *   SSH (22): 내 IP에서만 허용.
        *   PostgreSQL (5432): **App Layer 인스턴스의 Private IP** (또는 보안 그룹 ID)에서만 허용.
        *   Redis (6379): **App Layer**에서만 허용.
        *   OpenSearch (9200): **App Layer**에서만 허용.
        *   Exporters (9100, 9187, 9121): **App Layer**에서만 허용.
5.  **스토리지**:
    *   최소 **30GB gp3** 이상 (DB 및 검색 로그 데이터 적재용).

### B. App Layer 인스턴스 (Stateless)
*웹 서버 및 애플리케이션 로직이 실행되는 서버.*

1.  **AMI (OS)**: `Ubuntu Server 24.04 LTS (HVM)`.
2.  **인스턴스 유형**: `t3.small` (vCPU 2, RAM 2GB) 또는 `t3.medium`.
3.  **네트워크 설정**:
    *   **서브넷**: **Public Subnet** (외부 통신 필요).
    *   **퍼블릭 IP 자동 할당**: `활성화`.
    *   **보안 그룹 (`sg-backend-app`)** 생성:
        *   SSH (22): 내 IP에서만 허용.
        *   HTTP (80): `0.0.0.0/0` (전체 허용).
        *   HTTPS (443): `0.0.0.0/0` (전체 허용).
4.  **스토리지**: 8GB ~ 20GB gp3.

---

## 2. 초기 접속 및 필수 패키지 설치 (공통)

두 인스턴스 모두 SSH로 접속하여 **Docker**와 **Docker Compose**를 설치해야 합니다.

### 접속 방법
```bash
ssh -i /path/to/key.pem ubuntu@<Public-IP>
```

### 설치 스크립트 (Ubuntu 기준)
아래 명령어를 복사하여 터미널에 붙여넣으세요.

```bash
# 1. 시스템 업데이트
sudo apt-get update && sudo apt-get upgrade -y

# 2. 필수 패키지 설치
sudo apt-get install -y ca-certificates curl gnupg git

# 3. Docker GPG 키 추가
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 4. Docker 리포지토리 추가
echo \
  "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  \"$(. /etc/os-release && echo "$VERSION_CODENAME")\" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Docker 설치
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. 권한 설정 (sudo 없이 docker 실행)
sudo usermod -aG docker $USER
newgrp docker
```

---

## 3. 메모리 스왑 설정 (중요: t3.small/medium 사용 시)

메모리 부족으로 프로세스(특히 빌드 중)가 죽는 것을 방지하기 위해 **App Layer 인스턴스**에는 스왑 메모리를 설정하는 것이 좋습니다.

```bash
# 2GB 스왑 파일 생성
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**(Data Layer 인스턴스)**: OpenSearch를 위해 가상 메모리 설정을 변경해야 합니다.
```bash
# sysctl 설정 영구 적용
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## 4. IP 확인 및 보안 그룹 갱신

인스턴스 생성이 완료되면 **Private IP**를 확인하여 보안 그룹을 상호 업데이트해야 합니다.

1.  **Data Instance의 Private IP 확인**: (예: `172.31.20.5`)
2.  **App Instance의 Private IP 확인**: (예: `172.31.10.15`)
3.  **보안 그룹 수정**:
    *   **Data Layer 보안 그룹(Inbound)**: 소스(Source)를 App Instance의 Private IP (`172.31.10.15/32`) 또는 App 보안 그룹 ID(`sg-xxxxxxx`)로 지정하여 5432, 6379, 9200 포트 개방.

이제 인스턴스 준비가 완료되었습니다! `git clone` 후 배포를 진행하세요.
