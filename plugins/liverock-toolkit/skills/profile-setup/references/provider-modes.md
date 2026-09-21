# provider·mode·thinking 스냅샷

프로필의 `provider`, `model`, `modeId`, `thinkingOptionId`, `featureValues`를 정할 때 읽는다.

**이 문서의 값은 실조회 스냅샷이며 낡는다.** Paseo가 provider와 모델을 추가·제거하면 값이
달라진다. 실제 등록 직전에는 아래 MCP 도구로 다시 조회하고, 조회 결과와 이 문서가 다르면
**조회 결과를 쓴다.**

이 플러그인은 codex를 전제로 쓴다. 다만 활성 provider 구성은 사용자마다 다르므로, codex 외의
provider가 조회되면 배제하지 않고 아래 「codex 밖의 provider」 규칙으로 다룬다.

## 실시간 조회

| 도구 | 얻는 값 |
| --- | --- |
| MCP `list_providers` | provider 목록, 활성 여부, `defaultMode` |
| MCP `inspect_provider` | 한 provider의 `modes[].id`, `features[].id` |
| MCP `list_models` | 모델 ID, 모델별 `thinkingOptions[].id` |

`modeId`·`thinkingOptionId`·`featureValues`는 위 MCP나 CLI 조회로 해당 값이 확인될 때만
프로필 JSON에 넣는다. 확인되지 않으면 키 자체를 생략한다. 빈 문자열·null·`"default"` 어느
것도 남기지 않는다.

### CLI로는 mode 전체 목록을 얻을 수 없다

원리적 한계다. mode 목록을 주는 CLI 명령 자체가 존재하지 않는다.

| 명령 | 주는 것 | mode 목록 |
| --- | --- | --- |
| `paseo provider ls --json` | provider 목록, `defaultMode` **하나** | ✗ 기본값 하나뿐 |
| `paseo provider models <provider> --json` | 모델 ID, `thinkingOptionIds` | ✗ 없음 |
| `paseo provider diagnostic --json` | 설치 여부, PATH, 버전 | ✗ 없음 |

MCP를 쓸 수 없는 상황이면 CLI가 주는 것은 `defaultMode` 하나뿐이다. 그것이 `modes[].id`에
있는 값인지 확인할 수 없으면 프로필 JSON의 `modeId`는 생략한다. 이 문서의 다른 mode는
실시간으로 확인하지 못했다는 사실을 사용자에게 알린다.

## codex의 mode

| provider | 실조회로 확인된 `modeId` |
| --- | --- |
| `codex` | `auto` `auto-review` `full-access` |

- **표를 값의 출처로 쓰지 않는다.** 등록 직전에 `inspect_provider`로 `modes[].id`를 받아
  거기 있는 값만 쓴다. 표와 다르면 조회 결과가 이긴다.
- `defaultMode`는 `list_providers`가 함께 돌려주므로 거기서 읽는다. 추측해 적지 않는다.
- `scripts/manage_profiles.py`의 검증용 스냅샷 상수 `KNOWN_MODE_IDS`에도 codex의 세 값이
  들어 있다. 여기 없는 provider는 `defaultMode`가 아닌 모든 값에 `MODE_UNVERIFIED`
  **경고**를 받는다. 차단은 아니므로 `--apply`는 통과한다.

### 권한 등급 대응

| 권한 등급 | codex |
| --- | --- |
| 읽기·확인 | `auto` |
| 파일 작성 | `auto-review` |
| 명령 전권 | `full-access` |

- codex `full-access`는 **네트워크 접근과 무제한 실행**을 준다. 외부 호출이 핵심 동작인
  프로필에만 붙인다. 여덟 역할 세트에서는 `literature-search` 하나이고, 등록 전에 사용자에게
  알리고 확인받는다. 조사·검색처럼 읽기만 하는 프로필에는 쓰기 권한도 기본으로 주지 않는다.
- 계획만 내고 파일 산출까지 막는 mode는 어느 역할에도 쓰지 않는다. 결과를 파일로 받아야 하는
  역할이 그 mode에 걸리면 결과 자체가 나오지 않는다.

### codex 밖의 provider

조회 결과에 codex가 아닌 provider가 나오는 것은 정상이다. 표에 없다는 이유로 후보에서 빼지
않고, `inspect_provider`로 그 provider의 `modes[].id`를 받아 같은 방식으로 대응시킨다. 가장
제약이 큰 것을 읽기·확인에, 가장 제약이 없는 것을 명령 전권에 놓는다. mode가 하나뿐이면 세
등급 모두 그 값이 된다. 이름만으로 뜻이 분명하지 않으면 사용자에게 확인한다.

**`modes[].id`가 빈 배열이면 `modeId` 키 자체를 생략한다.** 빈 문자열도 null도 `"default"`도
안 된다. `defaultMode`를 세 등급에 채워 넣지도 않는다. `modes[].id`가 비어 있는데
`create_agent`에 `modeId`를 넣으면 기동이 실패한다. mode가 하나뿐인 경우와는 다르다 —
하나뿐이면 `modes[].id`에 그 값이라도 있지만, 이 경우는 목록 자체가 비어 있다.

`thinkingOptionId`는 이때도 전달된다. `create_agent`에 값을 주면 `effectiveThinkingOptionId`로
적용되고, 생략하면 provider 기본값이 적용된다. 다른 provider에서 쓰던 값을 그대로 옮기지
않는다. 스킬·MCP·로그인처럼 프로필에 없는 값은 그 CLI 자체 설정에 있으므로, 프로필로 흉내
내려 하지 말고 설정 위치를 사용자에게 안내한다.

