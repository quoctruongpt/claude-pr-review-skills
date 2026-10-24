# Review — <PR title / owner/repo#N>

**Verdict:** <APPROVE | APPROVE-WITH-NITS | REQUEST-CHANGES>
**Surface:** <N> file (<R> reviewable, <G> generated/binary) · +<A> −<D> dòng · <H> hunk
**Range:** `<git diff -M main...HEAD | gh pr diff N>`

> Review này chỉ chặn trên thứ PR gây ra. Mục "Ngoài phạm vi" ở cuối là quan sát,
> không phải điều kiện merge.

---

## Chặn merge

Mỗi mục: `file:line` · class · claim · cái gì sai khi chạy thật.

### B1 — `<path>:<line>` · DIFF-CONTAINED · <BLOCKER|MAJOR>

<Một câu nói cái gì sai.>

**Vỡ khi nào:** <input/trạng thái cụ thể → kết quả sai hoặc crash. Không viết
"có thể gây vấn đề".>

**Đề xuất:** <sửa thế nào, hoặc câu hỏi cần author trả lời nếu chưa chắc.>

### B2 — `<path>:<line>` · DIFF-CAUSED · <BLOCKER|MAJOR>

**caused_by:** `<path>:H<n>` — <hunk đó đổi cái gì khiến dòng này vỡ.>

<claim>

**Vỡ khi nào:** <...>

### B3 — cả PR · PR-LEVEL · <BLOCKER|MAJOR>

<Thiếu test cho nhánh mới / migration không có rollback / mô tả PR không khớp diff.>

---

## Nit (trong phạm vi, không chặn)

- `<path>:<line>` — <một câu>. Tùy author.

---

## Ngoài phạm vi — ghi nhận, không chặn

PR này không gây ra những mục dưới đây. Để ở đây cho author quyết, hoặc mở issue riêng.

| Mục | Vị trí | Class | Severity gốc | Ghi chú |
|---|---|---|---|---|
| <claim ngắn> | `<path>:<line>` | DIFF-ADJACENT | MAJOR (demoted) | dòng context, không bị diff đổi |
| <claim ngắn> | `<path>:<line>` | NOT-IN-PR | BLOCKER (demoted) | file không nằm trong diff — nên mở issue |

---

## Đã kiểm tra và không thấy vấn đề

Phần này tránh "approve im lặng" — nói rõ đã đọc gì, để author biết chỗ nào *chưa* được đọc.

- `<path>` — đọc từng dòng (<lý do risk: money/auth/migration>). Causal watch:
  `<SIGNATURE-CHANGED grant>` → đã grep call site, <N> chỗ, tất cả đã cập nhật.
- `<path>` — scan (docs/prose).
- `<path>` — không đọc từng dòng: generated (<lý do>). Đã xác nhận bump version là cố ý.

## Chưa verify được

<Những gì không kiểm tra được và vì sao — thiếu quyền, không chạy được test, cần
dữ liệu prod. Không coi "không verify được" là "đã pass".>
