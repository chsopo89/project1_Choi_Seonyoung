# 네트워크 장애 대응 Assistant용 로컬 LLM 선정

네트워크 장비 장애 대응 질의에 쓸 로컬 LLM을 고르려고 Ollama로 3개 모델을 같은 조건에서 돌려 비교했다. 문항 10개는 실무에서 직접 겪은 장애 사례에서 가져왔다.

작성자: 최선영

---

## 결과 요약

10문항을 3회씩, 총 90건을 5축 루브릭(v2.1, 15점 만점)으로 채점했다.

| 모델 | 총점 | A 사실 | B 불확실성 | C 밀도 | D 단서 | E 지시 | n |
|---|---|---|---|---|---|---|---|
| qwen3:8b | 6.77 | 0.27 | 0.90 | 1.80 | 0.80 | 3.00 | 30 |
| llama3.1:8b | 3.90 | 0.77 | 0.23 | 0.30 | 0.17 | 2.43 | 30 |
| gemma3:4b | 3.53 | 0.00 | 1.00 | 1.00 | 0.43 | 1.10 | 30 |

qwen3:8b를 골랐다. 다만 사실 정확도(A축)가 세 모델 모두 3점 만점에 1점도 안 되게 나왔다. 상대적으로 제일 낫다는 뜻이지 지금 상태로 실무에 넣어도 된다는 뜻은 아니다.

Cloud 쪽은 공통 5문항을 한 번씩 돌렸고 gpt-5.6-luna 14.0점, gemini-3.6-flash 11.8점이었다. 같은 문항에서 로컬 1위가 7.40점이니 격차가 두 배 가까이 난다.

---

## 실험 환경

| 항목 | 값 |
|---|---|
| OS | Windows 11 (NT 10.0.26200) |
| Python | 3.12.7 (uv) |
| Ollama | 0.34.1 |
| 주요 패키지 | ollama 0.6.2, openai 3.8.0, google-genai 2.24.0 |
| RAM | 약 31.4 GB |
| GPU | NVIDIA RTX 5060 Laptop, 8,151 MiB |

세 모델 다 Q4_K_M 양자화를 썼고 실험 context는 8,192(num_ctx)로 맞췄다.

---

## 설치

```powershell
uv sync
```

Ollama를 먼저 깔고 모델을 받아 둔다.

```powershell
ollama pull qwen3:8b
ollama pull llama3.1:8b
ollama pull gemma3:4b
```

Cloud 실행에는 API 키가 필요하다. 환경변수로 넣고 저장소에는 올리지 않는다.

---

## 실행 순서

### 1. 로컬 벤치마크

```powershell
python 04.ollama_test.py
```

10문항을 3회씩 세 모델에 돌린다. 결과는 `benchmark_local_v2.csv`, 응답 원문은 `responses/`에 쌓인다. 생성 조건은 temperature 1.0, num_predict 8192, num_ctx 8192이고 seed는 42에 회차를 더해 43·44·45를 쓴다. qwen3:8b만 thinking을 껐다(`think=False`).

### 2. 벤치마크 집계

```powershell
python 05.report.py            # 마지막 세션
python 05.report.py all        # 전체 세션
python 05.report.py 0916-1644  # 특정 세션
```

모델별 지표와 문제별 표, 회차 편차, 이상 행이 콘솔에 찍힌다.

<<<<<<< HEAD
> `05.report.py`의 `CSV_PATH`가 `benchmark_log.csv`로 박혀 있다. 이 실험 파일명은 `benchmark_local_v2.csv`라서 돌리기 전에 상수를 고쳐야 한다.

### 3. Cloud 실행

```powershell
python 08.gemini_chat.py   # gemini-3.6-flash
python 02_luna_chat.py     # gpt-5.6-luna
```

공통 5문항(q03, q06, q07, q09, q10)을 한 번씩 돌린다. 시스템 지시문과 질문 문구는 로컬과 같다. 결과는 `benchmark_gemini.csv`와 `benchmark_luna.csv`, 원문은 `responses_gemini/`, `responses_luna/`에 들어간다.

### 4. Cloud 집계 (luna)

```powershell
python 06.report.luna.py            # 마지막 세션
python 06.report.luna.py all        # 전체 세션
```

`benchmark_luna.csv`를 읽어 요약과 문제별 집계, 회차별 원자료를 뽑는다. 단가(입력 $0.20, 출력 $1.20 per 1M 토큰)가 상수로 들어 있어서 합계와 호출당 평균, 1,000회 환산 비용까지 같이 계산한다. 보고서에 적은 비용 추정치가 여기서 나온 값이다.

### 5. 채점 집계

```powershell
python 07.scoring.py --summary
```

`scores_v2_t1.csv`에서 모델별 총점과 축별 평균, 플래그를 집계한다.

### 6. 채점 병합 (1회성)

Cloud 채점 결과를 기존 파일에 합칠 때 쓴 스크립트다. 순서대로 돌렸고 단계마다 백업을 남겼다.

