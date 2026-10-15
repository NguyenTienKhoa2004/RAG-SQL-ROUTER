# Luồng xử lý query từ người dùng

Sơ đồ mô tả code ứng dụng hiện tại trong `frontend/src/` và `backend/`, bao gồm các thay đổi đang có trong workspace. `app.py` chỉ xuất FastAPI app; notebook và `workflow_all_flows.html` không phải entry point của ứng dụng hiện tại.

## 1. Từ UI đến câu trả lời

```mermaid
flowchart TD
    U([User nhập query và nhấn Enter hoặc Gửi]) --> V{Query sau trim rỗng<br/>hoặc UI đang busy?}
    V -->|Có| IGN([Không gửi request])
    V -->|Không| SS{Đã kết nối session?}
    SS -->|Chưa| CONNECT([Mở hộp thoại kết nối])
    SS -->|Rồi| SEND[useWorkspace.send<br/>Khóa thao tác UI, xóa lỗi cũ<br/>Hiển thị query pending và trạng thái tra cứu]
    SEND --> HTTP[POST /api/sessions/session_id/chat<br/>JSON chứa message]
    HTTP --> VALID{ChatRequest hợp lệ?<br/>message là chuỗi, dài 1–12000 ký tự}
    VALID -->|Không| H422[HTTP 422]
    VALID -->|Có| GET[SessionService.get<br/>Prune session hết hạn và không bị khóa<br/>Tìm session, cập nhật touched]
    GET --> EXISTS{Session tồn tại?}
    EXISTS -->|Không| H404[HTTP 404]
    EXISTS -->|Có| TRIM{question.strip có nội dung?}
    TRIM -->|Không| H400[HTTP 400]
    TRIM -->|Có| LOCK[Chờ và giữ session.lock<br/>Lưu turn_start và bắt đầu đo thời gian]
    LOCK --> RUN[asyncio.wait_for workflow.run<br/>query_timeout mặc định 60 giây]
    RUN --> PREP[prepare_chat: StartEvent<br/>Thêm user message vào chat_history<br/>Phát InputEvent]
    PREP --> CHAT[chat: tính needs_tool<br/>Có tool và chưa có role=tool trong lượt hiện tại<br/>thì tool_required=True]
    CHAT --> LLM[Router LLM qua OpenRouter<br/>System prompt + toàn bộ chat_history<br/>Tool definitions hiện có<br/>Cho phép nhiều tool call]
    LLM --> PARSE[Lấy tool_calls<br/>Lưu assistant message vào chat_history]
    PARSE --> CALLS{Có tool call?}
    CALLS -->|Không| REQUIRED{needs_tool=True?}
    REQUIRED -->|Có| MISSING[StopEvent: báo mô hình không gọi tool]
    REQUIRED -->|Không| FINAL[StopEvent: nội dung assistant]
    CALLS -->|Có| DISPATCH[dispatch_calls<br/>Ghi số lượng tool call<br/>Phát một ToolCallEvent cho mỗi call]
    DISPATCH --> EXEC[call_tool: tìm tool theo tên<br/>await tool.acall với arguments từ LLM<br/>Chi tiết SQL và RAG ở sơ đồ 2]
    EXEC --> TOOLMSG[ToolCallEventResult<br/>Chuẩn hóa nội dung thành role=tool<br/>Gắn tool_call_id, tên tool, tool_used<br/>Gắn is_error nếu tool lỗi]
    TOOLMSG --> GATHER{gather: đủ kết quả<br/>của tất cả call trong batch?}
    GATHER -->|Chưa| WAIT[Chờ các kết quả còn lại]
    WAIT --> GATHER
    GATHER -->|Đủ| APPEND[Thêm các tool message vào chat_history]
    APPEND --> CHAT
    MISSING --> PACK
    FINAL --> PACK
    PACK[collect_tool_results chỉ lấy lượt hiện tại<br/>Tạo ChatMessage: id, role, content, tools, duration_ms<br/>Lưu user và assistant vào session.messages<br/>Cập nhật touched, nhả session.lock] --> OK[HTTP 200: JSON câu trả lời]
    OK --> UI[React thêm user và assistant vào messages<br/>Hiển thị Markdown, thời gian, kết quả tool<br/>Xóa pending và busy]
    H422 --> UIERR
    H404 --> UIERR
    H400 --> UIERR
    HTTP -. Lỗi mạng .-> UIERR
    RUN -. Exception thoát khỏi workflow .-> ROLLBACK[Xóa chat_history từ turn_start<br/>Không lưu lượt thất bại vào session.messages]
    ROLLBACK --> ERRTYPE{Loại exception?}
    ERRTYPE -->|TimeoutError hoặc asyncio.TimeoutError| H504[HTTP 504]
    ERRTYPE -->|Exception khác| H502[HTTP 502]
    ERRTYPE -->|CancelledError| CANCEL([Ném lại cancellation])
    H504 --> UIERR
    H502 --> UIERR
    UIERR[Hiển thị lỗi, xóa pending và busy<br/>Khôi phục query vào ô nhập để gửi lại<br/>Riêng 404: xóa session và sessionStorage]
```

