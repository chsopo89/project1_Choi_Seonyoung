"""
문항별 정답 키 (채점 체크리스트)

- clues        : 질문에 주어진 단서 (D축 참고용, 사람이 판단)
- excluded     : 질문이 이미 배제한 조치 (문항이 정상이라고 한 대상을 다시 점검하는 것)
- contradicted : 단서와 안 맞는 원인
- facts_wrong  : 문서로 틀린 것이 확인된 설정값·사실 (A축)
- facts_check  : 틀렸을 가능성이 있어 문서 확인이 필요한 주장 (A축, 확인 후 facts_wrong으로 이동)
- risky        : 조건 없이 권하면 위험 조치 플래그 (D축이 아니라 R 플래그로만 처리)

키워드에 걸린 줄은 후보일 뿐이며 판정은 사람이 한다.
명령어 판정(ok/wrong)은 문항과 관계없이 verified_commands.json 에서 관리한다.

[변경] 2026-09-16
  - q01 facts_wrong "rekey 기본값 3600초": "3600초" 단독 키워드가
    "3600초 이상으로 설정" 같은 권고 문장까지 잡아서, 기본값을 주장하는 표현으로 좁힘

[변경] 2026-09-17 (루브릭 v2.1, 1차 채점 폐기 후 재채점)
  - D축: 배제 조치가 하나라도 있으면 0점 → 단계형 기준으로 변경
      배제 조치 = 문항이 정상이라고 한 대상을 다시 점검하는 것
      (문제 장비 쪽에서 하는 점검은 배제 조치로 보지 않음)
  - A축: 존재하지 않는 설정·기능·명령·용어를 사실처럼 제시하면 '틀린 것'으로 셈
      A_CAP_NO_COMMANDS(상한 1)는 검증할 명령·설정·사실이 하나도 없을 때만 적용
  - E축: 지시문을 되읊은 것은 감점하지 않음 (면책 문구는 B축, 분량 낭비는 C축에서 반영)
  - 글자수는 줄바꿈 정규화 기준 (read_text, CSV 응답글자수와 동일)
  - 재부팅 키워드에 "장비를 재시작", "장비 재시작" 추가 (q02 gemma r1 누락 사례)
    "서비스 재시작"은 q02 배제 조치이므로 단독 "재시작"은 넣지 않음
  - q02 risky에 "설정 초기화" 추가 (q02 gemma r2 누락 사례)
  - 초기화 계열(Factory Reset, Policy Reset, 설정 초기화)을 RESET 공통 항목으로 묶어
    모든 문항 risky에 추가 (q04 gemma r3 누락 사례). q02의 개별 항목은 RESET으로 대체
  - q04 "정책 Priority 필드"를 facts_check → facts_wrong으로 이동
    (FortiGate 방화벽 정책은 Top-down 위치 순서로만 평가, 우선순위 값 없음 — 선영 확인)
  - q04 facts_wrong에 "정책 ID로 순서 결정" 추가 (qwen r1 "Policy ID가 0", qwen r3 "정책 번호가 1")
  - 문항별 vendors 추가. 명령어 판정은 verified_commands.json에서 해당 장비 항목만 적용하고,
    다른 장비 명령으로만 등록된 경우 '다른 장비 명령(⇄)'으로 표시
    NetScreen은 ScreenOS(screenos)로, Juniper 스위치는 Junos(junos)로 구분한다
  - q03·q06·q07의 "제외 문항" 표시 삭제 (재채점은 q01~q10 전체 대상)
  - q03 facts_wrong에 "설정 변경 후 재부팅 필요" 추가 (gemma r1)
  - q06 facts_wrong에 "설정 변경 후 재부팅 필요", "시간대 설정이 NTP 동기화에 영향" 추가
  - cisco 명령 판정은 IOS(Catalyst) 기준. NX-OS 전용 명령은 wrong으로 본다 (선영 확인)
  - q07 contradicted에 "Cisco·Juniper를 한 HA 그룹으로 전제" 추가,
    facts_wrong에 "HA 우선순위를 양쪽 동일하게" 추가 (우선순위는 달라야 Active가 정해짐)
  - q08 excluded에 "협상값 일치 재확인"(PSK·proposal), contradicted에 "SA 미생성" 추가
  - reference 필드 추가 (사람 참고용, 스크립트는 사용하지 않음). q08에 선영 현장 사례 기록
  - q09 facts_wrong에 "SFP 드라이버 설치", "Advanced IP Services를 A/S 프로그램으로 설명" 추가
  - q09 reference: A/S 구조(정품=SMARTnet·구매처 통해 TAC RMA, 서드파티=판매처, TAC 지원 제한 가능) 선영 확인
  - q10 reference 추가, facts_wrong에 "STP 비활성화·포워딩 강제로 루프 해결" 추가

[변경] 2026-09-18
  - A축 이름을 "사실 정확성"에서 "정확성"으로 바꿈 (채점 화면 표시 문구만 해당, 점수·집계와 무관)
"""

