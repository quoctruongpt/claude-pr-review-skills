# Danh mục breakage ngoài diff do diff gây ra

Đây là mục đích tồn tại của lớp `DIFF-CAUSED`. Lỗi nằm ở file không ai đụng tới,
nên nó *trông như* pre-existing, nhưng chính PR này tạo ra. Nếu chặn cứng theo
"chỉ dòng trong diff", đây đúng là loại bug bị bỏ sót — và là loại đắt nhất, vì
nó chỉ hiện ra lúc runtime trên production.

Mỗi mục dưới đây: **dấu hiệu trong diff** → **cái vỡ ở ngoài diff** → **lệnh đi
tìm** → **`caused_by` khai thế nào**.

`diff_risk_router.py` tự phát hiện 5 trong số này (SIGNATURE-CHANGED,
SIGNATURE-REMOVED-OR-RENAMED, EXPORT-REMOVED, GUARD-REMOVED, DEFAULT-CHANGED,
ENUM-VARIANT-ADDED) khi surface được build với `--keep-text`. Phần còn lại phải
tự soi.

---

## 1. Đổi signature (thêm/bớt/đổi thứ tự tham số, đổi kiểu trả về)

**Dấu hiệu:** dòng `-` và `+` cùng tên hàm, khác danh sách tham số.

