---
name: diff-scoped-review
description: Gate phạm vi cho review PR — phân loại finding có sẵn thành lỗi do diff gây ra (chặn) hay lỗi cũ (phụ lục), ra verdict. Script dùng chung với pr-review-expert; gọi tay khi chỉ cần gate một danh sách finding đã có.
disable-model-invocation: true
---

# Diff-Scoped Review

Review PR mà **chỉ** chặn trên thứ PR gây ra. Bug có từ trước, style của code
không ai đụng, refactor "nhân lúc đang ở đây" — vẫn được ghi nhận, nhưng xuống
phụ lục và không bao giờ là điều kiện merge.

Quy trình review PR đầy đủ nằm ở `pr-review-expert`: nó gọi script của skill này
ở bước 1 (surface), bước 2 (router + causal watch) và bước 9 (gate). Skill này
giữ script, reference và quy tắc phạm vi làm nguồn chung.

## Khi nào gọi riêng skill này

- Đã có sẵn danh sách finding (review của người khác, comment trên PR, báo cáo
  cũ) và chỉ cần biết finding nào được chặn PR này.
- PR nhỏ đang bị giữ lại vì vấn đề có sẵn của file nó chạm vào.
- Báo cáo review trước đó dài nhưng author không biết phải sửa cái nào.

## Khi nào KHÔNG dùng

- **Rà soát chủ động cả codebase tìm bug ẩn** → việc đó cố tình đi ra ngoài
  diff. Skill này cố tình không.
- **Review PR từ đầu** (tìm lỗi bảo mật, test, breaking change, hiệu năng, spec)
  → `pr-review-expert`. Skill này quyết định *được phép chặn trên cái gì*, không
  thay thế checklist tìm lỗi.
- **Chứng minh lỗi payment/webhook/entitlement vỡ thật** → agent `breaker`
  sau khi đã có danh sách blocking ở đây.

Khác biệt một câu: `pr-review-expert` trả lời *có lỗi gì*; skill này trả lời
*lỗi nào là của PR này*.

## Ba lớp được chặn, ba lớp phụ lục

| Class | Điều kiện | Chặn? |
|---|---|---|
| `DIFF-CONTAINED` | dòng `+` (side `new`) hoặc `-` (side `old`) trong diff | có |
| `DIFF-CAUSED` | dòng ngoài diff + `caused_by` trỏ vào hunk/dòng thật trong surface | có |
| `PR-LEVEL` | thuộc tính của cả thay đổi, khai `scope: "pr-level"` | có |
| `DIFF-ADJACENT` | dòng context trong hunk, không có mắt xích | không |
| `PRE-EXISTING` | trong file của diff, ngoài mọi hunk, không mắt xích | không |
| `NOT-IN-PR` | file không nằm trong diff, không mắt xích | không |

Severity (`BLOCKER`/`MAJOR`/`MINOR`/`NIT`) nói **bug nghiêm trọng tới đâu**.
Class nói **PR nào phải trả giá**. Một BLOCKER thật ngoài phạm vi vẫn là BLOCKER
— của PR khác. Gate ghi `DEMOTED` chứ không hạ severity.

`DIFF-CAUSED` tồn tại vì chặn cứng theo "chỉ dòng trong diff" sẽ bỏ sót đúng loại
bug đắt nhất: đổi signature làm vỡ caller ở file khác, xóa guard làm nhánh cũ
reachable, thêm enum làm `switch` ở nơi khác rơi vào `default` fail-open. Danh mục
đầy đủ: `references/diff_caused_breakage.md`.

## Workflow

### 1. Lấy đúng diff

```bash
gh pr diff 123 > pr.diff
# hoặc, local — BẮT BUỘC ba dấu chấm:
BASE=$(gh pr view 123 --json baseRefName -q .baseRefName)   # main, develop...
git fetch origin "$BASE" && git diff --no-color -M "origin/$BASE...HEAD" > pr.diff
```

`main..HEAD` (hai chấm) hiển thị cả commit người khác đã merge vào main như phần
bị xóa. Chi tiết: `references/unified_diff_anatomy.md`.

### 2. Dựng review surface

```bash
python3 scripts/diff_surface_builder.py --diff pr.diff --keep-text \
  --output json --out surface.json
python3 scripts/diff_surface_builder.py --diff pr.diff   # bản đọc được
```

Surface là ground truth: dòng nào added/removed, thuộc hunk nào, file nào là
generated/rename/whitespace-only. Exit 2 = không parse được file nào.

`--keep-text` là bắt buộc nếu muốn có causal watch ở bước 3.

### 3. Phân bổ chú ý bên trong surface

```bash
python3 scripts/diff_risk_router.py --surface surface.json
```

Trả về thứ tự đọc: `LINE-BY-LINE` (money/auth/webhook/migration) →
`FOCUSED` → `SCAN` → `SKIP-LINES` (lock file, generated, binary: review *quyết
định bump version*, không review dòng máy sinh). Kèm `causal_watch` — những dòng
trong diff có thể làm vỡ code ngoài diff, mỗi cái có lệnh đi tìm call site.