`prepare_chat` còn kiểm tra `message is None` và ném `ValueError`; đường HTTP hợp lệ đã có `ChatRequest`, nên bình thường không tới nhánh này.

## 2. Bên trong từng tool

Mỗi tool call chọn một tool theo tên; một batch có thể chứa SQL, document hoặc cả hai. Tool call dùng câu hỏi/arguments do router LLM sinh, không nhất thiết dùng nguyên văn query UI.

```mermaid
flowchart TD
    START([Một ToolCallEvent]) --> LOOKUP{Tên tool có trong tools_dict?}
    LOOKUP -->|Không| UNAVAILABLE[Tool error: tool không khả dụng<br/>Nếu document_tool: yêu cầu upload tài liệu]
    LOOKUP -->|Có| TYPE{Tool nào?}

    subgraph SQL[sql_tool — 6 bảng bán hàng]
        SCHEMA[QueryEngineTool.acall<br/>NLSQLTableQueryEngine.aquery<br/>Lấy schema bán hàng và dialect SQLite]
        SCHEMA --> GEN[LLM chuyển câu hỏi + schema thành SQL]
        GEN --> PARSESQL[SQL parser lấy câu SQL từ output LLM]
        PARSESQL --> DB[SQLRetriever thực thi SQL trên SQLite]
        DB --> DBOK{Thực thi thành công?}
        DBOK -->|Có| ROWS[Kết quả truy vấn và metadata]
        DBOK -->|Không| SQLERR[LlamaIndex mặc định handle_sql_errors=True<br/>Chuyển lỗi SQL thành node chứa Error]
        ROWS --> SQLSYN[LLM tổng hợp câu trả lời từ các node<br/>synthesize_response mặc định True]
        SQLERR --> SQLSYN
        SQLSYN --> SQLOUT[ToolOutput: nội dung câu trả lời SQL]
    end

    subgraph RAG[document_tool — tài liệu đã upload]
        WORKER[document_query_tool query<br/>Chạy query_documents trong asyncio.to_thread]
        WORKER --> CACHE[RetrievalCache.get<br/>Khóa cache và xóa entry hết TTL]
        CACHE --> HIT{Exact query còn trong cache?}
        HIT -->|Có| COPIES[Đưa entry lên cuối LRU<br/>Trả deepcopy của các nodes đã lưu]
        HIT -->|Không| EMBED[Embed câu hỏi bằng model của document index<br/>Mặc định BAAI/bge-small-en-v1.5]
        EMBED --> HYBRID[Milvus hybrid search<br/>Dense semantic vector + sparse BM25 keyword query]
        HYBRID --> RRF[RRFRanker hợp nhất và xếp hạng<br/>similarity_top_k=3]
        RRF --> STORE[Lưu deepcopy nodes vào cache<br/>TTL 300 giây, tối đa 128 entry<br/>Vượt giới hạn: bỏ entry LRU]
        STORE --> SYN
        COPIES --> SYN[docs_query_engine.synthesize<br/>QueryBundle query + nodes + QA prompt<br/>LLM tạo câu trả lời mới trong mỗi lần gọi]
        SYN --> DOCOUT[Dictionary response chứa câu trả lời<br/>FunctionTool đóng gói thành ToolOutput]
    end

    TYPE -->|sql_tool| SCHEMA
    TYPE -->|document_tool| WORKER
    SQLOUT --> NORMALIZE
    DOCOUT --> NORMALIZE
    NORMALIZE[call_tool chuẩn hóa output<br/>Dictionary có response: lấy response<br/>Các output khác: chuyển thành chuỗi] --> RESULT([role=tool → gather])
    UNAVAILABLE --> ERROR
    TYPE -. Exception hoặc cancellation thoát ra ngoài tool .-> ERROR
    ERROR[role=tool với is_error=True<br/>Giữ tool_call_id và tên tool] --> RESULT
```

Lỗi retrieval không được cache; retrieval thành công nhưng không có nodes vẫn được cache. Cache thuộc một document index, nên upload thành công tạo tool/index/cache mới. SQL dùng `SQLOnlyEmbedding` để tắt vector embedding, không đi qua Milvus.

## 3. Lỗi được bắt bên trong workflow

```mermaid
flowchart TD
    CHAT[chat: gọi router LLM và xử lý response] --> CHK{Có exception?}
    CHK -->|AuthenticationError| AUTH[StopEvent: báo lỗi xác thực OpenRouter<br/>Yêu cầu nhập API key hợp lệ]
    CHK -->|CancelledError bị bắt ở chat| CANCEL[StopEvent: thông báo thao tác bị hủy]
    CHK -->|Exception khác| OTHER[StopEvent: thông báo lỗi xử lý câu hỏi]
    TOOL[call_tool: tìm và thực thi tool] --> THK{Có lỗi?}
    THK -->|ToolOutput.is_error hoặc exception hoặc cancellation| TMSG[Tool message với is_error=True]
    TMSG --> GATHER[gather chờ đủ batch và lưu tool messages]
    GATHER --> LOOP[Quay lại chat<br/>Tool message lỗi vẫn được tính là đã có tool result]
    GATHER -. Exception trong gather .-> GERR[StopEvent: báo lỗi xử lý kết quả tool]
    AUTH --> RETURN
    CANCEL --> RETURN
    OTHER --> RETURN
    GERR --> RETURN
    RETURN[Service coi StopEvent là kết quả của lượt<br/>Lưu messages và trả HTTP 200<br/>Nội dung câu trả lời mang thông báo lỗi]
```

