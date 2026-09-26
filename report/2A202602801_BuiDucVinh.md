# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Bùi Đức Vinh               |
| MSSV               | 2A202602801                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Sydneybadboy               |
| Vai trò chính    | Trưởng nhóm — Corruption & Integration owner |
| Repository         | https://github.com/DucVinhBui/K4-Day10-Sydneybadboy |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Corruption suite | `src/ingestion/corruption.py`: `corrupt_clean_dataframe`, `_inject_noise`, `_take` | Clean DataFrame | `data/clean/papers_clean_corrupted.{csv,json}`, `data/results/corruption_log.json` | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py`: `main`, `load_or_build_test_set`, `run_agent_demo` | Settings, raw snapshot | Toàn bộ artifact Phase 1, `baseline_metrics.json`, `agent_demo_answers.json` | Hoàn thành |
| Corruption → repair orchestration | `src/pipelines/corruption_flow.py`: `main`, `repair_from_raw`, `_needs_repair`, `_dataset_fingerprint` | Artifact Phase 1 | `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_report.md`, `dashboard.html` | Hoàn thành |
| Vector index portability | `src/retrieval/index.py`: `_portable_path`, `load` | — | Manifest `data/embeddings/*.json` dùng `persist_path: "data/chroma"` | Hoàn thành |
| Môi trường & CI | `uv.lock`, `pyproject.toml` (pytest config), `.github/workflows/tests.yml` | — | `.venv` tái lập bằng `uv sync --frozen --extra dev` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Thống nhất contract: corruption dùng lại `refresh_derived_columns` | Bùi Đức Thông — `cleaning.py` | `text_for_embedding` của dữ liệu hỏng dựng lại nhất quán |
| Tích hợp `trigger_reasons` từ report GX | Đỗ Phúc Hưng — `quality.py` | Auto-repair đọc trực tiếp `failed_expectations` |
| Điền `docs/TEAM.md`, `report/group_report.md` | Cả nhóm | Số liệu khớp `data/results/`, `data/quality/` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tiêm 6 lỗi, seed 42, các tập dòng rời nhau | `corruption.py` | 24 → 22 dòng; log đủ 6 loại lỗi kèm DOI | `test_corruption_injects_six_types_and_is_detected`, `test_corruption_is_deterministic` |
| Phase 1 end-to-end với gate chặn index | `phase1.py` | Hit Rate 1.0, F1 1.0, `phase1_report.md` | `uv run python script/run_phase1.py` (exit 0) |
| Phase 2 corruption → evaluate → auto-repair → so sánh | `corruption_flow.py` | Bảng 3 trạng thái; `matches_baseline = True`; `idempotent_rerun_identical = True` | `uv run python script/run_corruption_flow.py` (exit 0) |
| Làm manifest index portable | `index.py` | Không còn đường dẫn tuyệt đối trong `data/` | `test_index_manifest_is_portable_and_loadable`; `grep -rl "$HOME" data src` rỗng |

Output cụ thể, bảng console cuối Phase 2:

```text
Metric                        Baseline   Corrupted    Repaired
Retrieval Hit Rate              1.0000      0.8000      1.0000
Mean Token F1                   1.0000      0.8842      1.0000
Judge Accuracy                  1.0000      0.9000      1.0000
Mean Judge Score (1-5)          5.0000      4.4000      5.0000
```

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần chứng minh được một chuỗi nhân quả: dữ liệu hỏng → các tín hiệu observability báo động → agent suy giảm nhưng không báo lỗi → repair đúng cách → phục hồi. Mỗi bước phải tái lập được và đo trên cùng một test set.

### Cách triển khai