Đọc theo thứ tự này. Mỗi causal watch phải được đi kiểm tra trước khi approve:
kết quả hoặc thành một finding `DIFF-CAUSED`, hoặc thành một dòng trong mục "đã
kiểm tra" của báo cáo.

### 4. Gate findings

```bash
python3 scripts/finding_scope_gate.py --print-schema   # xem schema input
python3 scripts/finding_scope_gate.py --findings findings.json --surface surface.json
```

Exit code: `0` approve / approve-with-nits · `1` request-changes · `3`
**input rejected** — có finding thiếu anchor (không line, severity lạ, hoặc
`caused_by` trỏ vào hunk không tồn tại). Lúc exit 3 gate **không** ra verdict:
sửa finding rồi chạy lại. Đây là chủ ý — hạ cấp âm thầm một finding diff-caused
viết sai cú pháp còn tệ hơn là chặn lại và hỏi.

Viết báo cáo theo `assets/review_report_template.md`.

## Hard rules

1. **Không chặn trên class phụ lục.** Dù severity là BLOCKER. Mở issue riêng.
2. **`DIFF-CAUSED` phải có `caused_by` máy kiểm được.** Không chấp nhận mắt xích
   bằng lời ("cái này liên quan đấy") — nếu chấp nhận, mọi finding pre-existing
   sẽ tự nhận là diff-caused.
3. **Mỗi finding phải falsifiable.** "Vỡ khi nào: input X → kết quả Y sai". Không
   viết "có vẻ mong manh", "nên cân nhắc lại".
4. **Dòng `-` cũng review được.** Xóa validation, xóa test case, xóa nhánh error
   handling là lỗi nằm ở dòng bị xóa — khai `side: "old"`.
5. **Không approve im lặng.** Báo cáo phải nói rõ đã đọc file nào ở độ sâu nào,
   và causal watch nào đã đi kiểm tra. Không verify được thì ghi là không verify
   được — không coi đó là đã pass.
6. **Generated/lock file: review quyết định, không review dòng.** Nhưng
   **migration không phải generated** — nó ở nhánh rủi ro cao nhất.
7. **Router không báo gì ≠ không có breakage.** Router chỉ match pattern text; nó
   bỏ sót mọi thứ cần hiểu ngữ nghĩa.

## Câu hỏi bắt buộc tự trả lời trước khi approve

Hỏi từng câu một, không gộp. Mỗi câu kèm câu trả lời đề xuất và nguồn.

1. **Diff lấy bằng hai chấm hay ba chấm?** → ba chấm, hoặc `gh pr diff`.
   (`gitrevisions(7)`: `A...B` tính từ merge base, đúng ngữ nghĩa GitHub hiển thị.)
2. **Finding nào đang chặn mà thực ra là `DIFF-ADJACENT`?** → chạy gate thay vì
   tự phán; dòng context hiện ngay trên màn hình nên đây là bẫy hay sập nhất.
   (Google *Code Review Developer Guide*, "The Standard of Code Review": không
   giữ CL lại để đòi hoàn hảo.)
3. **Causal watch nào chưa đi kiểm tra?** → với watch có symbol, chạy
   `srcwalk trace callers <symbol>` (router in sẵn; file Dart dùng `rg -w`, vì srcwalk chưa hỗ trợ Dart).
   Bỏ qua bước này là chỗ duy nhất skill này có thể miss bug thật.
   (Hyrum's Law; Fowler *ParallelChange*.)
4. **Diff có đổi default, enum, hay signature không?** → nếu có, nhánh `default`
   ở nơi khác fail-closed hay fail-open? Với entitlement/payment, fail-open là lỗ
   hổng im lặng. (Giao cho agent `breaker` chứng minh bằng test.)
5. **Tỉ lệ finding trong phạm vi trên tổng là bao nhiêu?** → gate tự cảnh báo
   `SCOPE DRIFT` khi quá nửa nằm ngoài phạm vi. Dưới một nửa thì author sẽ skim
   cả danh sách. (Bacchelli & Bird, ICSE 2013.)
6. **PR này có cần `pr-review-expert` / agent `breaker` / skill khác không?** →
   router in sẵn `pull in:` theo path. Skill này quyết định phạm vi, không thay
   thế checklist tìm lỗi.

## Files

```
scripts/diff_surface_builder.py   diff → review surface (ground truth)
scripts/diff_risk_router.py       độ sâu đọc + causal watch bên trong surface
scripts/finding_scope_gate.py     phân loại finding → verdict (exit 0/1/3)

references/diff_scope_discipline.md   6 class, lý do, giới hạn quy tắc Boy Scout
references/unified_diff_anatomy.md    hai chấm vs ba chấm, @@, rename, generated
references/diff_caused_breakage.md    10 kiểu breakage ngoài diff + lệnh đi tìm

assets/findings_schema.json         schema input cho gate
assets/example_findings.json        worked example, một finding mỗi class
assets/review_report_template.md    khung báo cáo
```

Mọi script: stdlib, không network, không LLM call, có `--help` và `--sample`,
`--output json` để pipe.