## Những điều cần đọc đúng trên sơ đồ

- Session mới luôn có `sql_tool`; `document_tool` chỉ xuất hiện sau upload và xây index thành công. Upload/indexing là bước chuẩn bị riêng, không chạy lại trong mỗi query.
- Router phân loại bằng LLM và tool descriptions/system prompt. Không có `if` kiểm tra keyword để quyết định SQL hay RAG. Prompt yêu cầu dùng lịch sử để tạo câu hỏi tự đủ ngữ cảnh và giữ ngôn ngữ của user; đây là hướng dẫn cho LLM.
- `needs_tool` dựa trên việc có tool và có role=`tool` trong lượt hiện tại. Khi có tool, lần gọi router đầu tiên bị yêu cầu gọi tool cho mọi query. Kết quả tool của lượt cũ không bỏ qua yêu cầu này; tool message lỗi trong lượt hiện tại vẫn làm yêu cầu này chuyển thành False.
- Mọi batch kết quả tool đều quay lại router. Router có thể đọc chính sách qua RAG rồi gọi SQL, hoặc đọc đơn hàng qua SQL rồi tra chính sách; chỉ trả lời khi đủ dữ kiện hoặc báo thông tin còn thiếu.
- Không có bước kiểm tra điểm tin cậy, ngưỡng relevance hay nhánh `if context đủ` trong application code. QA prompt yêu cầu LLM chỉ dùng context và báo thiếu thông tin. SQL error được thư viện chuyển thành node không tự động có `ToolOutput.is_error=True`.
- `dispatch_calls` phát nhiều event, không tự `asyncio.gather`. Bản workflow library đang cài mặc định có 4 worker mỗi step, nên có thể xử lý tool call đồng thời. `gather` chờ đủ số lượng call trong batch.
- Không có giới hạn số vòng agent/tool call trong code này. Workflow và `asyncio.wait_for` cùng dùng `query_timeout` (mặc định 60 giây). Thời gian chờ `session.lock` nằm ngoài đồng hồ này và ngoài `duration_ms`.
- HTTP 504 chỉ áp dụng khi service bắt `TimeoutError`/`asyncio.TimeoutError`. `WorkflowTimeoutError` của thư viện đang cài kế thừa `Exception`; nếu lỗi này thoát ra trước outer timeout, service trả 502 theo nhánh exception khác.
- API trả một JSON sau khi hoàn thành; không có streaming token. Lỗi được workflow đổi thành `StopEvent` thường vẫn trả 200; exception thoát khỏi workflow mới đi nhánh rollback/HTTP error.

## Nguồn code

| Phần | File / hàm |
| --- | --- |
| Submit, pending, render kết quả | `frontend/src/components/ChatView.jsx`: `submit`, `Answer` |
| Khóa thao tác, gọi API, xử lý lỗi | `frontend/src/hooks/useWorkspace.js`: `perform`, `send` |
| HTTP client | `frontend/src/lib/api.js`: `request`, `api.chat` |
| Endpoint và validation | `backend/api.py`: `chat`; `backend/schemas.py`: `ChatRequest`, `ChatMessage` |
| Session, lock, timeout, rollback | `backend/service.py`: `get`, `chat`, `create`, `upload` |
| Vòng agent và tổng hợp kết quả | `backend/rag/workflow.py`: `prepare_chat`, `chat`, `dispatch_calls`, `call_tool`, `gather` |
| SQL/RAG engine và QA prompt | `backend/rag/tools.py`: `setup_sql_tool`, `setup_document_tool`, `document_query_tool` |
| Cache context | `backend/rag/retrieval_cache.py`: `RetrievalCache.get` |
| Tắt embedding cho SQL | `backend/rag/sql_embedding.py`: `SQLOnlyEmbedding` |
| Metadata của lượt hiện tại | `backend/serialization.py`: `collect_tool_results` |
| Mặc định và cấu hình môi trường | `backend/config.py`: `AppConfig` |
| SQL engine/retriever thực tế | `.venv/Lib/site-packages/llama_index/core/indices/struct_store/sql_query.py`, `sql_retriever.py` |
| Tool SQL và worker/timeout của library | `.venv/Lib/site-packages/llama_index/core/tools/query_engine.py`, `.venv/Lib/site-packages/workflows/decorators.py`, `errors.py` |

Đây là tài liệu từ việc đọc source và dependency đang cài, không phải báo cáo chạy query live với OpenRouter/Milvus.