- **Corruption:** sắp theo `published` giảm dần và bỏ 20% đầu (`ceil(24×0.2) = 5`). Từ 19 dòng còn lại, bốc bằng `random.Random(42)` các tập **rời nhau**: 3 blank summary, 3 noise, 3 truncate title (7 ký tự), 6 stale date (−365 ngày, cộng 365 vào `age_days`). Sau đó nhân bản 3 dòng. Vì tập rời nhau, mỗi loại lỗi đều có thể quan sát riêng. Log lưu DOI, giá trị gốc (title, ngày) để đối chiếu.
- **Phase 1:** chạy Quality Gate *trước* khi build index; `success = False` thì raise và không nạp Chroma. Test set được tái sử dụng nếu mọi ground-truth DOI còn trong corpus. Agent demo thử `create_agent` với tool calling; với provider `mock` hoặc khi thiếu key thì fallback sang QA trích xuất, và ghi `mode` vào `agent_demo_answers.json`.
- **Phase 2:** cố ý bỏ qua gate để index dữ liệu hỏng vào collection riêng `papers-corrupted`, nhằm đo silent failure. `_needs_repair` gom các expectation fail cùng vi phạm Freshness thành `trigger_reasons`. Repair gọi `load_raw_records` rồi `build_clean_dataframe` (chạy 2 lần), kiểm lại gate (vẫn fail thì raise), index vào `papers-repaired` và evaluate trên cùng test set.
- **Idempotency:** fingerprint = SHA-256 của dataset dạng JSON, bỏ cột `age_days` (vì cột này phụ thuộc ngày chạy). So sánh repaired với baseline, và lần repair 1 với lần 2.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `data/clean/papers_clean.json`, `data/results/baseline_metrics.json`, `data/eval/test_set.json`, `data/raw/crossref_records.json` |
| Output | `corruption_log.json`, `corrupted_/repaired_metrics.json`, `*_answers.json`, `corruption_report.md`, `dashboard.html`, 3 Chroma collections |
| Module phụ thuộc | `ingestion/*`, `observability/*`, `retrieval/index.py`, `evaluation/metrics.py` |
| Module sử dụng output | Báo cáo nhóm, live demo CP6 |
| Điều kiện lỗi cần xử lý | Thiếu artifact Phase 1 (raise với hướng dẫn chạy Phase 1), repair vẫn fail gate, agent không khả dụng |

### Cách xác minh

```bash
uv sync --frozen --extra dev
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run pytest -q
```

- **Kết quả mong đợi:** hai lệnh exit 0, bảng 3 trạng thái, repaired = baseline.
- **Kết quả thực tế:** như bảng ở mục 3; `repair_summary` có `matches_baseline: True`, `idempotent_rerun_identical: True`; `15 passed`. Chạy lại toàn bộ flow nhiều lần cho cùng metric.
- **Artifact/log:** `data/results/`, `data/reports/corruption_report.md`, `data/reports/dashboard.html`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Repair dữ liệu hỏng bằng cách nào?
- **Các phương án đã cân nhắc:** (1) Vá tại chỗ: `drop_duplicates`, lọc summary rỗng, loại dòng có ký tự rác. (2) Rollback về `papers_clean.json` của baseline. (3) Tái tạo từ raw snapshot bất biến bằng đúng code cleaning.
- **Phương án đã chọn:** (3).
- **Lý do:** (1) không khôi phục được dữ liệu đã mất (5 bài mới nhất, title bị cắt, ngày bị lùi), chỉ che triệu chứng. (2) phụ thuộc vào một artifact trung gian có thể đã bị ghi đè. (3) chạy lại bao nhiêu lần cũng cho cùng kết quả, không cần sửa tay, và dùng cùng một code path với baseline.
- **Bằng chứng quyết định phù hợp:** trong `corruption_report.md`, `repaired_fingerprint = baseline_fingerprint`, `idempotent_rerun_identical = True`, và 4 metric trở về 1.0/5.0.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Các file manifest `data/embeddings/papers_embeddings*.json` chứa `persist_path` là đường dẫn tuyệt đối tới `data/chroma` trên máy cá nhân. `LocalEmbeddingIndex.load` đọc đường dẫn này nên trên máy giám khảo sẽ trỏ tới thư mục không tồn tại. Rubric cũng trừ 5 điểm nếu hardcode đường dẫn tuyệt đối.
- **Lệnh hoặc bước tái hiện:** `grep -rl "$HOME" data src` sau khi chạy Phase 1.
- **Nguyên nhân gốc:** `LocalEmbeddingIndex.build` ghi `str(persist_path)`, mà `persist_path` đến từ `settings.paths.chroma_dir` (đã được `resolve()` thành đường dẫn tuyệt đối).
- **Cách xử lý:** thêm `_portable_path`, ghi đường dẫn tương đối so với `project_dir` (`data/chroma`); `load` ghép lại với `settings.paths.project_dir` khi đường dẫn không tuyệt đối.
- **Cách xác minh sau khi sửa:** `grep -rl "$HOME" data src tests script` không còn kết quả; `test_index_manifest_is_portable_and_loadable` load lại index và đếm đủ 24 document.
- **Điều học được:** Artifact được commit cũng là "code" chạy trên máy người khác, nên phải kiểm tra tính portable của cả dữ liệu, không chỉ mã nguồn.

