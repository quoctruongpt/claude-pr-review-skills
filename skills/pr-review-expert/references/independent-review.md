# Review độc lập: Codex + Claude + Breaker

Ba reviewer, context sạch, chạy song song và chạy nền. Người review chính làm
tiếp bước 3–8 trong lúc chờ, gộp kết quả ở bước 9.

| Reviewer | Công cụ | Quyền | Bắt được |
|---|---|---|---|
| Codex | `codex exec -s read-only` | chỉ đọc | lỗi logic, error path, góc nhìn model khác |
| Claude | Agent tool, `subagent_type: general-purpose`, chạy nền | chỉ đọc (dặn trong prompt) | lỗi logic, concurrency, lifecycle |
| Breaker | Agent tool, `subagent_type: breaker`, chạy nền | viết/chạy test tạm trong worktree | chứng minh vỡ thật: race, replay, cấp quyền trùng |

Breaker chỉ chạy khi bước 0 cho phép chạy code (PR nội bộ, hoặc user đồng ý).

## Hai chế độ

| | Review PR người khác (`pr-review-expert`) | Tự review thay đổi của mình (mục "Review code" trong CLAUDE.md) |
|---|---|---|
| Thư mục | `$WT` (worktree của PR) | repo hiện tại |
| Danh sách file | `ocr delegate preview --format json --from origin/$BASE --to HEAD` | `ocr delegate preview --format json` |
| Diff | `git --no-pager diff --no-color origin/$BASE...HEAD -- <path>` | `git --no-pager diff --no-color HEAD -- <path>` (file mới chưa track: đọc cả file) |
| Quy ước commit của user | không áp lên PR, review theo quy ước repo | áp dụng |

## Bước 1: chia file bằng OCR

```bash
ocr delegate preview --format json --from origin/$BASE --to HEAD > $W/ocr-preview.json
jq -r '.reviewable_files[].path' $W/ocr-preview.json > $W/review-files.txt
ocr delegate rule --format json $(cat $W/review-files.txt) > $W/ocr-rules.json
```

OCR loại file test, generated, lock theo mặc định (`excluded_files` ghi lý do). File test do người review chính đọc ở bước 8b. `ocr` không chạy được → dùng danh sách file non-generated từ `$W/surface.json`, ghi "OCR lỗi: <lỗi>" vào báo cáo.

## Bước 2: prompt chung

Cả Codex và Claude nhận cùng một prompt (thay `<...>`):

```text
Bạn review code độc lập, context sạch. CHỈ ĐỌC: không sửa file, không chạy lệnh ghi, không cài package, không gọi mạng.

Repo: <$WT hoặc repo hiện tại>. Stack: <stack từ bước 0>.
Dải diff: <origin/$BASE...HEAD | working tree so với HEAD>.
File cần review (mỗi file một lần, ghi reviewed/skipped kèm lý do):
<nội dung $W/review-files.txt>
Rule theo file (từ OCR): <tóm tắt $W/ocr-rules.json, hoặc "không có">.
Mô tả thay đổi / rủi ro tác giả khẳng định: <tóm tắt mô tả PR>.
Điểm nóng cần soi: <causal watch và file LINE-BY-LINE từ router bước 2>.

Lấy diff từng file bằng: git --no-pager diff --no-color <dải diff> -- "<path>"
Đọc code xung quanh khi cần (caller, callee, model, config).

Tìm: lỗi logic, sai dữ liệu, bảo mật khai thác được, authorization theo resource, race/idempotency, error path, lifecycle
(React unmount, Flutter dispose/mounted, Unity OnDestroy, goroutine/Task không kết thúc), breaking change với caller ngoài diff
và app mobile bản cũ. Bỏ qua style và thứ linter bắt được.

Mỗi finding, đúng định dạng:
- file:line bên new (dòng bị xóa: ghi "old:<line>")
- severity: BLOCKER | MAJOR | MINOR
- vỡ khi nào: input/trạng thái X → kết quả Y sai
- bằng chứng: đoạn code liên quan
- sửa: một câu
Không có bằng chứng cụ thể thì không báo. Cuối cùng liệt kê file reviewed/skipped.
```

## Bước 3: chạy

**Codex** (Bash, `run_in_background: true`):

```bash
codex exec -s read-only -C "$WT" --ephemeral -o $W/codex.md - < $W/review-prompt.txt
```

Lưu prompt vào `$W/review-prompt.txt` trước. Codex lỗi (chưa login, hết quota) → ghi lại, không coi là pass.

**Claude** (Agent tool): `subagent_type: general-purpose`, `run_in_background: true`, prompt như trên. Nhắc subagent không dùng Edit/Write.

**Breaker** (Agent tool): `subagent_type: breaker`, `run_in_background: true`. Prompt gồm:

- Worktree `$WT` là nơi duy nhất được làm việc, dải diff `origin/$BASE...HEAD`; checkout của user không được đụng.
- Stack và lệnh chạy test của repo (từ `references/stack-checks.md` § Test).
- Tóm tắt thay đổi, rủi ro tác giả khẳng định, causal watch và finding đáng ngờ từ bước 2–6, làm hướng tấn công ưu tiên (tối đa 5).
- Có được cài dependency không (mặc định: chỉ khi đã có sẵn `node_modules`/`.dart_tool`/`vendor`; không thì `--ignore-scripts` hoặc ghi PLAUSIBLE).
- Không dùng `.env`/config/DB/Redis/API thật.

## Bước 4: gộp (ở bước 9 của skill)

Đọc `$W/codex.md` và kết quả hai agent. Gộp finding trùng; finding một nguồn → tự mở code kiểm lại. Trước khi xóa worktree: `git -C $WT status --porcelain` phải sạch (không còn file `zz_breaker_*`).
