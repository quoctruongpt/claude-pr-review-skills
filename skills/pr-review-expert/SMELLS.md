# Code smell baseline (Fowler, *Refactoring* ch.3)

Đọc khi chạy bước 8 của `pr-review-expert`. Mỗi mục: smell là gì → cách sửa.

- **Mysterious Name**: tên không nói được nó làm gì → đổi tên; không đặt được tên rõ thì thiết kế đang mù mờ.
- **Duplicated Code**: cùng một khối logic ở nhiều hunk/file → tách ra dùng chung.
- **Feature Envy**: method đụng vào dữ liệu object khác nhiều hơn của chính nó → chuyển method sang chỗ dữ liệu.
- **Data Clumps**: vài field/tham số luôn đi cùng nhau → gom thành một kiểu.
- **Primitive Obsession**: string/int đứng thay khái niệm domain → tạo kiểu riêng (enum, value object).
- **Repeated Switches**: cùng một `switch`/chuỗi `if` theo cùng một type lặp lại → polymorphism hoặc một map dùng chung.
- **Shotgun Surgery**: một thay đổi logic buộc sửa rải rác nhiều file → gom thứ hay đổi cùng nhau về một module.
- **Divergent Change**: một file bị sửa vì nhiều lý do không liên quan → tách.
- **Speculative Generality**: abstraction/tham số/hook cho nhu cầu spec không có → xóa.
- **Message Chains**: `a->b()->c()->d()` → giấu sau một method.
- **Middle Man**: class/hàm gần như chỉ chuyển tiếp → gọi thẳng đích.
- **Refused Bequest**: class con bỏ qua phần lớn thứ kế thừa → dùng composition.
