# Kỷ luật phạm vi: review cái thay đổi, không review cả file

## Vấn đề

Mở một file trong PR, mắt sẽ thấy cả file — không chỉ phần `+`. Người review (và
LLM review còn nặng hơn) trượt sang: bug có từ trước, style của code không ai
đụng tới, refactor "nhân lúc đang ở đây". Kết quả quen thuộc: author nhận 20
finding, 3 cái thực sự nói về thay đổi của họ, 17 cái còn lại về code họ chỉ vô
tình đứng cạnh.

Hậu quả không phải "hơi ồn". Là ba thứ cụ thể:

1. **Mất signal.** Author không phân biệt được cái nào phải sửa trước khi merge.
   Finding thật bị chôn trong danh sách.
2. **PR bị chặn vì nợ của người khác.** Thay đổi 4 dòng bị giữ lại vì class đó
   vốn đã dùng raw SQL từ 2 năm trước. Author hoặc phải sửa phần không thuộc
   mình, hoặc phải đi thuyết phục reviewer bỏ qua.
3. **Review mất uy tín.** Sau vài lần, author học cách skim toàn bộ comment. Lúc
   đó finding chặn thật cũng bị skim luôn.

Google's *Code Review Developer Guide* nói thẳng ở "The Standard of Code Review":
reviewer không được giữ CL lại để đòi hoàn hảo; việc cần làm là xác nhận thay đổi
làm codebase **tốt lên**, và các đề xuất không bắt buộc thì gắn tiền tố `Nit:`.
Đây là bản vận hành có thể kiểm tra được của nguyên tắc đó.

## Ba lớp blocking-eligible

Một finding chỉ được quyền chặn PR nếu thuộc một trong ba lớp dưới. Script
`finding_scope_gate.py` phân loại tự động, không để reviewer tự phán.

### 1. DIFF-CONTAINED — dòng lỗi chính là dòng trong diff

Dòng `+` (side `new`) hoặc dòng `-` (side `old`). Mặc định, và chiếm đa số.

Finding về dòng `-` là hợp lệ và hay bị bỏ sót: xóa một validation, xóa một test
case, xóa một nhánh error handling đều là lỗi nằm ở dòng bị xóa.

### 2. DIFF-CAUSED — dòng lỗi ngoài diff, nhưng diff này gây ra

Đây là loại bug đắt nhất của PR, và là lý do **không** được chặn cứng theo
"chỉ dòng trong diff". Đổi signature `grant()` thì call site ở file khác vỡ —
dòng vỡ đó không có trong diff, nhưng PR này gây ra nó.

Điều kiện bắt buộc: finding phải khai `caused_by` trỏ tới một hunk hoặc một dòng
thật trong surface (`app/Services/EntitlementService.php:H1`). Không có mắt xích
→ gate xếp xuống phụ lục. Có mắt xích nhưng trỏ vào hunk không tồn tại → gate
từ chối ra verdict (`INPUT-REJECTED`), chứ không âm thầm hạ cấp.

Lý do bắt buộc khai: nếu cho phép "cái này liên quan đấy" bằng lời, mọi finding
pre-existing đều tự nhận là diff-caused. Mắt xích phải là thứ máy kiểm tra được.
Danh mục các kiểu breakage ngoài diff: `diff_caused_breakage.md`.

### 3. PR-LEVEL — thuộc tính của cả thay đổi, không của dòng nào

Không có file/line, khai `scope: "pr-level"`. Hợp lệ:

- Thay đổi hành vi idempotency nhưng không có test cho đường retry.
- Có migration nhưng không có đường rollback.
- Title/description nói một việc, diff làm việc khác.
- Thiếu feature flag cho thay đổi rủi ro cao (xem `feature-rollout-safety`).

Không hợp lệ: "project này thiếu test" — đó là pre-existing, không phải PR-level.
Phân biệt: PR-level là *cái PR này đáng lẽ phải kèm theo*, không phải *cái repo
này đáng lẽ phải có*.

