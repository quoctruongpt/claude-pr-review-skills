<!-- PR_REVIEW_START -->
## Review code

Khi user nhờ review thay đổi của chính họ (working tree, branch chưa thành PR), hoặc trước khi báo xong một thay đổi lớn đụng payment/IAP/auth/API/schema:

1. Tự đọc diff (`git diff HEAD`, file mới chưa track thì đọc cả file) và soi theo `~/.claude/skills/pr-review-expert/references/stack-checks.md` (chỉ mục của stack có trong diff).
2. Thay đổi rủi ro cao: chạy review độc lập theo `~/.claude/skills/pr-review-expert/references/independent-review.md`, cột "Tự review" — Codex (`codex exec -s read-only`) + subagent Claude chỉ đọc, song song, chạy nền; thêm agent `breaker` khi cần chứng minh lỗi tiền/quyền. Gộp kết quả, finding một nguồn thì tự kiểm lại.
3. Báo cáo theo mức BẮT BUỘC SỬA / NÊN SỬA / GỢI Ý, mỗi finding có `file:line` và "vỡ khi nào".

Review PR/MR của người khác: dùng skill `pr-review-expert`.

Điều hướng code: repo có `.codegraph/` thì dùng CodeGraph trước; không có thì dùng `srcwalk` (TS/JS, Go, C#, PHP); Dart dùng `rg`.
<!-- PR_REVIEW_END -->