## 모델별 thinking 옵션

`thinkingOptionId`의 유효 값은 **provider가 아니라 모델 단위로 다르다.** 같은 provider 안에서도
모델이 바뀌면 지원 목록이 달라지고, codex의 최상위 값은 `ultra`다.

**실제 값은 `list_models`가 돌려준 `thinkingOptions`로 정한다.** 표시명(`Sonnet 5` 같은 이름)과
실제 모델 ID는 다를 수 있으므로, 프로필에는 반드시 `list_models`가 돌려준 **ID**를 넣는다.

### 함정 — 옵션이 빈 배열인 모델

**`thinkingOptions`가 빈 배열인 모델에는 `thinkingOptionId`를 넣지 않는다. 필드 자체를
생략한다.** 빈 문자열도 `off`도 안 된다. 그 모델에는 유효한 값이 하나도 없다. 빈 배열은 목록이
있는 것이 아니라 **선언이 없는 것**으로 다룬다. `scripts/manage_profiles.py`는 이때
`THINKING_UNVERIFIED` 경고로 통과시키지만, 대조되지 않았을 뿐 그 모델이 값을 지원한다는 뜻은
아니다. 그 모델이 역할의 등급을 지원한다고 판정하지도 않는다.

목록이 있는데 거기 없는 값을 넣으면 **경고가 아니라 오류(`THINKING`)로 막힌다.** 오류가
하나라도 있으면 `--apply`가 프로필 전체를 쓰지 않는다. `max`나 `xhigh`처럼 모델마다 있고 없고가
갈리는 값, 다른 provider의 최상위 값(`ultracode`)을 codex 모델에 넣는 것이 여기 해당한다.

모델 후보를 여럿 두고 그중 하나를 고르는 방식으로 프로필을 만들 때는, **고른 모델의
`thinkingOptions`를 다시 확인한 뒤** 값을 정한다. 다른 후보에 쓰려던 값을 그대로 옮기지 않는다.

### 성능 등급 판정

조회 결과에 처음 보는 모델이 나오는 것은 정상이다. 새 모델이 추가되었거나 이 문서를 쓸 때 없던
provider가 활성화된 경우다. **처음 본다는 이유로 후보에서 빼지 않는다.** 등급은 목록에 실린
이름이 아니라 조회 결과로 정하며, 규칙은 이렇다.

**1. provider 안에서 사고 상한으로 정렬한다.** 상한은 그 모델의 `thinkingOptions` 중 가장 높은
값이고, 높낮이는 이 순서다.

```text
(빈 배열) < off < low < medium < high < xhigh < max < ultra
```

상한이 같으면 `list_models`가 돌려준 순서를 유지한다.

**2. 정렬 결과의 자리로 등급을 준다.**

| provider의 모델 수 | 고성능 | 중급 | 저성능 |
| --- | --- | --- | --- |
| 3개 이상 | 1위 | 2위 | 최하위 |
| 2개 | 1위 | 1위 | 2위 |
| 1개 | 그 모델 | 그 모델 | 그 모델 |

등급은 **provider 안에서의 상대 순위**다. provider마다 따로 매긴다. 후보가 하나뿐이라 여덟
역할이 같은 모델을 쓰게 되는 것은 실패가 아니라 이 환경의 정상 상태다.

**3. 갈리지 않으면 묻는다.** 사고 상한이 같은 모델이 여럿이고 반환 순서로도 우열을 정할 수
없으면 **추측하지 말고 사용자에게 어느 등급으로 둘지 묻는다.**

**4. 역할의 thinking 등급은 이 판정으로 바뀌지 않는다.** 등급은 모델이 아니라 역할에 붙는다.
고른 모델의 `thinkingOptions`가 역할의 등급을 지원하지 않으면 그 후보를 「충족 실패」로 표시하고
다른 조회 모델을 찾는다. 값을 임의로 낮추지 않는다. 조회된 어떤 후보도 그 등급을 지원하지
않으면, 한 단계 낮춘 값과 근거를 사용자에게 제시하고 **승인받은 경우에만** 낮춘다. `ultra`는
사용자가 명시적으로 요청할 때만 쓴다.

## featureValues

provider·모델별 토글 스위치 모음이다. 값은 `{ "<feature id>": <bool> }` 형태다.

**같은 값을 부르는 이름이 두 곳에서 다르다.**

| 위치 | 키 이름 |
| --- | --- |
| 프로필 (`config.json`의 `daemon.agentProfiles[]`) | `featureValues` |
| MCP `create_agent` | `settings.features` |

- feature 집합은 **모델마다 다르다.** 같은 provider라도 모델이 바뀌면 다시 확인한다. 근거는
  `inspect_provider`가 돌려준 `features[].id`다. 목록에 없는 id는 `featureValues`에 넣지
  않는다. 키 자체를 생략한다.
- 기본은 아무것도 넣지 않는 것이다. `fast_mode` 같은 토글은 사용자가 요청할 때만 존재를
  확인하고 추가한다.
- Paseo CLI(`paseo run`, `paseo agent update`)에는 feature 관련 플래그가 **없다.** feature를
  지정해 에이전트를 띄워야 하면 MCP `create_agent`의 `settings.features`를 쓴다.
- **이름이 비슷해도 같은 기능이라고 가정하지 않는다.** codex의 `auto-review`는 승인 자동화처럼
  보이지만 **feature가 아니라 `modeId`**이고, 승인을 건너뛰는 게 아니라 리뷰 서브에이전트로
  우회하는 것이다. 뜻이 같다고 가정하지 말고 `features[].id`로 그 provider·모델에 실제로 있는
  기능인지 먼저 확인한다.