## Ba lớp phụ lục (không bao giờ chặn)

- **DIFF-ADJACENT** — dòng context trong hunk. Diff *cho thấy* nó, không *đổi*
  nó. Đây là cái bẫy hay sập nhất: dòng hiện ra ngay trên màn hình review nên có
  cảm giác thuộc PR.
- **PRE-EXISTING** — trong file của diff nhưng ngoài mọi hunk, không có mắt xích.
- **NOT-IN-PR** — file không nằm trong diff, không có mắt xích.

Severity được giữ nguyên trong phụ lục nhưng bị đánh dấu `DEMOTED`. Severity nói
về *mức độ nghiêm trọng của bug*; scope nói về *PR nào phải trả giá cho nó*. Một
bug BLOCKER thật nằm ngoài phạm vi vẫn là BLOCKER — nhưng của PR khác.

## Quy tắc Boy Scout, và giới hạn của nó

"Để lại chỗ cắm trại sạch hơn lúc đến" là nguyên tắc tốt cho **author**, không
phải quyền cho **reviewer** ép author làm. Khoảng cách giữa hai việc đó là chỗ
review trượt phạm vi.

Cách xử lý phụ lục đúng: mở issue riêng, hoặc để nguyên trong phụ lục cho
author tự quyết. Không đổi nó thành điều kiện merge.

Ngoại lệ hẹp duy nhất: nếu code pre-existing **và** diff làm nó trở nên nguy
hiểm hơn (xóa guard khiến nhánh cũ giờ reachable), thì nó là DIFF-CAUSED, khai
`caused_by`, và được chặn. Khác biệt nằm ở mắt xích nhân quả, không ở cảm giác.

## Ngân sách chú ý

Scope discipline giải phóng chú ý, nhưng chú ý vẫn hữu hạn. Nghiên cứu code
review của Cisco/SmartBear (study trên ~2.500 review tại Cisco) báo cáo khả năng
phát hiện defect giảm rõ sau khoảng 200–400 LOC mỗi lượt review và sau khoảng 60
phút liên tục — con số của study đó, không phải hằng số phổ quát, nhưng hướng thì
nhất quán với *Software Engineering at Google* ch. 9: CL nhỏ, review nhanh, lặp
nhiều lần.

`diff_risk_router.py` phân bổ ngân sách đó **bên trong** diff: path chạm tiền /
auth / migration đọc từng dòng; lock file và generated code thì review *quyết
định nâng version*, không review dòng máy sinh.

## Nguồn

1. Google, *Code Review Developer Guide* — "The Standard of Code Review" và
   "What to Look For in a Code Review" (quy tắc không đòi hoàn hảo; tiền tố
   `Nit:`). https://google.github.io/eng-practices/review/
2. Winters, Manshreck, Wright, *Software Engineering at Google* (O'Reilly, 2020),
   ch. 9 "Code Review" — CL nhỏ, review theo thay đổi.
3. Bacchelli & Bird, "Expectations, Outcomes, and Challenges of Modern Code
   Review", ICSE 2013 — khó khăn số một của reviewer là hiểu *context và lý do*
   của thay đổi, không phải đọc code.
4. Rigby & Bird, "Convergent Contemporary Software Peer Review Practices",
   FSE 2013 — thực hành hội tụ: review nhỏ, tăng dần, thường xuyên.
5. Cohen et al. (SmartBear/Cisco), *Best Kept Secrets of Peer Code Review* —
   ngưỡng 200–400 LOC và ~60 phút cho hiệu quả phát hiện defect.
6. Conventional Comments — https://conventionalcomments.org/ — quy ước gắn nhãn
   `nit:` / `issue:` / `question:` để severity không bị suy diễn từ giọng văn.
7. Martin Fowler, "Refactoring" + quy tắc Boy Scout (Robert C. Martin, *Clean
   Code*) — nguyên tắc dành cho người sửa code, không phải cho người review.