**Vỡ ở đâu:** mọi call site cũ. Ngôn ngữ compile (Go, C#, Dart, TS strict) bắt
được lúc build — *trong cùng repo*. PHP/JS **không** — lỗi chỉ hiện lúc chạy đúng
nhánh đó. Kể cả ngôn ngữ compile cũng không bắt được: caller ở repo/package khác
(npm package, Go module, NuGet, pub package dùng chung), app mobile bản cũ đang
gọi API (RN/Flutter không ép cập nhật), Unity gọi qua `SendMessage`/reflection/
UnityEvent gán trong Inspector, Laravel route/container resolve bằng string,
NestJS DI theo token.
Tham số mới có default thì còn tệ hơn: build pass, chạy pass, nhưng caller cũ
chạy với hành vi cũ một cách im lặng.

```bash
srcwalk trace callers grant          # TS/Go/C#/PHP
rg -n -w 'grant' -g '*.dart'         # Dart: srcwalk chưa có grammar
rg -n "[\"']grant[\"']"              # gọi bằng string: SendMessage, Invoke, route, DI token
```

**caused_by:** `app/Services/EntitlementService.php:H1`

---

## 2. Xóa hoặc đổi tên symbol được export

**Dấu hiệu:** dòng `-` có `export` / `module.exports` / `public` / `__all__`, và
tên đó không còn xuất hiện ở dòng `+`.

**Vỡ ở đâu:** importer vỡ lúc load module, không phải lúc gọi — nghĩa là cả file
import nó chết, không chỉ một hàm.

**caused_by:** hunk chứa dòng export bị xóa.

---

## 3. Xóa guard / validation / authorization

**Dấu hiệu:** dòng `-` có `if (!...)`, `if not`, `assert`, `throw`, `raise`,
`abort()`, `return false`, `validate*`, `authorize*`, `can(...)`.

**Vỡ ở đâu:** nhánh code *phía sau* guard giờ reachable, hoặc reachable mà không
còn được validate. Code trong nhánh đó không đổi một dòng nào — nên bug trông
hoàn toàn pre-existing. Đây là ca kinh điển của broken access control
(OWASP A01:2021).

**Cách tìm:** không grep được. Phải trace: ai gọi tới hàm này, input nào trước
đây bị guard chặn, giờ input đó đi tới đâu.

**caused_by:** hunk chứa guard bị xóa. Finding trỏ vào dòng trong nhánh giờ mới
reachable.

---

## 4. Đổi giá trị default (tham số, config key, env var, feature flag)

**Dấu hiệu:** `-$retry = 3` / `+$retry = 0`, hoặc đổi default trong file config.

**Vỡ ở đâu:** mọi caller **không** truyền tham số đó. Không có lỗi, không có
exception — chỉ là hành vi khác. Loại này hay lên production rồi mới phát hiện,
và Google SRE ghi nhận config push là một trong các nguyên nhân sự cố hàng đầu
(xem *Site Reliability Engineering*, chương về release engineering và chương
Configuration trong *SRE Workbook*).

```bash
rg -n 'retryCount'   # tìm cả nơi đọc config key (appsettings, .env, app.json, pubspec)
```

**caused_by:** hunk chứa default mới.

---

## 5. Thêm biến thể enum / status / case mới

**Dấu hiệu:** dòng `+` thêm `case`, hằng số, hoặc giá trị enum.

**Vỡ ở đâu:** mọi `switch`/`match` trên type đó ở nơi khác. Ngôn ngữ có
exhaustiveness check (Dart 3 `switch` trên enum/sealed class, TS discriminated
union có `never` check) sẽ fail build. PHP, Go, JS, C# (`switch` có `default`/`_`)
thì rơi vào nhánh `default` — và câu hỏi duy nhất đáng hỏi là:
**nhánh default đó fail-closed hay fail-open?**

Với entitlement/payment, default fail-open (cấp quyền khi gặp trạng thái lạ) là
lỗ hổng im lặng. Giao agent `breaker` chứng minh bằng test khi đụng tiền.

**caused_by:** hunk thêm biến thể. Finding trỏ vào dòng `default` ở file khác.

---

## 6. Đổi schema DB: drop/rename column, đổi nullability, đổi kiểu

**Dấu hiệu:** file trong `migrations/`, `*.sql`, hoặc đổi model/entity.

**Vỡ ở đâu:** mọi query, ORM mapping, báo cáo, view, dashboard, ETL job đọc
column đó — kể cả thứ không nằm trong repo này. Thứ tự deploy quyết định: nếu
migration chạy trước khi code mới lên, code cũ đang chạy sẽ query column không
còn tồn tại.

Cách an toàn là parallel change / expand-contract (Fowler): thêm cột mới → ghi cả
hai → chuyển đọc → mới xóa cột cũ. Một PR vừa thêm vừa xóa là một PR không có
đường rollback.

**caused_by:** hunk migration. Xem thêm skill `migration`.

---

## 7. Đổi format serialization / contract API

**Dấu hiệu:** đổi response shape, đổi tên field JSON, đổi kiểu từ string sang
int, bỏ field, đổi proto field number.

**Vỡ ở đâu:** client đã release (mobile app không update được ngay), consumer
khác, cached payload cũ còn trong queue. Hyrum's Law: với đủ số lượng user, mọi
hành vi quan sát được của hệ thống đều đã có người phụ thuộc vào — kể cả hành vi
không nằm trong contract.

**caused_by:** hunk đổi shape. Xem thêm `api-contract-design`.

---

## 8. Đổi tên log / metric / event

**Dấu hiệu:** đổi string trong log line, tên metric, tên event analytics.

**Vỡ ở đâu:** alert rule, dashboard, log-based metric, funnel analytics. Không có
test nào bắt được. Phát hiện ra lúc có sự cố mà alert không kêu.

**caused_by:** hunk đổi string. Xem thêm `observability-designer`.

---

## 9. Bump dependency

**Dấu hiệu:** lock file + manifest cùng đổi.

**Vỡ ở đâu:** ở đâu cũng được. Ở đây cần review *quyết định*, không review dòng:
bump này cố ý hay do `install` kéo theo? Major hay minor? Đã đọc changelog chưa?
SemVer chỉ là lời hứa, không phải đảm bảo.

**caused_by:** hunk trong manifest (không phải lock file).

---

## 10. Đổi tên env var / secret key

**Dấu hiệu:** `.env.example`, config, Dockerfile, helm values.

**Vỡ ở đâu:** môi trường chưa được cập nhật — thường là production, vì staging
được sửa tay lúc test. App start lên với giá trị rỗng, hoặc fallback im lặng.

**caused_by:** hunk đổi tên key. Đây cũng thường là PR-LEVEL finding: "đổi tên
env var mà không có bước cập nhật môi trường trong mô tả PR".

---

## Giới hạn

Danh mục này không đầy đủ, và router chỉ phát hiện bằng pattern text — nó bỏ sót
mọi thứ cần hiểu ngữ nghĩa (ví dụ: đổi thứ tự hai lệnh gọi làm vỡ giả định về
thứ tự ở nơi khác). Watch item của router là **điểm cần đi kiểm tra**, không phải
finding. Nói "router không báo gì nên không có breakage" là kết luận sai.

## Nguồn

1. Semantic Versioning 2.0.0 — định nghĩa breaking change.
   https://semver.org/
2. Hyrum's Law — mọi hành vi quan sát được đều sẽ có người phụ thuộc vào.
   https://www.hyrumslaw.com/ ; và *Software Engineering at Google* ch. 21–22
   (Dependency Management, Large-Scale Changes).
3. Martin Fowler, "ParallelChange" (expand–migrate–contract).
   https://martinfowler.com/bliki/ParallelChange.html
4. Michael Feathers, *Working Effectively with Legacy Code* — seam và việc truy
   call site trước khi đổi interface.
5. OWASP Top 10 2021, A01 Broken Access Control — xóa/bỏ qua authorization check.
   https://owasp.org/Top10/A01_2021-Broken_Access_Control/
6. Beyer, Jones, Petoff, Murphy, *Site Reliability Engineering* (O'Reilly, 2016)
   + *The Site Reliability Workbook* — config change là nguồn sự cố hàng đầu;
   chương Release Engineering và Configuration.
7. Google API Improvement Proposals, AIP-180 "Backwards compatibility" — những gì
   được coi là thay đổi phá vỡ trên một API đã publish.
   https://google.aip.dev/180
8. Rust Reference, `#[non_exhaustive]` + Swift `@unknown default` — hai ngôn ngữ
   coi "thêm biến thể enum" là breaking change đủ nghiêm trọng để đưa vào ngôn ngữ.
