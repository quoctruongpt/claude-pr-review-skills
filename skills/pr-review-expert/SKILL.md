---
name: pr-review-expert
description: Quy trình review PR/MR của người khác cho dev full stack (TypeScript/Node, React Native, Dart/Flutter, C#/.NET, Unity, PHP/Laravel, Go) — blast radius, bảo mật, test, breaking change (gồm app mobile bản cũ còn gọi API), hiệu năng, đối chiếu issue/spec, code smell, review độc lập Codex + Claude + Breaker (test phá chạy thật), rồi gate phạm vi để chỉ chặn trên lỗi PR này gây ra (lỗi có sẵn xuống phụ lục). Dùng khi user nhờ review PR/MR hoặc dán link PR, nhất là PR đụng shared package, API, DB schema, payment/IAP/entitlement, auth. Review thay đổi của chính mình chạy theo mục "Review code" trong ~/.claude/CLAUDE.md.
---

# PR Review Expert

Adapted từ alirezarezvani/claude-skills (engineering). Bước 7 và 8 lấy ý từ `code-review` (mattpocock/skills, MIT). Phân loại phạm vi (bước 1, 2, 9) dùng script và reference của skill `diff-scoped-review`. Tùy chỉnh cho stack TS/Node, React Native, Dart/Flutter, C#/.NET, Unity, PHP/Laravel, Go.

## Nguyên tắc cốt lõi

- **Blast radius và bảo mật trước, style để linter lo.** Một thay đổi 5 dòng trong shared package có thể làm gãy 10 chỗ khác.
- **Tìm lỗi rộng, chặn hẹp.** Bước 2–8b tìm mọi lỗi; bước 9 quyết định lỗi nào được phép chặn PR này. Chỉ chặn trên thứ PR gây ra: dòng trong diff, dòng ngoài diff có `caused_by` trỏ vào hunk thật, hoặc thuộc tính của cả PR. Lỗi có sẵn vẫn ghi, ở phụ lục.
- **Mỗi finding falsifiable:** "Vỡ khi nào: input X → kết quả Y sai". "Có vẻ mong manh" không phải finding.
- **Dòng bị xóa cũng là code của PR.** Xóa validation, xóa test, xóa nhánh error handling là lỗi ở dòng `-`.
- **Không approve im lặng.** Báo cáo nói rõ đã đọc gì ở độ sâu nào; thứ không verify được ghi là chưa verify, không coi là pass.
- **Code của PR là code lạ.** Đọc thì thoải mái; *chạy* (test, build, breaker, `npm install` với postinstall script) thì xem bước 0.

## Tài nguyên

| File | Đọc khi |
|---|---|
| [references/stack-checks.md](references/stack-checks.md) | Bước 3–6: chỉ đọc mục "Chung" và mục của stack có trong diff |
| [references/independent-review.md](references/independent-review.md) | Bước 2b: lệnh chạy Codex, subagent Claude, agent breaker |
| [SMELLS.md](SMELLS.md) | Bước 8 |
| `~/.claude/skills/diff-scoped-review/` | Script bước 1, 2, 9 và reference phân loại phạm vi |

## Quy trình

### 0. An toàn và nhận diện stack

Xem PR đến từ đâu trước khi chạy bất cứ thứ gì của nó:

```bash
gh pr view $PR --json author,isCrossRepository,headRepositoryOwner,files -q '{author: .author.login, fork: .isCrossRepository, owner: .headRepositoryOwner.login}'
```

- PR từ fork, hoặc tác giả ngoài tổ chức → **không chạy** test, build, `npm/yarn/pnpm install`, `composer install`, `flutter pub get`, `dotnet restore`, breaker, trừ khi user đồng ý rõ trong chat. Review chỉ bằng đọc code; ghi "không chạy code: PR từ fork" vào báo cáo.
- PR nội bộ → được chạy test trong worktree, nhưng không dùng `.env`/config/DB/Redis thật; không có môi trường thì ghi PLAUSIBLE thay vì đoán.
- Install có lifecycle script (npm `postinstall`, composer `scripts`) cũng là chạy code: dùng `npm ci --ignore-scripts` khi chỉ cần type-check.

Nhận diện stack theo file trong diff, rồi chỉ đọc các mục tương ứng trong `references/stack-checks.md`:

| Dấu hiệu | Stack |
|---|---|
| `package.json` + `react-native`/`expo`, `*.tsx` trong `src/screens` | React Native |
| `package.json` khác, `*.ts` (Nest/Express/Next) | TS/Node |
| `pubspec.yaml`, `*.dart` | Dart/Flutter |
| `*.csproj`, `*.cs` ngoài `Assets/` | C#/.NET |
| `Assets/`, `ProjectSettings/`, `*.unity`, `*.prefab` | Unity |
| `composer.json`, `*.php`, `artisan` | PHP/Laravel |
| `go.mod`, `*.go` | Go |

### 1. Lấy context, checkout, dựng review surface

```bash
PR=123
W=/tmp/pr-$PR; mkdir -p $W
DSR=~/.claude/skills/diff-scoped-review/scripts

gh pr view $PR --json title,body,labels,milestone,assignees | jq .
BASE=$(gh pr view $PR --json baseRefName -q .baseRefName)

# Lấy code PR vào worktree riêng (detached): không đụng checkout và thay đổi dở của user
GH_CRED='credential.helper=!gh auth git-credential'   # git HTTPS báo "Repository not found" → mượn credential của gh, không đổi config
git -c credential.helper= -c "$GH_CRED" fetch origin "$BASE" "pull/$PR/head:refs/remotes/origin/pr-$PR"
WT=$W/wt; git worktree add --detach $WT refs/remotes/origin/pr-$PR
cd $WT                            # mọi bước sau chạy ở đây
# Xong review: git worktree remove $WT

# Diff BA chấm (từ merge base) — khớp với diff GitHub hiển thị
git diff --no-color -M origin/$BASE...HEAD > $W/pr.diff

# Review surface: ground truth dòng nào added/removed, thuộc hunk nào, file nào generated
python3 $DSR/diff_surface_builder.py --diff $W/pr.diff --keep-text --output json --out $W/surface.json
python3 $DSR/diff_surface_builder.py --diff $W/pr.diff

# Dòng thêm/xóa kèm anchor path:line:text (bỏ file generated) — input cho bước 3–6
python3 - $W/surface.json $W <<'PY'
import json, sys
files = json.load(open(sys.argv[1]))["files"]
with open(sys.argv[2] + "/added.txt", "w") as a, open(sys.argv[2] + "/removed.txt", "w") as r:
    for f in files:
        if f["generated"]:
            continue
        for n, t in zip(f["added_lines"], f["added_text"]):
            a.write(f'{f["path"]}:{n}:{t}\n')
        for n, t in zip(f["removed_lines"], f["removed_text"]):
            r.write(f'{f["path"]}:{n}:{t}\n')
PY
```

GitLab: `glab mr view <IID> --output json`, base lấy từ `target_branch`, ref là `merge-requests/<IID>/head`; các lệnh còn lại giữ nguyên.

Hai chấm (`origin/$BASE..HEAD`) sai: commit mới trên base hiện ra như phần bị xóa. Chi tiết: `diff-scoped-review/references/unified_diff_anatomy.md`.

File coi là generated (bỏ đọc dòng, chỉ xét *vì sao* đổi): lock file (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lock`, `pubspec.lock`, `Podfile.lock`, `composer.lock`, `go.sum`, `packages.lock.json`), codegen (`*.g.dart`, `*.freezed.dart`, `*.mocks.dart`, `*.Designer.cs`, `*ModelSnapshot.cs`, `*.pb.go`, `*_gen.go`), Unity serialized (`*.meta`, `*.unity`, `*.prefab`, `*.asset`, `*.mat`, `*.anim`, `*.controller`), `*.pbxproj`. Migration không bao giờ là generated. Với Unity scene/prefab: vẫn mở diff khi PR đổi script có `[SerializeField]`, để xem reference trong scene có bị mất (`m_Script`/`fileID: 0`) không.

### 2. Thứ tự đọc, causal watch, blast radius

```bash
python3 $DSR/diff_risk_router.py --surface $W/surface.json
```

Router trả về:

- **Thứ tự đọc:** `LINE-BY-LINE` (money/IAP/auth/webhook/migration) → `FOCUSED` (native config & permission, API contract, async, cache) → `SCAN` → `SKIP-LINES`. Router chấm theo tên đường dẫn, không hiểu code: file mà blast radius bên dưới xếp CRITICAL/HIGH thì đọc từng dòng dù router xếp `SCAN`.
- **`pull in:`** — agent/skill nên gọi thêm (`breaker (agent)`, `migration`, `ui-ux-pro-max`); ghi lại cho mục "Bước tiếp theo".
- **Causal watch** — dòng trong diff có thể làm vỡ code ngoài diff (SIGNATURE-CHANGED, EXPORT-REMOVED, GUARD-REMOVED, DEFAULT-CHANGED, ENUM-VARIANT-ADDED). Router in sẵn lệnh `find:`. GUARD-REMOVED và ENUM phải trace tay: input nào trước bị guard chặn giờ đi tới đâu; mọi `switch`/`match` trên enum rơi vào `default` fail-open hay fail-closed. Danh mục đủ 10 kiểu: `diff-scoped-review/references/diff_caused_breakage.md`.

Đo blast radius cho mỗi file và symbol thay đổi bằng `srcwalk` (TS/JS, Go, C#, PHP; chạy `srcwalk guide` một lần nếu chưa quen). **Dart chưa được srcwalk hỗ trợ → dùng `rg`.**

```bash
srcwalk deps <file-thay-đổi>              # ai import file này
srcwalk trace callers <SymbolĐãĐổi>       # ai gọi trực tiếp
srcwalk review origin/$BASE..HEAD         # Flow Map của các symbol đã đổi

# Sweep bằng rg: bắt chỗ trace bỏ sót (gọi bằng string, reflection, DI token, config)
rg -w -l 'ChangedSymbol' -g '*.{ts,tsx,js,dart,cs,php,go}'
rg -n "[\"']ChangedSymbol[\"']"           # SendMessage/Invoke (Unity), route/container (Laravel), DI token (Nest)
rg -l "from ['\"].*changed-module['\"]|import .*changed_module" -g '*.{ts,tsx,dart}'
```

Ngoài code trong repo, blast radius còn gồm thứ không grep được:

- **API dùng bởi app mobile:** bản RN/Flutter/Unity cũ trên máy user vẫn gọi contract cũ hàng tháng sau khi merge. Đổi/xóa field, đổi kiểu, thêm field bắt buộc ở request → coi là CRITICAL trừ khi có versioning hoặc force-update.
- **Package dùng chung** (npm workspace, Go module, NuGet, pub package, composer package): caller ở repo khác.
- **OTA update** (EAS Update/CodePush/Shorebird): JS/Dart mới chạy trên native binary cũ → gọi native module/permission chưa có là crash.

Phân loại mức độ:
- **CRITICAL** — shared package, model/schema DB, middleware auth, contract API mà app mobile đã phát hành gọi, payment/IAP/webhook
- **HIGH** — service dùng bởi >3 nơi khác, config chung, env var, native config/permission (AndroidManifest, Info.plist, entitlements)
- **MEDIUM** — thay đổi nội bộ 1 service/1 màn hình, hàm tiện ích
- **LOW** — file test, docs

Bước này xong khi mọi dòng `rg` tìm ra đã được phân loại, và mọi causal watch đã đóng: hoặc thành finding có `caused_by: <path>:H<n>`, hoặc thành một dòng trong mục "Đã kiểm tra" của báo cáo.

### 2b. Review độc lập: Codex + Claude + Breaker (chạy nền)

Grep ở bước 3–6 chỉ bắt pattern; lỗi logic, concurrency, error path, lifecycle (unmount/dispose/OnDestroy) cần reviewer đọc code thật.

- **Bắt buộc** khi blast radius CRITICAL/HIGH, hoặc PR đụng payment/IAP/entitlement/auth.
- **Bỏ qua** khi MEDIUM/LOW và diff nhỏ; ghi "bỏ qua review độc lập: <lý do>" vào báo cáo.

Chạy theo [references/independent-review.md](references/independent-review.md), dải diff `origin/$BASE...HEAD`, thư mục `$WT`. Breaker chỉ chạy khi bước 0 cho phép chạy code. Khởi chạy ngay rồi làm tiếp bước 3–8 trong lúc chờ; dùng kết quả ở bước 8b và gộp ở bước 9.

### 3. Quét bảo mật

Chạy khối **Chung** và khối của từng stack có trong diff ở `references/stack-checks.md` § Bảo mật, trên `$W/added.txt` (mỗi dòng khớp đã có anchor `path:line`). Mỗi dòng khớp là *gợi ý đọc*, chưa phải finding: mở code, xác nhận input có thật sự đến từ client không.

Route/endpoint mới nằm ngoài nhóm có auth → mọi giới hạn theo `userId` do client gửi đều bị vượt bằng cách đổi `userId`; xét quota, rate limit, chi phí gọi LLM/dịch vụ ngoài theo giả định đó. Với app mobile: mọi thứ trong bundle (API key, endpoint ẩn, cờ premium kiểm ở client) coi như public.

### 4. Test

```bash
CHANGED=$(git diff --name-only origin/$BASE...HEAD)
TEST_RE='(\.test\.|\.spec\.|\.e2e\.|_test\.dart$|_test\.go$|Tests?\.cs$|Test\.php$|(^|/)(__tests__|test|tests|integration_test)/|/Tests/(EditMode|PlayMode)/)'
CHANGED_SRC=$(echo "$CHANGED" | grep -vE "$TEST_RE")
CHANGED_TESTS=$(echo "$CHANGED" | grep -E "$TEST_RE")
echo "File nguồn thay đổi: $(echo "$CHANGED_SRC" | grep -c .)"
echo "File test thay đổi:  $(echo "$CHANGED_TESTS" | grep -c .)"

# Test case bị xóa (side old)
grep -E "$TEST_RE" $W/removed.txt | grep -E "\b(it|test|describe|testWidgets|group)\(|func Test|\[(Test|Fact|Theory|UnityTest)\]|function test|@test"
```

Lệnh chạy test theo stack: `references/stack-checks.md` § Test. Chỉ chạy khi bước 0 cho phép; chỉ ghi coverage % khi đã đo thật.

Quy tắc: function/method/component/widget mới có logic không có test → flag. Xóa test mà không xóa code liên quan → flag. Luồng payment/IAP/entitlement/auth → cần test cả nhánh lỗi, không chỉ happy path. Router báo `NO-TEST-CHANGE` → finding `scope: pr-level`. Đọc nội dung file test để ở bước 8b.

### 5. Breaking change

Chạy khối **Chung** và khối stack ở `references/stack-checks.md` § Breaking change trên `$W/removed.txt` và `$W/added.txt`: route/endpoint bị xóa hoặc đổi, field DTO/response đổi, migration thiếu đường rollback hoặc khóa bảng, env var/config mới hoặc bị xóa, permission native mới, bump minimum SDK/OS, đổi serialized field (Unity), đổi key local storage/schema DB local (mobile).

Migration chưa chạy ở đâu (tác giả ghi trong test plan) → mục PR-LEVEL nếu code mới phụ thuộc cột/index đó mà không có đường chạy khi thiếu.

### 6. Tác động hiệu năng

Chạy khối stack ở `references/stack-checks.md` § Hiệu năng: N+1 query, render lại thừa (RN/Flutter), allocation trong `Update()` (Unity), goroutine/Task/Promise không có điểm kết thúc, dữ liệu client kiểm soát kích thước đi vào cache/DB không TTL, dependency mới nặng (bundle size app).

Với mỗi lệnh ghi cache/Redis: giá trị lớn tới đâu, ai quyết định kích thước, key có TTL không, và chỗ nào ghi lại key đó.

### 7. Đối chiếu với issue/spec gốc

Code sạch mà làm sai yêu cầu vẫn là PR hỏng, và các bước 2–6 không bắt được loại này. Tìm spec theo thứ tự: issue được nhắc trong commit/mô tả PR (`Refs #N`, `Closes #N`, link Jira/Linear) → file spec/design doc trong repo → hỏi user. Không có spec thì ghi "không có spec để đối chiếu", không coi là đã pass.

```bash
gh pr view $PR --json body,closingIssuesReferences | jq .
gh issue view <N> --comments
```

Báo cáo ba loại, mỗi finding trích đúng dòng spec:

- Yêu cầu trong spec bị thiếu hoặc làm dở.
- Hành vi trong diff mà spec không yêu cầu (scope creep).
- Yêu cầu có implement nhưng implement sai.

PR có UI: đối chiếu thêm với design (Figma link trong PR/issue) nếu có; sai lệch giao diện ghi ở đây, không trộn với finding kỹ thuật.

Giữ phần này tách riêng trong báo cáo, không xếp hạng chung với finding kỹ thuật: PR có thể qua một trục mà trượt trục kia.

### 8. Code smell (luôn là nhận định, không bao giờ là BẮT BUỘC SỬA)

Chỉ soi trên dòng diff thêm/sửa, đối chiếu từng mục trong [SMELLS.md](SMELLS.md). Quy ước của repo thắng danh sách này; bỏ qua thứ linter/analyzer đã bắt (ESLint, `dart analyze`, Roslyn analyzers, PHPStan/Pint, `go vet`/golangci-lint). Ghi kiểu "có thể là Feature Envy" kèm hunk, xếp vào GỢI Ý.

### 8b. Review file test (sau khi đã biết rủi ro của code)

Đọc test cuối cùng, khi đã có danh sách rủi ro từ bước 2–8 và kết quả bước 2b: câu hỏi là "test có bảo vệ đúng chỗ rủi ro không". Codex/Claude ở bước 2b thường không đọc file test, nên bước này do chính người review làm. Không soi bảo mật/hiệu năng/style trong file test.

- Mỗi finding BẮT BUỘC/NÊN SỬA đã có: có test nào lẽ ra bắt được không? Không có → ghi vào finding ("không test nào bắt được"); test có mà vẫn pass → test sai, thêm finding.
- Hành vi rủi ro tác giả khẳng định trong mô tả PR (idempotent, quota tính một lần, restore purchase không cấp trùng): có test assert đúng điều đó, hay chỉ chạy qua không lỗi?
- Mock/stub có che mất đúng chỗ dễ vỡ không (vd mock repo luôn trả lỗi duplicate nên không test được insert thật; mock IAP luôn trả `purchased`)?
- Assertion nào bị nới hoặc xóa ở dòng `-` (`side: old`)? Snapshot test bị cập nhật hàng loạt (`-u`) mà không ai nhìn?
- Test phụ thuộc thời gian, thứ tự, mạng thật, `pumpAndSettle` với animation vô hạn, `Task.Delay`/`setTimeout`, hay build tag/category không chạy trong CI?

### 9. Gộp kết quả, gate phạm vi, ra verdict

**Gộp.** Nếu bước 2b đã chạy: đọc kết quả Codex, Claude và Breaker, gộp với finding từ bước 2–8b, gộp finding trùng. Finding chỉ một nguồn báo → tự mở code kiểm lại, ghi rõ giữ hay bác bỏ và lý do. Một reviewer lỗi (`codex` không chạy, subagent fail) → ghi rõ bên nào thiếu, không coi là đã qua.

Kết quả Breaker map như sau:

- CONFIRMED → finding có bằng chứng chạy thật; đưa lệnh repro vào finding. Vẫn mở code kiểm lại test có đúng giả định không (fake có mô phỏng đúng WHERE/guard thật không).
- PLAUSIBLE → finding một nguồn, kiểm lại như trên; chưa kiểm được thì vào "CHƯA VERIFY ĐƯỢC".
- REFUTED → dòng trong "ĐÃ KIỂM TRA". Breaker chỉ trả lời "hành vi có xảy ra không"; khi nó ghi REFUTED vì "rủi ro tác giả đã chấp nhận" mà hành vi vẫn xảy ra, mức độ do bước này quyết định theo bảng dưới.

**Giả định runtime.** Mỗi lần giữ, bác bỏ hay hạ mức một finding vì một khẳng định về prod — bản app nào còn gọi endpoint, gateway/CDN giới hạn body/rate gì, feature flag/remote config đang bật hay tắt, migration đã chạy chưa, bao nhiêu user còn ở bản cũ — thì kiểm ở nguồn sống: log/APM, analytics theo app version, Firebase Remote Config/LaunchDarkly, config prod, bảng migration. Mô tả PR, spec và memory là giả thuyết, chưa phải bằng chứng. Ghi nguồn cạnh finding (vd "log API 13/10: app 2.3.x vẫn gọi /v1/profile"). Chưa kiểm được → finding giữ mức như thể giả định sai, và giả định vào mục "CHƯA VERIFY ĐƯỢC" kèm cách kiểm.

**Xếp mức.** Mức nói bug nghiêm trọng tới đâu, chưa nói PR nào phải trả:

| Mức | Severity cho gate | Khi nào |
|---|---|---|
| BẮT BUỘC SỬA | `BLOCKER` | sai dữ liệu, lỗ hổng bảo mật khai thác được, gãy caller đã xác định ở bước 2 (kể cả app mobile bản cũ), mất tiền hoặc entitlement, crash khi mở app/màn hình chính, migration không rollback được |
| NÊN SỬA | `MAJOR` | lỗi ở edge case/error path, thiếu test cho luồng rủi ro, hiệu năng xấu đi đo/suy ra được, memory leak |
| GỢI Ý | `MINOR` / `NIT` (smell) | đặt tên, cấu trúc, code smell; không bao giờ chặn |

**Lỗi nằm sau feature flag/remote config đang tắt** (chỉ xảy ra khi bật cờ, mặc định tắt): xếp `MINOR` cho gate, vì merge không làm nó xảy ra. Ghi thêm vào mục "ĐIỀU KIỆN TRƯỚC KHI BẬT CỜ" với mức thật của nó. Cờ mặc định bật, hoặc đã bật trên prod, thì xếp như lỗi thường.

**Gắn anchor rồi gate.** Ghi mọi finding kỹ thuật vào `$W/findings.json` theo schema (`python3 $DSR/finding_scope_gate.py --print-schema`; ví dụ: `diff-scoped-review/assets/example_findings.json`). Mỗi finding có đúng một kiểu anchor:

- `file` + `line` — dòng thêm; thêm `"side": "old"` khi nói về dòng bị xóa.
- `file` + `line` + `caused_by: "<path>:H<n>"` — dòng ngoài diff mà hunk đó làm vỡ.
- `"scope": "pr-level"` — thuộc tính cả PR (thiếu test đường retry, migration không rollback, mô tả PR lệch diff).

Mở đầu `claim` bằng nguồn: `[grep]`, `[Codex]`, `[Claude]`, `[Breaker]`, `[causal watch]`. Finding đối chiếu spec (bước 7) không đưa vào gate.

```bash
python3 $DSR/finding_scope_gate.py --findings $W/findings.json --surface $W/surface.json
```

- Exit `0` APPROVE / APPROVE-WITH-NITS · `1` REQUEST-CHANGES · `3` input bị từ chối (thiếu anchor, severity lạ, `caused_by` trỏ vào hunk không có) — sửa anchor rồi chạy lại; exit 3 không có verdict.
- `DIFF-ADJACENT` (dòng context hiện trong hunk) là bẫy hay sập nhất: thấy trên màn hình nhưng PR không đổi nó.
- Class phụ lục (`DIFF-ADJACENT`, `PRE-EXISTING`, `NOT-IN-PR`) không bao giờ chặn, dù severity là BLOCKER — đề xuất mở issue riêng.
- Gate cảnh báo `SCOPE DRIFT` → rà lại vì review đang trôi khỏi thay đổi thật.

Bước này xong khi gate trả exit 0 hoặc 1, mọi finding có mức và nguồn, mọi finding một nguồn đã kiểm lại, mọi giả định runtime có nguồn sống hoặc nằm trong "CHƯA VERIFY ĐƯỢC". Sau đó: kiểm `git -C $WT status --porcelain` sạch rồi `git worktree remove $WT`.

**Không tự post comment lên PR.** Gửi báo cáo cho user; chỉ post (`gh pr review`/`gh pr comment`) khi user bảo.

## Checklist đầy đủ

```markdown
### Phạm vi
- [ ] Đã kiểm nguồn PR (fork/ngoài tổ chức) trước khi chạy code
- [ ] Diff lấy bằng ba chấm từ origin/$BASE đã fetch
- [ ] Đã đối chiếu với issue/spec (và design nếu có UI), hoặc ghi rõ không có spec
- [ ] Tiêu đề/mô tả PR đúng với thay đổi thực tế; breaking change đã ghi rõ
- [ ] Verdict lấy từ gate, không có finding phụ lục nào đang chặn

### Blast radius
- [ ] Đã xác định file/service/package phụ thuộc vào thay đổi
- [ ] Đã xét app mobile bản cũ và OTA update nếu PR đổi API hoặc native
- [ ] Mọi causal watch đã đóng (finding DIFF-CAUSED hoặc dòng "Đã kiểm tra")
- [ ] Migration rollback được; env var mới có trong .env.example/appsettings mẫu
- [ ] Review độc lập (bước 2b) đã chạy, hoặc ghi rõ lý do bỏ qua
- [ ] Worktree sạch file `zz_breaker_*` trước khi remove

### Bảo mật
- [ ] Không có secret hardcode (kể cả trong app bundle, google-services, appsettings)
- [ ] Query có bind param; không nối chuỗi vào SQL/NoSQL query
- [ ] Endpoint mới có auth và authorization theo resource (không chỉ "đã login")
- [ ] Không xóa guard/validation mà không có thay thế
- [ ] Webhook/IAP mới verify chữ ký/receipt ở server và có idempotency
- [ ] Không log token, PII, receipt; không lưu token ở AsyncStorage/SharedPreferences/PlayerPrefs

### Test
- [ ] Logic mới có test; có test cho nhánh lỗi, không chỉ happy path
- [ ] Không xóa test/nới assertion mà thiếu lý do

### Breaking change
- [ ] Không xóa/đổi field API mà app mobile đang phát hành dùng, trừ khi có versioning
- [ ] Không thêm cột NOT NULL vào bảng có dữ liệu mà thiếu default/migration 2 bước
- [ ] Enum/default mới không làm nhánh default ở nơi khác fail-open
- [ ] Permission/minSdk/iOS target mới đã được nêu trong mô tả PR

### Hiệu năng
- [ ] Không có N+1 query mới; index đã thêm cho pattern query mới
- [ ] Không có render lại/allocation thừa trong đường nóng (list, Update, build)
```

## Output format

```
## PR Review: [tiêu đề] (owner/repo#số)

Verdict: REQUEST-CHANGES (từ finding_scope_gate)
Range: git diff -M origin/develop...HEAD · 6 file (5 reviewable, 1 generated) · +120 −34 · 9 hunk
Stack: TS/Node (api), React Native (app)
Blast radius: CRITICAL — đổi response GET /v1/profile, app RN 2.x đang gọi
Test: 4 file nguồn đổi, 1 file test đổi (coverage % chỉ ghi khi đã đo thật)
Review độc lập: Codex + Claude + Breaker đã chạy (hoặc: "bỏ qua: <lý do>" / "không chạy code: PR từ fork")

--- BẮT BUỘC SỬA (chặn merge) ---
1. api/src/users/users.repository.ts:42 · DIFF-CONTAINED · BLOCKER [grep, Codex]
   Nối chuỗi vào $queryRawUnsafe.
   Vỡ khi nào: id = "1 OR 1=1" → trả về mọi user.
   Sửa: dùng $queryRaw`... WHERE id = ${id}` (tagged template, có bind).

2. app/src/screens/Profile.tsx:88 · DIFF-CAUSED · BLOCKER [causal watch]
   caused_by: api/src/users/dto/profile.dto.ts:H1 — đổi `avatarUrl` thành `avatar.url`.
   Vỡ khi nào: app bản 2.x mở màn Profile → `avatarUrl` undefined → Image crash trên Android.

--- NÊN SỬA (chặn merge) ---
3. Cả PR · PR-LEVEL · MAJOR — đổi logic restore purchase nhưng không có test nhánh receipt trùng.

--- GỢI Ý (không chặn) ---
4. api/src/orders/orders.service.ts:120 — có thể là Feature Envy (code smell, bước 8)

--- ĐIỀU KIỆN TRƯỚC KHI BẬT CỜ (không chặn merge) ---
remoteConfig.newCheckout: BLOCKER — giá lấy từ client, server không kiểm (checkout.service.ts:57)

--- ĐỐI CHIẾU SPEC (#issue, tách riêng) ---
Thiếu: "hiển thị lỗi khi thẻ bị từ chối" (issue dòng 3) chưa có UI
Thừa: thêm field `discountNote` vào response, spec không yêu cầu
Sai: không có

--- NGOÀI PHẠM VI (ghi nhận, không chặn) ---
| Mục | Vị trí | Class | Severity gốc | Ghi chú |
| token lưu ở AsyncStorage | app/src/auth/storage.ts:12 | NOT-IN-PR | MAJOR | nên mở issue riêng |

--- ĐÃ KIỂM TRA ---
- profile.dto.ts — đọc từng dòng. Causal watch SIGNATURE-CHANGED: srcwalk trace callers ra 3 caller, 1 vỡ (#2).
- package-lock.json — chỉ review quyết định bump (axios 1.6.8 → 1.7.2).

--- ĐÃ BÁC BỎ ---
- Codex báo race ở orders.service.ts:60: bác bỏ, đoạn này chạy trong transaction có SELECT ... FOR UPDATE

--- CHƯA VERIFY ĐƯỢC ---
- Tỉ lệ user còn ở app 2.x: chưa xem analytics; finding #2 giữ BLOCKER. Cách kiểm: analytics theo app_version 30 ngày.
```

## Lỗi thường gặp cần tránh

Chỉ soi style mà bỏ qua blast radius và bảo mật; approve happy path mà không kiểm tra error path; quên app mobile bản cũ khi review API; chạy `npm install`/test của PR từ fork; bỏ qua rủi ro migration (NOT NULL cần default hoặc 2 bước); chặn PR vì dòng context hoặc nợ cũ; bỏ qua causal watch vì router "không báo gì" (router chỉ match text); PR quá lớn thì đề xuất tách nhỏ thay vì approve đại khái.

## Bước tiếp theo

- PR đụng payment/IAP/entitlement/webhook mà breaker chưa chạy (vì PR từ fork hoặc thiếu môi trường) → đề xuất user chạy breaker sau khi đồng ý, trước khi merge.
- Router `pull in:` nêu `migration` → gọi skill `migration` cho đúng file migration; nêu `ui-ux-pro-max` → review UI/accessibility cho file màn hình/component.
