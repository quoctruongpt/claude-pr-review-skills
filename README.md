# claude-pr-review-skills

Bộ review PR cho Claude Code, tùy chỉnh cho dev full stack: TypeScript/Node, React Native, Dart/Flutter, C#/.NET, Unity, PHP/Laravel, Go.

Ý tưởng chính: **tìm lỗi rộng, chỉ chặn merge vì lỗi do chính PR gây ra.** Lỗi có sẵn vẫn ghi, ở phụ lục. Mỗi lỗi phải nói được "input X → kết quả Y sai".

## Cài

```bash
gh repo clone quoctruongpt/claude-pr-review-skills ~/claude-pr-review-skills
~/claude-pr-review-skills/install.sh
```

Cập nhật về sau:

```bash
git -C ~/claude-pr-review-skills pull && ~/claude-pr-review-skills/install.sh
```

Tham số: `--no-cli` (không cài npm CLI), `--no-claude-md` (không sửa `~/.claude/CLAUDE.md`). Chạy lại nhiều lần an toàn: skill bị ghi đè, mục CLAUDE.md được thay giữa marker `PR_REVIEW_START/END`.

Cần sẵn: `git`, `gh` (đã `gh auth login`), `python3`, `jq`, `rg`, `node`/`npm`. Tùy chọn: `codex` (đã login) cho bước review độc lập.

## Thành phần

| Thành phần | Cài vào | Vai trò |
|---|---|---|
| `skills/pr-review-expert` | `~/.claude/skills/` | Quy trình review PR 9 bước |
| `skills/diff-scoped-review` | `~/.claude/skills/` | Script: dựng review surface, xếp thứ tự đọc + causal watch, gate ra verdict |
| `agents/breaker.md` | `~/.claude/agents/` | Viết test tạm `zz_breaker_*` trong worktree để chứng minh code vỡ thật, rồi dọn |
| `claude-md/review-code.md` | nối vào `~/.claude/CLAUDE.md` | Mục "Review code": tự review thay đổi của mình |
| CLI `srcwalk`, `ocr` + skill `srcwalk` | npm global, `~/.claude/skills/srcwalk` | Tìm caller/importer; chia file cho reviewer |

## Dùng

- Review PR người khác: `review PR #123` hoặc dán link PR.
- Tự review: `review code của tôi`.

Kết quả: verdict từ gate (APPROVE / REQUEST-CHANGES), BẮT BUỘC SỬA / NÊN SỬA / GỢI Ý có `file:line`, đối chiếu spec, phụ lục lỗi cũ, mục chưa verify. Claude không tự post lên PR.

## Quy trình

0. An toàn: PR từ fork/người ngoài → chỉ đọc, không chạy test/install khi chưa được đồng ý. Nhận diện stack.
1. Worktree riêng, diff ba chấm, review surface.
2. Router xếp thứ tự đọc theo rủi ro; causal watch (đổi signature, xóa guard, thêm enum…); blast radius bằng `srcwalk`/`rg`, gồm app mobile bản cũ và OTA update.
3. (2b) Review độc lập khi rủi ro cao: Codex read-only + subagent Claude + agent breaker, chạy nền.
4. Quét bảo mật, test, breaking change, hiệu năng theo stack (`references/stack-checks.md`).
5. Đối chiếu issue/spec (và design nếu có UI).
6. Code smell (chỉ gợi ý). Review file test sau cùng.
7. Gộp, gắn anchor, `finding_scope_gate.py` ra verdict.

## Hạn chế

- `srcwalk` chưa hỗ trợ Dart → Dart dùng `rg`.
- Unity test cần Unity Editor → breaker chỉ viết test, user tự chạy.

## Nguồn

Phỏng theo `alirezarezvani/claude-skills` (engineering) và `code-review` của `mattpocock/skills` (MIT). Công cụ: [srcwalk](https://github.com/sting8k/srcwalk), [open-code-review](https://github.com/alibaba/open-code-review).