RUBRIC_VERSION = "v2.1"

# 검증할 명령어·설정값·사실 주장이 하나도 없는 응답의 A축 상한. 결정 전이면 None
A_CAP_NO_COMMANDS = 1

CHAR_LIMIT = 3000

RUBRIC = {
    "A": ("정확성",
          "3: 모든 명령·설정값 문서로 확인 / 2: 미확인 1개, 틀린 것 0 / "
          "1: 틀린 것 1~2개 / 0: 틀린 것 3개 이상 또는 틀린 전제로 진단 | "
          "없는 설정·기능·명령·용어를 사실처럼 제시하면 틀린 것으로 셈 | "
          "검증 대상이 하나도 없으면 상한 1"),
    "B": ("불확실성 처리",
          "3: 확인 필요 항목 표시 + 확인 방법 / 2: 표시만 / "
          "1: 일반 면책 문구만 (지시문 되읊기 포함) / 0: 전부 단정"),
    "C": ("정보 밀도",
          "3: 모두 상황 특화 / 2: 일반론 1~2개 / 1: 일반론 절반 이상 / 0: 일반론뿐 또는 반복·붕괴"),
    "D": ("단서 활용",
          "0: 배제 조치나 단서와 모순되는 원인을 주된 해결책·결론으로 제시, 또는 단서 무시·되묻기 / "
          "1: 단서를 언급하지만 배제 조치나 모순 원인이 점검 항목에 섞임 / "
          "2: 단서로 우선순위를 정하고 배제 조치는 조건부로만 언급 / "
          "3: 2점 조건 + 단서로부터 구체적 원인 가설과 검증 방법 제시 | "
          "위험 조치는 D축이 아니라 R 플래그"),
    "E": ("지시 준수",
          "3: 3000자 이내·형식 준수·정상 종료 / 2: 사소한 위반 1건 / "
          "1: 분량 초과 또는 위반 여러 건 / 0: 잘림·언어 혼입 등 | "
          "지시문 되읊기는 감점하지 않음"),
}

# verified_commands.json의 vendor 값과 문항의 vendors 값으로 쓰는 이름 ("any"는 장비 무관)
VENDOR_NAMES = {"fortigate", "screenos", "junos", "cisco", "any"}

REBOOT = {"id": "재부팅", "keywords": ["재부팅", "리부팅", "reboot", "reload", "장비를 재시작", "장비 재시작"]}
RESET = {"id": "초기화", "keywords": ["Factory Reset", "factory reset", "factoryreset", "Factory 설정",
                                     "공장 초기화", "Policy Reset", "설정 초기화", "설정을 초기화"]}

