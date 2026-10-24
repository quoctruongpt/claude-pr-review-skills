# Giải phẫu unified diff: lấy đúng diff trước khi review

Scope discipline vô nghĩa nếu diff lấy ra đã sai. Phần này là các bẫy cụ thể khi
lấy diff, và cách đọc `@@` để biết số dòng nào thuộc về bên nào.

## Bẫy số một: hai dấu chấm vs ba dấu chấm

```bash
git diff main..HEAD    # SAI cho review PR
git diff main...HEAD   # ĐÚNG
```

- `main..HEAD` (hai chấm) = `git diff main HEAD`: so sánh hai **đầu nhánh**. Nếu
  `main` đã có commit mới sau khi bạn tách nhánh, những commit đó hiện ra trong
  diff như **phần bị xóa** — code của người khác xuất hiện trong "PR của bạn".
- `main...HEAD` (ba chấm) = diff từ **merge base** tới `HEAD`: chỉ commit của bạn.

Theo `gitrevisions(7)`, `git diff A...B` được định nghĩa là diff từ merge base
của A và B tới B. Đây là ngữ nghĩa GitHub dùng khi hiển thị PR, nên local phải
dùng ba chấm mới khớp với cái reviewer thấy trên web.

Dùng `gh pr diff <N>` thì không phải lo — nó đã trả về diff theo merge base.

```bash
gh pr diff 123 > pr.diff                       # an toàn
git diff --no-color -M main...HEAD > pr.diff   # an toàn
git fetch origin && git diff -M origin/main...HEAD > pr.diff  # khi main local cũ
```

Nếu `main` local lạc hậu, merge base cũng lạc hậu. Luôn `git fetch` trước.

## Đọc header hunk

```
@@ -40,9 +40,12 @@ class EntitlementService
```

- `-40,9` — bên **cũ** (old): bắt đầu dòng 40, dài 9 dòng.
- `+40,12` — bên **mới** (new): bắt đầu dòng 40, dài 12 dòng.
- Phần sau `@@` là "section heading", git đoán từ ngữ cảnh (tên hàm/class). Chỉ
  là gợi ý, có thể sai — đừng dùng nó làm căn cứ.
- Thiếu dấu phẩy (`@@ -40 +40,2 @@`) nghĩa là count = 1.

Trong thân hunk, con trỏ dòng chạy như sau:

| Prefix | old_ln | new_ln | Thuộc về |
|---|---|---|---|
| `' '` (context) | +1 | +1 | Không phải thay đổi — là DIFF-ADJACENT |
| `'+'` | — | +1 | Dòng added, số dòng là bên **new** |
| `'-'` | +1 | — | Dòng removed, số dòng là bên **old** |
| `'\'` | — | — | `\ No newline at end of file`, bỏ qua |

Đây là lý do một finding phải nói rõ `side`. "Dòng 43" là hai dòng khác nhau tùy
bên new hay old. Mặc định của gate là `new`; chỉ khai `old` khi finding nói về
dòng bị xóa.

## Rename và move: đừng review lại code không đổi

Không có `-M`, git hiển thị file đổi tên thành **một file xóa hết + một file thêm
mới toàn bộ**. Review như vậy là đọc lại nguyên file cũ như thể nó mới.

```bash
git diff -M main...HEAD         # bật rename detection
git diff -M -C main...HEAD      # thêm copy detection
git diff --color-moved=zebra    # tô khối code bị di chuyển nguyên khối
git diff --stat main...HEAD     # xem phân bố trước khi mở từng file
```

`diff_surface_builder.py` đọc `rename from` / `rename to` và set
`change_kind: renamed`, và phát hiện hunk chỉ đổi whitespace/thứ tự
(`whitespace_or_move_only`) bằng cách so sánh tập dòng added/removed sau khi
strip. Router hạ những file đó xuống `SCAN`: xác nhận không có gì đổi về mặt
nghĩa, rồi đi tiếp.

## Code máy sinh: review quyết định, không review dòng

`package-lock.json`, `go.sum`, `*.pb.go`, `__snapshots__/`, `dist/` — đọc từng
dòng ở đây là đốt ngân sách chú ý vào output của generator. Cái cần review là
**quyết định ở phía trên**: tại sao bump version này, bump có cố ý không,
changelog của dependency có gì.

`diff_surface_builder.py` gắn `generated: true` theo tên file, suffix, thư mục và
marker trong 5 dòng đầu (`@generated`, `DO NOT EDIT`). Router cho `SKIP-LINES`.

Lưu ý: **migration không phải generated**, dù tool sinh ra. Nó chạy một lần,
không rollback được dễ, và nằm ở nhánh rủi ro cao nhất. Router cho nó +3 điểm.

## Diff rỗng hoặc hỏng

Nếu `diff_surface_builder.py` exit 2 ("no files parsed"), kiểm tra theo thứ tự:

1. File có thật là unified diff không, hay là `git log -p` / output có màu? Luôn
   dùng `--no-color`.
2. Range có đúng không — `git diff main...HEAD` khi đang **ở trên** main sẽ rỗng.
3. Thay đổi còn trong working tree chưa commit? Dùng `git diff HEAD`.
4. Chỉ có file binary? Diff binary không có hunk; đó là kết quả đúng.

## Nguồn

1. GNU diffutils manual — "Detailed Description of Unified Format".
   https://www.gnu.org/software/diffutils/manual/html_node/Detailed-Unified.html
2. `git-diff(1)` — tùy chọn `-M`, `-C`, `--color-moved`, `--no-color`, `--stat`.
   https://git-scm.com/docs/git-diff
3. `gitrevisions(7)` — định nghĩa `A...B` qua merge base.
   https://git-scm.com/docs/gitrevisions
4. GitHub Docs, "About comparing branches in pull requests" — PR dùng three-dot
   comparison. https://docs.github.com/en/pull-requests
5. `gh pr diff` — GitHub CLI manual. https://cli.github.com/manual/gh_pr_diff
6. Gerrit Code Review, "Patch Sets" / interdiff — khái niệm review phần *mới*
   giữa hai patch set thay vì review lại toàn bộ.
   https://gerrit-review.googlesource.com/Documentation/
7. POSIX `diff` utility specification — unified format `@@` ranges.
   https://pubs.opengroup.org/onlinepubs/9699919799/utilities/diff.html