| 순서 | 스크립트 | 역할 |
|---|---|---|
| 1 | `09.add_gemini_scores.py` | gemini 점수·근거 25행 추가 |
| 2 | `10.normalize_flags.py` | 플래그 값을 1/0에서 Y/빈칸으로 통일 |
| 3 | `11.merge_luna_scores.py` | `scores_luna_v2_t1.csv` 25행 병합, q03 D축 재판정 반영 |

---

## 파일 구성

### 스크립트

| 파일 | 역할 |
|---|---|
| `04.ollama_test.py` | 로컬 벤치마크 수집 |
| `05.report.py` | 로컬 벤치마크 집계 |
| `06.report.luna.py` | luna 집계와 비용 계산 |
| `07.scoring.py` | 채점 집계 |
| `08.gemini_chat.py` | gemini-3.6-flash 실행 |
| `02_luna_chat.py` | gpt-5.6-luna 실행 |
| `09~11.*.py` | 채점 병합 (1회성) |
| `answer_keys.py` | 문항별 정답 키 |
| `verified_commands.json` | 명령어 검증 목록 |

`01_ollama_chat.py`와 `03_measure_time.py`는 수업에서 받은 예제라 이 실험에는 쓰지 않았다.

### 데이터

| 파일 | 내용 |
|---|---|
| `benchmark_local_v2.csv` | 로컬 90건 측정 결과 |
| `benchmark_gemini.csv`, `benchmark_luna.csv` | Cloud 각 5건 |
| `scores_v2_t1.csv` | 채점 결과 505행 (로컬 450, Cloud 50, q10 D축 재입력 5) |
| `scores_luna_v2_t1.csv` | luna 독립 채점 원본 |
| `answers_q01~q10.md` | 문항별 응답 모음 |
| `responses/`, `responses_gemini/`, `responses_luna/` | 응답 원문 |

---

## 채점 기준 (루브릭 v2.1)

5개 축을 각각 0~3점으로 매기고 더한다.

| 축 | 내용 |
|---|---|
| A | 사실 정확성. 제시한 명령과 설정이 문서에서 확인되는지 |
| B | 불확실성 처리. 확인이 필요한 항목과 확인 방법을 밝히는지 |
| C | 정보 밀도. 상황에 맞는 내용인지 일반론인지 |
| D | 단서 활용. 질문에 나온 단서를 쓰는지, 이미 배제된 걸 다시 확인하지는 않는지 |
| E | 지시 준수. 형식과 분량(3000자), 언어 |

판정에서 자주 걸린 지점은 이렇다.

- A축 2점은 미확인이 하나 이상 있되 틀린 게 없는 상태다.
- 공식 문서에도 웹 검색에도 안 나오는 명령이나 메시지는 틀린 것으로 봤다.
- 동작을 설명한 문장은 검색 결과가 없다는 것만으로 틀렸다고 하기 어려워 미확인으로 뒀다.

---

## 알려진 제약

평가셋이 10문항뿐이라 점수 차이를 그대로 믿기는 어렵다. temperature를 1.0으로 뒀으니 돌릴 때마다 결과도 달라진다. 실제로 같은 문항 3회 총점이 qwen3:8b와 llama3.1:8b는 최대 4점까지 벌어졌다. gemma3:4b는 1점 안에서 움직였는데, 잘해서가 아니라 매번 비슷하게 못했기 때문이다.

Cloud는 5문항을 한 번씩만 돌려서 분산 자체가 없고, 로컬 3회 평균과 반복 수가 달라 나란히 놓고 보기에 무리가 있다. 두 Cloud 스크립트 모두 추론 토큰 수를 화면에만 찍고 CSV에는 안 남긴다. 다시 돌릴 일이 있으면 열을 추가해야 한다.

`benchmark_local_v2.csv`의 `위험명령어` 열은 검출 로직이 두 단어짜리 표현을 전부 걸러내는 바람에 거의 다 Y가 찍혔다. 쓰지 않는 게 낫다. 같은 파일의 로딩 시간(0.002~0.007초)도 워밍업 뒤에 잰 값이라 콜드 로딩이 아니다. 콜드 로딩은 따로 측정했다.

---

## 재현할 때

API 키와 조직 ID, 프로젝트 ID는 코드에도 저장소에도 로그에도 남기지 않는다. 콘솔 화면을 캡처할 일이 있으면 키 일부와 프로젝트 ID를 가린다.

`scores_v2_t1.csv.bak_*` 백업과 `.venv`, `__pycache__`는 커밋 대상이 아니다.

채점 파일이 꼬이면 백업에서 되돌린다.

```powershell
Copy-Item <백업파일> .\scores_v2_t1.csv -Force
```
=======
실행 파일 안의 `QUESTION` 한 줄을 바꾸고 **Ctrl+S**로 저장하면 다른 질문을 보낼 수 있습니다. 이 파일들은 대화 기록을 유지하지 않고, 매번 질문 1개를 새로 보냅니다.
=======