Hai blocker môi trường khác cũng đã xử lý: `pip install -e .` bị kẹt ở bước giải dependency hơn 10 phút, nên chuyển sang `uv sync --frozen` theo `uv.lock`. Tải model MiniLM từng lỗi `httpx.RemoteProtocolError: Server disconnected without sending a response.`; tải lại bằng `huggingface_hub.snapshot_download` có retry thì được.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. `fetch_source_records` lấy snapshot (hoặc gọi live API), lưu raw và parse. Cleaning dựng bảng 16 cột. Gate GX pass thì `LocalEmbeddingIndex.build` encode `text_for_embedding` bằng MiniLM (vector đã chuẩn hóa) và ghi vào collection cosine `papers-baseline`.
2. `answer_question` tra đúng tiêu đề trong dấu nháy trước (exact lookup), sau đó mới semantic search top-4. Hit Rate đo xem DOI ground truth có trong danh sách retrieved không; F1 và judge đo câu trả lời trích xuất từ tài liệu top-1.
3. GX là kiểm tra hợp lệ theo từng giá trị, có ngưỡng cứng. Freshness là kiểm tra thống kê theo thời gian trên cả tập. Trong Phase 2, riêng `drop_latest_records` và `stale_date` không làm fail expectation nào của GX; tín hiệu của chúng nằm ở Freshness (`latest_published` lùi, stale ratio vượt ngưỡng).
4. Cùng test set thì delta chỉ đến từ dữ liệu. Phase 2 cũng kiểm tra điều kiện này: báo lỗi nếu thiếu `test_set.json` thay vì tự sinh test set mới.
5. Repair thành công dựa trên: GX 8/8, FRESH, metric bằng baseline, fingerprint bằng baseline và idempotent.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Đúng bằng 2/10 câu có tài liệu nằm trong nhóm bị drop |
| `mean_token_f1`      | 1.0000 | 0.8842 | 1.0000 | Giảm ít hơn Hit Rate: eval_002 miss nhưng F1 vẫn 1.0 |
| `judge_accuracy`     | 1.0000 | 0.9000 | 1.0000 |  |
| `mean_judge_score`   | 5.0000 | 4.4000 | 5.0000 |  |
| Quality checks         | 8/8 | 4/8 | 8/8 | Là nguồn `trigger_reasons` cho auto-repair |
| Freshness status       | FRESH | STALE_ALERT | FRESH |  |

### Kết luận từ số liệu

1. `drop_latest_records` + `duplicate_rows` → Freshness `latest_age_days` 65 → 105, GX unique fail → eval_002 retrieval miss nhưng câu trả lời vẫn đúng: silent failure điển hình. Agent đang dựa trên nguồn sai mà không metric câu trả lời nào phát hiện.
2. `repair_from_raw` → GX 8/8, FRESH, fingerprint trùng baseline → cả 4 metric phục hồi 100%.

Corruption ảnh hưởng rõ nhất là **drop latest records**: nó gây ra toàn bộ phần giảm Hit Rate (−0.2), và một phần giảm F1 (eval_001).

Kết quả khác kỳ vọng: `duplicate_rows` không làm giảm Hit Rate như dự đoán. Bản trùng chiếm chỗ trong top-4, nhưng exact lookup theo tiêu đề vẫn đưa tài liệu đúng lên đầu. Mình kiểm tra bằng `retrieved_doc_ids` trong `data/results/corrupted_answers.json`.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline tốt phải tái lập được: dùng seed cố định, raw bất biến, lockfile (`uv.lock`) và artifact portable.
2. Observability chỉ có giá trị khi được nối vào hành động: gate chặn index ở Phase 1, và vi phạm kích hoạt repair ở Phase 2.
3. Dữ liệu sai làm RAG trả lời sai một cách tự tin; không có exception nào được ném ra trong suốt flow corrupted.

### Nếu có thêm thời gian

Mình sẽ chạy với LLM thật (Gemini) cho cả judge lẫn agent để thay heuristic judge, rồi so `judge_accuracy` giữa hai chế độ. Mình kỳ vọng câu trả lời nhiễu (eval_005) sẽ bị LLM judge chấm thấp hơn mức 3/5 của heuristic.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Đức Vinh
**Ngày xác nhận:** 2026-09-25