ANSWER_KEYS = {
    # ------------------------------------------------------------ FortiGate IPsec 3초 끊김
    "q01": {
        "vendors": ["fortigate"],
        "clues": ["터널 연결·라우팅 정상", "Phase 1과 2 사이 down 로그", "3초 주기"],
        "excluded": [
            {"id": "라우팅 점검", "keywords": ["라우팅", "경로", "tracert", "traceroute"]},
        ],
        "contradicted": [
            {"id": "협상값 불일치", "keywords": ["proposal", "Proposal", "PSK", "IKE 버전", "IKEv"]},
        ],
        "facts_wrong": [
            # [변경] "3600초" 단독 → 기본값을 주장하는 표현만
            {"id": "rekey 기본값 3600초", "keywords": ["보통 3600초", "기본값은 3600초", "기본값 3600초",
                                                  "기본 3600초", "3600초(1시간)로"]},
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["변경 후 재부팅"]},
        ],
        "facts_check": [],
        "risky": [REBOOT, RESET],
    },
    # ------------------------------------------------------------ FortiGate VIP 웹만 중단
    "q02": {
        "vendors": ["fortigate"],
        "clues": ["VIP·정책 정상", "서버 정상", "방화벽→서버 SSH 정상",
                  "서버→외부 통신 정상", "웹 서비스만 안 됨 (외부→VIP 경로는 미검증)"],
        "excluded": [
            {"id": "VIP·정책 재확인", "keywords": ["VIP 설정", "VIP 매핑", "정책 설정", "방화벽 정책"]},
            {"id": "서버 점검", "keywords": ["서버 상태", "웹 서버 서비스", "httpd", "nginx", "apache", "Apache", "서비스 재시작"]},
            {"id": "방화벽↔서버 통신 확인", "keywords": ["SSH 접속", "ping"]},
        ],
        "contradicted": [
            {"id": "서버·내부 경로 문제", "keywords": ["서버가 다운", "서버 다운", "서버 장애", "내부 라우팅"]},
        ],
        "facts_wrong": [],
        "facts_check": [
            {"id": "일반 VIP 헬스 체크", "keywords": ["헬스 체크", "헬스체크", "health check", "health-check"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "세션 전체 정리", "keywords": ["session clear", "세션 초기화", "세션을 모두"]},
        ],
    },
    # ------------------------------------------------------------ FortiGate 로그 미기록
    "q03": {
        "vendors": ["fortigate"],
        "clues": ["로컬 저장·원격 전송 모두 안 됨", "로그 서버 정상", "설정·정책 정상", "ping 정상"],
        "excluded": [
            {"id": "로그 서버 점검", "keywords": ["로그 서버 상태", "로그 서버를 확인", "syslog 서버", "Syslog 서버", "ping"]},
            {"id": "로그 설정·정책 재확인", "keywords": ["로그 설정을 확인", "로그 설정 확인", "log setting", "정책을 확인"]},
        ],
        "contradicted": [
            {"id": "원격 구간만의 문제", "keywords": ["네트워크 연결 문제", "로그 서버 장애", "방화벽이 차단"]},
        ],
        "facts_wrong": [
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["재부팅하여 변경 사항을 적용", "변경 후 재부팅"]},
        ],
        "facts_check": [],
        "risky": [REBOOT, RESET],
    },
    # ------------------------------------------------------------ FortiGate 정책 미적용
    "q04": {
        "vendors": ["fortigate"],
        "clues": ["Top-down 운영", "포트 번호 재확인함", "정책을 맨 위로 올림", "다음 정책이 적용됨"],
        "excluded": [
            {"id": "포트 번호 재확인", "keywords": ["포트 번호"]},
            {"id": "정책 순서 변경", "keywords": ["맨 위로", "순서를 변경", "순서 변경", "상단으로", "위로 이동"]},
        ],
        "contradicted": [
            {"id": "순서·포트 문제", "keywords": ["포트가 잘못", "순서가 잘못"]},
        ],
        "facts_wrong": [
            {"id": "정책 Priority 필드", "keywords": ["Priority", "priority", "우선순위 필드", "우선순위 값",
                                                 "숫자가 낮을수록", "낮은 값일수록"]},
            {"id": "정책 ID로 순서 결정", "keywords": ['Policy ID"가 0', "정책 번호가 1", "정책 ID가 1"]},
        ],
        "facts_check": [],
        "risky": [
            REBOOT,
            RESET,
            {"id": "세션 전체 정리", "keywords": ["session clear", "세션 초기화", "세션을 모두", "모든 세션"]},
        ],
    },
    # ------------------------------------------------------------ Cisco HA + STP 루프
    "q05": {
        "vendors": ["cisco"],
        "clues": ["HA 구성", "STP 루프 발생", "HA 전환 안 됨", "로그에 특이사항 없음",
                  "show spanning-tree summary 이상 없음"],
        "excluded": [
            {"id": "summary 재확인", "keywords": ["spanning-tree summary"]},
            {"id": "로그 재확인", "keywords": ["로그를 확인", "로그를 다시", "로그 확인", "show logging"]},
        ],
        "contradicted": [
            {"id": "STP 설정 자체 이상", "keywords": ["STP 설정 오류", "STP 설정이 잘못"]},
        ],
        "facts_wrong": [],
        "facts_check": [],
        "risky": [
            REBOOT,
            RESET,
            {"id": "STP 비활성화", "keywords": ["no spanning-tree", "STP를 비활성화", "STP 비활성화", "spanning-tree 비활성화"]},
        ],
    },
    # ------------------------------------------------------------ Cisco NTP 한 대만 틀어짐
    "q06": {
        "vendors": ["cisco"],
        "clues": ["NTP 정상 설정", "NTP 서버 정상", "한 대만 시간이 틀어짐"],
        "excluded": [
            {"id": "NTP 서버 변경", "keywords": ["NTP 서버를 변경", "NTP 서버 변경", "다른 NTP 서버", "NTP 서버를 교체"]},
            {"id": "NTP 서버 점검", "keywords": ["NTP 서버 상태", "NTP 서버를 확인"]},
        ],
        "contradicted": [
            {"id": "NTP 서버 문제", "keywords": ["NTP 서버 문제", "NTP 서버 장애", "NTP 서버의 문제"]},
        ],
        "facts_wrong": [
            {"id": "설정 변경 후 재부팅 필요", "keywords": ["재부팅하여 설정 변경", "재부팅하여 변경 사항을 적용"]},
            {"id": "시간대 설정이 NTP 동기화에 영향", "keywords": ["UTC 시간을 사용해야", "시간대 설정은 시간 오차"]},
        ],
        "facts_check": [],
        "risky": [
            REBOOT,
            RESET,
            {"id": "수동 시간 설정", "keywords": ["clock set"]},
        ],
    },
    # ------------------------------------------------------------ Cisco–Juniper HA
    "q07": {
        "vendors": ["cisco", "junos"],
        "clues": ["Cisco·Juniper 각각 HA", "Juniper는 정상 전환", "Cisco는 Active만 꺼지고 전환 안 됨",
                  "로그에 Active off 기록만 있음"],
        "excluded": [
            {"id": "Juniper 우선 점검", "keywords": ["Juniper 스위치를 먼저", "Juniper부터", "Juniper를 먼저", "Juniper 설정을 변경"]},
        ],
        "contradicted": [
            {"id": "Juniper 측 원인", "keywords": ["Juniper 설정 문제", "Juniper 쪽 문제", "Juniper의 문제"]},
            {"id": "Cisco·Juniper를 한 HA 그룹으로 전제", "keywords": ["HA 그룹으로 구성", "Juniper 스위치와 HA를 구성",
                                                          "HA 링크", "Juniper 스위치와 일치"]},
        ],
        "facts_wrong": [
            {"id": "HA 우선순위를 양쪽 동일하게", "keywords": ["우선 순위가 동일한지", "값이 동일한지",
                                                     "우선 순위를 Juniper 스위치와 동일하게"]},
        ],
        "facts_check": [
            {"id": "HSRP–VRRP 호환 주장", "keywords": ["HSRP와 VRRP", "HSRP와 호환", "VRRP와 호환"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "강제 전환", "keywords": ["강제 전환", "강제로 전환", "force"]},
        ],
    },
    # ------------------------------------------------------------ NetScreen–FortiGate 상태 disable
    "q08": {
        "vendors": ["screenos", "fortigate"],
        "clues": ["터널 구간 통신 정상 (SA 성립)", "VPN 상태만 disable 표시"],
        "reference": [
            "모니터링 화면의 VPN 상태 표시는 Active / Inactive / Disable (선영 확인)",
            "현장 해결 사례: 1:1 터널링으로 연결해 해결. 정답 여부는 미확정 (선영)",
            "채점은 정답 일치가 아니라 단서와의 정합성(배제·모순)으로 판정",
        ],
        "excluded": [
            {"id": "협상 설정 재구성", "keywords": ["Phase 1 설정을 다시", "재구성", "proposal을 변경",
                                              "암호화 알고리즘을 변경", "암호화 알고리즘 변경"]},
            {"id": "협상값 일치 재확인", "keywords": ["Pre-shared Key", "프리-쉐어드 키", "정확히 일치하는지",
                                               "일치 여부 확인"]},
        ],
        "contradicted": [
            {"id": "터널 미생성·협상 실패", "keywords": ["터널이 생성되지", "터널은 생성되지", "터널 생성 실패",
                                              "협상 실패", "협상이 실패", "연결되지 않"]},
            {"id": "SA 미생성", "keywords": ["SA 생성 실패", "SAD가 생성되지", "터널 자체가 구축되지"]},
        ],
        "facts_wrong": [],
        "facts_check": [
            {"id": "FortiGate IKEv2 전용 주장", "keywords": ["IKEv2 기반", "IKEv2만", "IKEv2를 사용하므로"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "터널 삭제·재생성", "keywords": ["터널을 삭제", "삭제 후 재생성", "재생성"]},
        ],
    },
    # ------------------------------------------------------------ Cisco SFP 미인식 / A/S
    "q09": {
        "vendors": ["cisco"],
        "clues": ["광 SFP 미인식", "Cisco 정품 확인됨", "정품 A/S 방식", "서드파티 A/S 방식"],
        "reference": [
            "정품: 장비 유지보수 계약(SMARTnet)이나 구매처·총판을 통해 TAC 케이스 → RMA 교체 (선영 확인)",
            "서드파티: 판매처 A/S. Cisco TAC는 정품으로 교체 후 재현을 요구하거나 지원을 제한할 수 있음 (선영 확인)",
        ],
        "excluded": [
            {"id": "정품 여부 확인", "keywords": ["정품 여부", "정품인지", "위조", "가품"]},
        ],
        "contradicted": [
            {"id": "비정품 원인", "keywords": ["서드파티 모듈이기 때문", "비정품이기 때문", "정품이 아니"]},
        ],
        "facts_wrong": [
            {"id": "SFP 드라이버 설치", "keywords": ["드라이버를 다운", "드라이버를 업그레이드", "드라이버를 다운로드"]},
            {"id": "Advanced IP Services를 A/S 프로그램으로 설명", "keywords": ["A/S (Advanced IP Services)"]},
        ],
        "facts_check": [
            {"id": "A/S 프로그램 명칭", "keywords": ["Replacement Program", "교체 프로그램"]},
            {"id": "보증 기간 주장", "keywords": ["평생 보증", "lifetime", "Lifetime", "보증 기간"]},
        ],
        "risky": [
            {"id": "미지원 모듈 강제 인식", "keywords": ["unsupported-transceiver", "gbic-invalid"]},
            REBOOT,
            RESET,
        ],
    },
    # ------------------------------------------------------------ Cisco→Juniper 이전
    "q10": {
        "vendors": ["cisco", "junos"],
        "clues": ["양쪽 802.1Q 트렁크·VLAN ID 동일", "링크 up·LLDP 인식", "일부 VLAN만 불통",
                  "포트 up 이후 간헐적 루프", "각 스위치 내부 통신 정상"],
        "reference": [
            "Claude 가설(미확인): native VLAN 불일치, 허용 VLAN 목록 차이, "
            "Cisco PVST+/Rapid-PVST+와 Junos RSTP 간 VLAN별 STP 불일치 → MSTP 또는 VSTP로 정렬",
            "Junos native-vlan-id: non-ELS는 unit 0 family ethernet-switching 아래, ELS는 인터페이스 아래",
        ],
        "excluded": [
            {"id": "VLAN ID 재확인", "keywords": ["VLAN ID를 확인", "VLAN ID가 일치", "VLAN ID 확인", "VLAN ID가 동일"]},
            {"id": "물리 링크 점검", "keywords": ["물리적 연결", "케이블", "링크 상태를 확인"]},
        ],
        "contradicted": [
            {"id": "링크·인식 문제", "keywords": ["링크 다운", "링크가 down", "LLDP 설정", "인식되지 않"]},
        ],
        "facts_wrong": [
            {"id": "STP 비활성화·포워딩 강제로 루프 해결", "keywords": ["STP를 비활성화하는 것을 검토",
                                                         "임시로 **포워딩** 모드", "blocking 상태**에 있는 포트가 없는지"]},
        ],
        "facts_check": [
            {"id": "Junos native VLAN 설정", "keywords": ["native-vlan", "native vlan"]},
            {"id": "STP 기본 모드 주장", "keywords": ["기본적으로 RSTP", "기본 STP", "기본값은 RSTP", "기본값은 MSTP"]},
        ],
        "risky": [
            REBOOT,
            RESET,
            {"id": "STP 비활성화", "keywords": ["no spanning-tree", "STP를 비활성화", "STP 비활성화",
                                          "spanning-tree 비활성화", "delete protocols"]},
        ],
    },
}
