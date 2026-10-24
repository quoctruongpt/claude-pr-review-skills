# Stack checks cho bước 3–6

Chỉ chạy khối **Chung** và khối của stack có trong diff. Mọi lệnh chạy trên
`$ADDED=$W/added.txt` / `$REMOVED=$W/removed.txt` (dòng dạng `path:line:text`,
đã bỏ file generated). Dòng khớp là *gợi ý đọc*, chưa phải finding.

```bash
ADDED=$W/added.txt; REMOVED=$W/removed.txt
```

Mục lục: [Chung](#chung) · [TS/Node](#tsnode) · [React Native](#react-native) ·
[Dart/Flutter](#dartflutter) · [C#/.NET](#cnet) · [Unity](#unity) ·
[PHP/Laravel](#phplaravel) · [Go](#go)

---

## Chung

### Bảo mật
```bash
# Secret hardcode — gán (=), mảng PHP (=>), YAML/JSON/plist (:)
grep -iE "(password|passwd|secret|api_?key|apikey|token|private_?key|client_?secret)['\"]?\s*(=>|=|:)\s*['\"][^'\"]{8,}" $ADDED
grep -E "AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|sk_live_[0-9a-zA-Z]{20,}|xox[bp]-|ghp_[0-9A-Za-z]{36}|-----BEGIN (RSA |EC )?PRIVATE KEY" $ADDED
# Auth bypass / TODO bảo mật
grep -iE "bypass|skip.?auth|noauth|disable.?auth|TODO.*(auth|security|validate)|FIXME.*(auth|security)" $ADDED
# Hash/crypto yếu, random yếu cho token
grep -iE "\bmd5\b|\bsha1\b|DES\b|ECB|Math\.random\(|new Random\(|math/rand|\brand\(|mt_rand\(" $ADDED
# TLS tắt / cho phép mọi cert
grep -iE "rejectUnauthorized:\s*false|InsecureSkipVerify:\s*true|badCertificateCallback|ServerCertificateCustomValidationCallback|CURLOPT_SSL_VERIFYPEER.*false|NSAllowsArbitraryLoads|usesCleartextTraffic=\"true\"" $ADDED
# Log dữ liệu nhạy cảm
grep -iE "(console\.(log|info|debug)|print\(|debugPrint\(|Debug\.Log|_logger\.Log|logger\.(info|debug)|Log::(info|debug)|log\.Print).*(token|password|secret|receipt|card|otp|authorization)" $ADDED
# Webhook/callback mới: phải verify chữ ký và idempotency
grep -iE "webhook|callback|notification" $ADDED | grep -iE "route|post|controller|handler|router\.|app\.(post|use)|\[Http(Post)\]|HandleFunc|\.POST\("
```

### Breaking change
```bash
# Env var/config đọc mới hoặc bị bỏ — so sánh hai danh sách
PAT="process\.env\.[A-Z_]+|env\(['\"][A-Z_]+|os\.Getenv\(\"[A-Z_]+|Environment\.GetEnvironmentVariable\(\"[A-Z_]+|Configuration\[\"[A-Za-z:_]+|dotenv\.env\['[A-Z_]+|String\.fromEnvironment\('[A-Z_]+|config\('[a-z_.]+"
grep -oE "$PAT" $ADDED | sort -u
grep -oE "$PAT" $REMOVED | sort -u
# Migration: tìm file mới
git diff --name-only origin/$BASE...HEAD | grep -iE "migrations?/|\.sql$|schema\.prisma$"
grep -iE "DROP (TABLE|COLUMN)|NOT NULL|ALTER TABLE|RENAME (COLUMN|TO)|dropColumn|dropTable|renameColumn|DropColumn|DropTable|RenameColumn" $ADDED
```
Mỗi `ALTER TABLE` trên bảng lớn (MySQL): có khai `ALGORITHM=INSTANT/INPLACE, LOCK=NONE` không? Postgres: `CREATE INDEX` có `CONCURRENTLY` không? Thêm cột NOT NULL có default không?

### Hiệu năng
```bash
# Dependency mới (package.json, pubspec.yaml, csproj, composer.json, go.mod)
git diff origin/$BASE...HEAD -- '*package.json' '*pubspec.yaml' '*.csproj' '*composer.json' '*go.mod' | grep -E '^\+' | grep -vE '^\+\+\+'
# Vòng lặp không giới hạn
grep -E "while\s*\(\s*true\s*\)|for\s*\(\s*;\s*;\s*\)|for \{$" $ADDED
# Cache/Redis không TTL
grep -iE "\.set\(|setex|HSet\(|SetNX\(|Cache::(put|forever)|IMemoryCache|IDistributedCache|cache\.(set|put)" $ADDED
```

---

## TS/Node

(Express, NestJS, Next.js API, Prisma/TypeORM/Knex/Mongoose)

### Bảo mật
```bash
# SQL/NoSQL injection
grep -E "\\\$queryRawUnsafe|\\\$executeRawUnsafe|\.raw\(|\.query\(\s*[\`'\"].*\\\$\{|\.query\(.*\+\s*\w" $ADDED
grep -E "\.(find|findOne|updateOne|deleteMany|aggregate)\(\s*req\.(body|query|params)" $ADDED   # NoSQL operator injection ($gt, $ne)
# Code exec / command injection
grep -E "\beval\(|new Function\(|vm\.run|child_process|\bexec\(|execSync\(|spawn\(.*shell:\s*true" $ADDED
# Path traversal
grep -E "(readFile|createReadStream|sendFile|res\.download|path\.join)\(.*req\.(params|query|body)" $ADDED
# Prototype pollution / mass assignment
grep -E "Object\.assign\(\s*\w+,\s*req\.body|\.\.\.req\.body|merge\(.*req\.body|\.update\(\s*\{?\s*data:\s*req\.body" $ADDED
# XSS (Next/React server-rendered)
grep -E "dangerouslySetInnerHTML|innerHTML\s*=|res\.send\(.*req\.(query|params)" $ADDED
# CORS mở, JWT yếu
grep -E "origin:\s*(true|['\"]\*['\"])|credentials:\s*true|algorithms:\s*\[.*none|jwt\.decode\(|ignoreExpiration:\s*true" $ADDED
# Route mới — có guard/middleware auth không
grep -E "@(Get|Post|Put|Patch|Delete)\(|router\.(get|post|put|patch|delete)\(|app\.(get|post|put|patch|delete)\(|export (async )?function (GET|POST|PUT|PATCH|DELETE)" $ADDED
grep -E "@Public\(|@SkipAuth|@AllowAnonymous" $ADDED
# Validation: DTO thiếu class-validator / zod
grep -E "@Body\(\)\s+\w+:\s*any|req\.body\.\w+" $ADDED
```

### Test
```bash
npx vitest run --coverage 2>/dev/null | tail -20 || npx jest --coverage 2>/dev/null | tail -20
npx tsc --noEmit -p . 2>&1 | tail -20      # type-check: bắt caller vỡ trong cùng repo
```

### Breaking change
```bash
# Export bị xóa (importer ngoài diff vỡ)
grep -E "^\S+:\d+:\s*export " $REMOVED
# Field DTO/response/type bị xóa hoặc đổi optional → required
grep -E "^\S+:\d+:\s+\w+\??:\s" $REMOVED | grep -iE "dto|type|interface|schema|model|response"
# Prisma schema: field/model/enum đổi
git diff origin/$BASE...HEAD -- '*schema.prisma'
```

### Hiệu năng
```bash
# N+1: await query trong vòng lặp
grep -E "for\s*\(.*of|\.forEach\(|\.map\(" $ADDED     # rồi xem thân vòng lặp có await prisma/repo/fetch không
grep -E "await .*\.(findUnique|findOne|findFirst|findById|query)\(" $ADDED
# Block event loop
grep -E "readFileSync|writeFileSync|execSync|JSON\.parse\(.*(readFileSync|body)|bcrypt\.hashSync|crypto\.pbkdf2Sync" $ADDED
# Promise không await / không catch
grep -E "^\S+:\d+:\s+[a-zA-Z_.]+\(.*\);\s*$" $ADDED | grep -iE "send|save|update|delete|publish|emit|enqueue"   # đọc xem có thiếu await không
```

---

## React Native

(Expo/bare, React Navigation, Redux/Zustand/React Query)

### Bảo mật
```bash
# Lưu token/secret không mã hóa
grep -E "AsyncStorage\.setItem\(.*(token|password|secret|session)|MMKV.*(token|password)" $ADDED
# Secret trong bundle JS (mọi thứ trong bundle là public)
grep -E "EXPO_PUBLIC_|process\.env\.\w+(SECRET|PRIVATE|KEY)" $ADDED
# WebView nguy hiểm
grep -E "javaScriptEnabled|originWhitelist=\{\[['\"]\*|injectedJavaScript|onMessage=|allowFileAccess|mixedContentMode" $ADDED
# Deep link: tham số đi thẳng vào navigation/API không validate
grep -E "Linking\.(getInitialURL|addEventListener)|linking=\{|useURL\(|expo-linking" $ADDED
# Kiểm premium/entitlement ở client
grep -iE "isPremium|isPro|hasEntitlement|entitlements\.active|purchaserInfo|customerInfo" $ADDED
```
Mọi cờ premium kiểm ở client phải có kiểm tương ứng ở server cho tài nguyên trả phí.

### Test
```bash
npx jest --coverage 2>/dev/null | tail -20
npx tsc --noEmit 2>&1 | tail -20
```

### Breaking change
```bash
# Native config & permission mới
git diff origin/$BASE...HEAD -- '**/AndroidManifest.xml' '**/Info.plist' '**/*.entitlements' 'app.json' 'app.config.*' 'eas.json' '**/build.gradle' '**/Podfile'
grep -E "uses-permission|NS\w+UsageDescription|minSdkVersion|targetSdkVersion|IPHONEOS_DEPLOYMENT_TARGET|platform :ios|\"version\"|runtimeVersion|versionCode|buildNumber" $ADDED
# Native module mới + OTA update: JS mới trên binary cũ sẽ crash
grep -E "NativeModules\.|requireNativeModule|TurboModuleRegistry" $ADDED
# Key storage/navigation đổi: user cũ mất state, deep link cũ chết
grep -E "AsyncStorage\.(getItem|setItem)\(['\"]|name=['\"]\w+['\"]|screens:\s*\{" $REMOVED
```
Thêm native dependency hay đổi `runtimeVersion` mà PR vẫn nói "ship qua OTA" → finding PR-LEVEL.

### Hiệu năng
```bash
# Render lại thừa: object/func inline làm prop, list không virtualize
grep -E "ScrollView" $ADDED                                  # list dài dùng ScrollView thay FlatList/FlashList?
grep -E "renderItem=\{\s*\(|keyExtractor=\{\s*\(.*index|key=\{index\}" $ADDED
grep -E "style=\{\{|onPress=\{\(\)\s*=>" $ADDED | grep -iE "renderItem|Item|Row|Cell"   # trong item của list
# useEffect thiếu cleanup / deps sai
grep -E "useEffect\(|addEventListener|addListener|setInterval|subscribe\(" $ADDED   # có return cleanup không?
# Ảnh lớn không cache/resize
grep -E "<Image\s|source=\{\{\s*uri" $ADDED
```

---

## Dart/Flutter

(Riverpod/Bloc/Provider, Dio/http, Drift/Isar/Hive, in_app_purchase/RevenueCat)

> srcwalk chưa hỗ trợ Dart: blast radius dùng `rg -w '<symbol>' -g '*.dart'`.

### Bảo mật
```bash
# Lưu token không mã hóa
grep -E "SharedPreferences|prefs\.set(String|Bool)|Hive\.box" $ADDED | grep -iE "token|password|secret|session"
# Secret trong app (dart-define vẫn nằm trong binary)
grep -E "String\.fromEnvironment|dotenv\.env\[|const\s+\w*(key|secret|token)\w*\s*=" $ADDED
# TLS / cert
grep -E "badCertificateCallback|HttpOverrides|onBadCertificate" $ADDED
# WebView / deep link
grep -E "JavaScriptMode\.unrestricted|setJavaScriptMode|addJavaScriptChannel|uni_links|app_links|getInitialLink|onGenerateRoute" $ADDED
# Raw SQL local
grep -E "rawQuery\(|rawInsert\(|execute\(['\"].*\\\$" $ADDED
# Kiểm premium ở client
grep -iE "isPremium|entitlements|customerInfo|purchaseDetails\.status|PurchaseStatus\." $ADDED
```
IAP: `purchaseStream` phải xử lý `pending/error/restored`, gọi `completePurchase` khi `pendingCompletePurchase`, và verify receipt ở server trước khi cấp quyền.

### Test
```bash
flutter test --coverage 2>/dev/null | tail -20      # hoặc: dart test
dart analyze 2>&1 | tail -20                        # bắt caller vỡ, lint
```

### Breaking change
```bash
git diff origin/$BASE...HEAD -- 'pubspec.yaml' '**/AndroidManifest.xml' '**/Info.plist' '**/*.entitlements' '**/build.gradle*' '**/Podfile'
grep -E "^\s*version:|sdk:|flutter:|minSdk|targetSdk|uses-permission|NS\w+UsageDescription" $ADDED
# Model JSON đổi field (json_serializable/freezed): app cũ đọc response mới, cache cũ đọc model mới
grep -E "@JsonKey|fromJson|toJson|final \w+\??\s+\w+;" $REMOVED
# Schema DB local (Drift/Isar/Hive): đổi schemaVersion có migration không
grep -E "schemaVersion|@HiveType|@HiveField|@collection|MigrationStrategy" $ADDED $REMOVED
# Route name đổi: deep link/push notification cũ chết
grep -E "GoRoute\(|path:\s*['\"]|routes:\s*\[" $REMOVED
```

### Hiệu năng
```bash
# setState/rebuild lớn, build() nặng
grep -E "setState\(|\.watch\(|context\.watch|BlocBuilder|Consumer\(" $ADDED
grep -E "ListView\(|Column\(.*children:.*\.map\(|SingleChildScrollView" $ADDED   # list dài không dùng ListView.builder?
# Thiếu const, tạo object trong build
grep -E "Widget build\(" $ADDED
# Async gap: dùng BuildContext/setState sau await mà không kiểm mounted
grep -E "await " $ADDED          # rồi xem dòng sau có context./setState( mà thiếu if (!mounted) / context.mounted
# Controller/stream không dispose
grep -E "(Animation|TextEditing|Scroll|Page|Tab)Controller\(|StreamSubscription|\.listen\(|Timer(\.periodic)?\(" $ADDED   # có dispose()/cancel() không?
# Việc nặng trên UI isolate
grep -E "jsonDecode\(|json\.decode\(" $ADDED     # payload lớn → compute()/Isolate.run
```

---

## C#/.NET

(ASP.NET Core, EF Core, Dapper, MediatR)

### Bảo mật
```bash
# SQL injection
grep -E "FromSqlRaw\(|ExecuteSqlRaw\(|SqlQueryRaw|\.Query(<\w+>)?\(\s*\\\$\"|\.Execute\(\s*\\\$\"|new SqlCommand\(.*(\+|\\\$\")" $ADDED
# Auth
grep -E "\[AllowAnonymous\]|\[Http(Get|Post|Put|Patch|Delete)|Map(Get|Post|Put|Patch|Delete)\(" $ADDED     # endpoint mới có [Authorize]/RequireAuthorization?
grep -E "\[Authorize" $REMOVED
# Deserialization nguy hiểm, XXE
grep -E "BinaryFormatter|TypeNameHandling\.(All|Auto|Objects)|JavaScriptSerializer|XmlDocument\(|DtdProcessing\.Parse" $ADDED
# Mass assignment: bind thẳng vào entity
grep -E "\[FromBody\]\s+\w+(Entity|Model)\b|_context\.\w+\.Update\(\s*\w+\s*\)" $ADDED
# Command/path
grep -E "Process\.Start\(|Path\.Combine\(.*(Request|query|input)" $ADDED
```

### Test
```bash
dotnet test --collect:"XPlat Code Coverage" 2>/dev/null | tail -20
dotnet build -warnaserror 2>&1 | tail -20
```

### Breaking change
```bash
# EF Core migration: Down() có làm ngược Up() không; drop/rename cột
git diff --name-only origin/$BASE...HEAD | grep -E "Migrations/.*\.cs$" | grep -vE "Designer\.cs$|ModelSnapshot\.cs$"
grep -E "DropColumn|DropTable|RenameColumn|AlterColumn.*nullable:\s*false" $ADDED
# Public API/DTO đổi
grep -E "public\s+[\w<>?,\[\] ]+\s+\w+\s*\{\s*get;" $REMOVED
grep -E "appsettings.*\.json:" $ADDED $REMOVED
```

### Hiệu năng
```bash
# Sync-over-async, async void
grep -E "\.Result\b|\.Wait\(\)|GetAwaiter\(\)\.GetResult\(\)|async void " $ADDED
# N+1 / thiếu Include / tải cả bảng
grep -E "\.ToList\(\)\.(Where|Select|First)|foreach.*\n?.*await .*(Find|First|Single)Async|\.Include\(" $ADDED
grep -E "AsNoTracking" $REMOVED
# HttpClient tạo mới mỗi lần, IDisposable không using
grep -E "new HttpClient\(|new SqlConnection\(|new FileStream\(" $ADDED
```

---

## Unity

(MonoBehaviour, ScriptableObject, Addressables, Unity IAP, Netcode)

### Bảo mật
```bash
# Lưu dữ liệu nhạy cảm/tiền tệ ở client không bảo vệ
grep -E "PlayerPrefs\.Set(String|Int|Float)" $ADDED | grep -iE "token|coin|gem|gold|currency|premium|purchase|score"
# IAP: cấp hàng ở client không verify receipt server-side
grep -E "ProcessPurchase|PurchaseProcessingResult|ConfirmPendingPurchase|CrossPlatformValidator|IStoreListener|IDetailedStoreListener" $ADDED
# Gọi động bằng string (khó trace, dễ bị lợi dụng)
grep -E "SendMessage\(|BroadcastMessage\(|Invoke\(\"|Type\.GetType\(|Assembly\.Load" $ADDED
# Multiplayer: tin client
grep -E "\[(ServerRpc|Command|ClientRpc|Rpc)" $ADDED      # ServerRpc có validate input/quyền không
```

### Test
Unity test cần Editor (chạy batchmode lâu, cần license): chỉ chạy khi user yêu cầu.
```bash
# Unity -batchmode -projectPath . -runTests -testPlatform EditMode -testResults $W/unity-tests.xml -logFile -
```
Không chạy được → ghi "chưa chạy Unity test" và review test bằng đọc.

### Breaking change
```bash
# Đổi tên/xóa field serialized → mất dữ liệu đã gán trong scene/prefab/ScriptableObject
grep -E "\[SerializeField\]|^\S+:\d+:\s+public\s+[\w<>\[\]]+\s+\w+\s*;" $REMOVED
grep -E "FormerlySerializedAs" $ADDED          # rename có kèm attribute này không
# Script đổi tên/namespace/xóa → prefab/scene mất reference (Missing Script)
git diff --name-status -M origin/$BASE...HEAD | grep -E "^(R|D).*\.cs$"
git diff --name-status origin/$BASE...HEAD | grep -E "\.cs\.meta$"     # đổi .meta (GUID) = mất mọi reference
# Project settings, package, define symbols
git diff origin/$BASE...HEAD -- 'ProjectSettings/*' 'Packages/manifest.json'
```
Đổi `.meta` của asset có sẵn (GUID mới) là BLOCKER mặc định: mọi reference tới asset đó vỡ im lặng.

### Hiệu năng
```bash
# Allocation/lookup trong vòng lặp frame
grep -E "void (Update|FixedUpdate|LateUpdate|OnGUI)\(" $ADDED     # rồi xem thân hàm:
grep -E "GetComponent<|FindObjectOfType|GameObject\.Find|Camera\.main|new List<|new \w+\[|\.ToList\(\)|LINQ|string\.Format|\+\s*\"|Instantiate\(|Resources\.Load" $ADDED
# Coroutine/event không hủy
grep -E "StartCoroutine|InvokeRepeating|\+= On\w+|AddListener\(" $ADDED     # có StopCoroutine/-=/RemoveListener ở OnDisable/OnDestroy không
# async không theo lifecycle
grep -E "async (void|Task|UniTask)" $ADDED     # object bị Destroy giữa chừng thì sao (destroyCancellationToken)?
```

---

## PHP/Laravel

### Bảo mật
```bash
# SQL injection: raw query nối chuỗi, không bind
grep -E "DB::raw|whereRaw|selectRaw|orderByRaw|havingRaw|->raw\(|DB::(select|statement|unprepared)\(" $ADDED | grep -E '\$\{|\.\s*\$|sprintf|"\s*\.|\$[a-z]\w*\s*\.|"[^"]*\$[a-z]'
# Code exec
grep -E "\beval\(|create_function\(|\bsystem\(|shell_exec\(|passthru\(|\bexec\(|proc_open\(|unserialize\(\s*\\\$" $ADDED
# Mass assignment
grep -E "\\\$guarded\s*=\s*\[\s*\]|->(fill|update|create)\(\s*\\\$request->all\(\)|forceFill\(" $ADDED
# XSS trong Blade
grep -E "\{!!\s*\\\$" $ADDED
# Auth / authorization
grep -E "Route::(get|post|put|patch|delete|resource|apiResource)\(" $ADDED     # nằm trong group middleware('auth') không?
grep -E "withoutMiddleware|->middleware\(" $ADDED $REMOVED
grep -E "\\\$this->authorize|Gate::|->can\(|policy" $REMOVED
# Upload: kiểm mime/size/đường dẫn
grep -E -e "->store(As)?\(|move_uploaded_file|getClientOriginalName" $ADDED
```

### Test
```bash
php artisan test --coverage 2>/dev/null | tail -20     # hoặc: vendor/bin/pest --coverage
vendor/bin/phpstan analyse --no-progress 2>/dev/null | tail -20
```

### Breaking change
```bash
grep -E "Route::(get|post|put|patch|delete)\(" $REMOVED
for f in $(git diff --name-only origin/$BASE...HEAD | grep -E "database/migrations/.*\.php$"); do grep -q "function down" $f || echo "thiếu down(): $f"; done
grep -E "dropColumn|dropTable|renameColumn|->change\(\)|->nullable\(false\)" $ADDED
# API Resource/field đổi
grep -E "'\w+'\s*=>" $REMOVED | grep -iE "Resource|Transformer"
```

### Hiệu năng
```bash
# N+1: query/relationship trong vòng lặp, thiếu with()
grep -E "::find\(|::where\(|->(load|first|get)\(\)|->\w+\(\)->get\(\)" $ADDED      # có nằm trong foreach/map/each không
grep -E -e "->with\(|->load\(" $REMOVED
# Lấy cả bảng
grep -E "::all\(\)|->get\(\)" $ADDED | grep -vE "paginate|chunk|cursor|limit|take"
# Job/queue mới: có tries/timeout/unique không
grep -E "implements ShouldQueue|dispatch\(" $ADDED
```

---

## Go

(net/http, gin/echo/chi/fiber, database/sql, sqlx, gorm)

### Bảo mật
```bash
# SQL injection
grep -E '(Query|QueryRow|Exec|Raw|Where)(Context)?\(.*(Sprintf|" *\+)' $ADDED
grep -E 'Sprintf\("[^"]*(SELECT|INSERT|UPDATE|DELETE|WHERE|ORDER BY)' $ADDED
# Body/multipart không giới hạn kích thước
grep -E 'MultipartForm\(|ParseMultipartForm|ShouldBind|FormFile\(|ReadAll\(.*Body|json\.NewDecoder\(r\.Body\)' $ADDED
grep -q 'MaxBytesReader' $ADDED || echo "diff không có MaxBytesReader: kiểm giới hạn body ở middleware và gateway (giả định runtime, bước 9)"
# Command/path
grep -E 'exec\.Command\(|filepath\.Join\(.*(r\.URL|c\.Param|c\.Query)|os\.Open\(.*(r\.URL|c\.Param)' $ADDED
# Route mới: nhóm có middleware auth không
grep -E '\.(GET|POST|PUT|PATCH|DELETE|Handle|HandleFunc)\(' $ADDED
# Template không escape
grep -E '"text/template"|template\.HTML\(' $ADDED
```

### Test
```bash
go test ./... -race -cover 2>/dev/null | tail -20
go vet ./... 2>&1 | tail -20
```

### Breaking change
```bash
# Exported symbol bị xóa/đổi (module dùng chung vỡ ở repo khác)
grep -E "^\S+:\d+:func (\([^)]*\) )?[A-Z]|^\S+:\d+:type [A-Z]|^\S+:\d+:\s+[A-Z]\w*\s+\S+\s+\`json" $REMOVED
for f in $(git diff --name-only origin/$BASE...HEAD | grep -E 'migrations?/.*\.up\.sql$'); do [ -f "${f%.up.sql}.down.sql" ] || echo "thiếu down: $f"; done
grep -E 'json:"[^"]+"' $REMOVED     # field JSON đổi tên/xóa
```

### Hiệu năng
```bash
# Goroutine mới: recover, context nào (Background hay ctx request đã hủy), cái gì đảm bảo nó kết thúc
grep -E '\bgo (func|[A-Za-z_][A-Za-z0-9_.]*\()' $ADDED | grep -v '_test\.go:'
# Query trong vòng lặp
grep -E 'for .* range ' $ADDED      # rồi xem thân có db.Query/QueryRow/Get không
# Defer trong vòng lặp, rows không Close
grep -E 'defer ' $ADDED; grep -E '\.Query(Context)?\(' $ADDED     # có defer rows.Close() và kiểm rows.Err() không
```
