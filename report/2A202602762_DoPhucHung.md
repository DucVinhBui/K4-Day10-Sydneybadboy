# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Đỗ Phúc Hưng               |
| MSSV               | 2A202602762                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Sydneybadboy               |
| Vai trò chính    | Evaluation & Observability owner |
| Repository         | https://github.com/DucVinhBui/K4-Day10-Sydneybadboy |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Quality Gate GX 1.x | `src/observability/quality.py`: `run_data_quality_checks`, `_build_expectations` | Clean/corrupted/repaired DataFrame | `data/quality/{baseline,corrupted,repaired}_quality_report.json` | Hoàn thành |
| Freshness SLA | `build_freshness_report`, `_stale_stats` | DataFrame có `published`, `age_days` | `data/quality/freshness_report.json`, `corrupted_/repaired_freshness_report.json` | Hoàn thành |
| Evaluation set | `src/evaluation/testset.py`: `build_test_set` | Clean DataFrame | `data/eval/test_set.json` (10 câu) | Hoàn thành |
| Reporting | `src/observability/reporting.py`; breakdown theo `question_type` trong `evaluation/metrics.py` | Metrics, quality, freshness, corruption log | `data/reports/phase1_report.md`, `data/reports/corruption_report.md`, bảng in console | Hoàn thành |
| Dashboard (bonus B1) | `src/observability/dashboard.py`, `script/build_dashboard.py` | Các artifact JSON | `data/reports/dashboard.html` | Hoàn thành |
| Test suite (bonus B3) | `tests/` | Raw snapshot (project tạm) | 15 test pytest | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Đối chiếu số liệu trong `group_report.md` với `data/results/*.json` | Bùi Đức Vinh — tích hợp | Mọi số trong bảng 3 trạng thái khớp artifact |
| Viết test cho parse/cleaning | Bùi Đức Thông | `test_ingestion.py`, `test_cleaning.py` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Dựng suite 8 expectations trên ephemeral context | `quality.py` | Baseline 8/8 pass, corrupted 4/8, repaired 8/8 | Lệnh CP1 in `Quality check status = True`; `test_corruption_injects_six_types_and_is_detected` |
| Freshness SLA | `build_freshness_report` | Baseline FRESH (0.0417), corrupted STALE_ALERT (0.2727) | `test_freshness_report_on_clean_data` |
| Sinh 10 câu hỏi 4 nhóm | `testset.py` | summary 3, authors 3, date 2, categories 2 | Lệnh CP2 in `Sinh được 10 câu hỏi test` |
| Báo cáo 3 trạng thái + dashboard | `reporting.py`, `dashboard.py` | `corruption_report.md`, `dashboard.html` | Mở file; bảng console cuối `run_corruption_flow.py` |

Output cụ thể: `data/quality/corrupted_quality_report.json` ghi đúng 4 expectation fail, gồm `expect_column_values_to_be_unique(paper_id)` (6 giá trị trùng), `expect_column_value_lengths_to_be_between(title)` (4), `expect_column_value_lengths_to_be_between(summary)` (3) và `expect_column_values_to_not_match_regex(summary)` (4). Danh sách này cũng chính là `trigger_reasons` kích hoạt auto-repair.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Silent failure: agent vẫn trả lời trơn tru trên dữ liệu hỏng. Phần của mình tạo ra các tín hiệu độc lập với agent để phát hiện dữ liệu xấu trước khi nó vào vector store (Quality Gate, Freshness), và dựng một thước đo cố định (test set) để lượng hóa thiệt hại.

### Cách triển khai

- **GX 1.x:** `gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch(batch_parameters={"dataframe": df})` → `ExpectationSuite` → `batch.validate(suite)`. Không dùng cú pháp cũ `context.sources.pandas_default`.
- **Expectations:** 4 cái bắt buộc (row count 5–5000; not null `paper_id`/`title`/`text_for_embedding`; unique `paper_id`; summary ≥ 30 ký tự) và 2 cái mở rộng: title ≥ 8 ký tự, summary không khớp regex `(?:�|[#@!%&~]{3,}|0x[0-9A-Fa-f]{6,})`. Không có 2 cái mở rộng thì `truncate_title` và `inject_noise` sẽ lọt qua gate.
- **Cột list:** trên bản sao dùng để validate, `authors`/`categories` được đổi sang chuỗi, để pandas engine của GX xử lý như cột text thông thường.
- **Freshness:** `stale_ratio = #(age_days > 180) / total`, cảnh báo khi ratio > 0.25. Report kèm `latest_published`, `latest_age_days` để phát hiện mất dữ liệu mới.
- **Test set:** lọc paper có tiêu đề không chứa dấu `'` (vì `qa.py` trích tiêu đề bằng regex `'...'`), sắp theo ngày, chọn 10 vị trí trải đều từ mới nhất tới cũ nhất, gán lần lượt các loại câu hỏi. Ground truth dùng đúng format mà `qa.py` trả về (`first_sentence(summary)`, `authors_joined`, ...).

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | DataFrame theo `CLEAN_COLUMNS`; `Settings` (paths, `freshness_threshold_days`) |
| Output | Dict `{success, expectations_passed/total, failed_expectations, checks[], freshness}`; JSON trong `data/quality/`; `test_set.json` gồm `id, question_type, question, ground_truth, ground_truth_doc_ids` |
| Module phụ thuộc | `ingestion/cleaning.py` (schema), `retrieval/qa.py` (format câu hỏi/câu trả lời) |
| Module sử dụng output | `pipelines/phase1.py` (gate chặn index), `pipelines/corruption_flow.py` (trigger repair), `evaluation/metrics.py` |
| Điều kiện lỗi cần xử lý | Ít hơn 10 document, tiêu đề chứa `'`, `age_days` không phải số, DataFrame rỗng |

### Cách xác minh

```bash
uv run python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Tín hiệu hoàn thành: Quality check status = {res[\"success\"]}')"
uv run python -c "from core.config import load_settings; from evaluation.testset import build_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=build_test_set(df, s.paths.eval_testset); print(f'Tín hiệu hoàn thành: Sinh được {len(ts)} câu hỏi test')"
uv run pytest -q
```

- **Kết quả mong đợi:** `True`, `10`, toàn bộ test pass.
- **Kết quả thực tế:** `Quality check status = True`, `Sinh được 10 câu hỏi test`, `15 passed`.
- **Artifact/log:** `data/quality/`, `data/eval/test_set.json`, `data/reports/`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `success` của Quality Gate có nên gộp cả Freshness hay không?
- **Các phương án đã cân nhắc:** (1) `success = GX pass AND is_fresh`. (2) `success` chỉ phản ánh GX; Freshness là một tín hiệu riêng (`freshness.is_fresh`, `status`).
- **Phương án đã chọn:** (2).
- **Lý do:** `age_days` phụ thuộc ngày chạy. Snapshot cố định sẽ tự thành "stale" sau vài tháng dù dữ liệu không đổi. Nếu gộp, Phase 1 sẽ từ chối index dữ liệu hợp lệ khi giám khảo chạy vào ngày khác. Tách riêng thì gate chặn dữ liệu *sai*, còn Freshness cảnh báo dữ liệu *cũ*; cả hai vẫn cùng kích hoạt auto-repair.
- **Bằng chứng quyết định phù hợp:** Baseline hiện có 1/24 bài 181 ngày tuổi (sát ngưỡng). `test_freshness_report_on_clean_data` cố định `RUN_DATE = 2026-09-25` để kết quả kiểm thử không trôi theo ngày chạy.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi chạy pytest, GX in cảnh báo: `UserWarning: This pattern is interpreted as a regular expression, and has match groups. To actually get the groups, use str.extract.` (từ `column_values_not_match_regex.py`). Ngoài ra, mỗi lần validate log bị ngập bởi thanh tiến trình `Calculating Metrics: ...`.
- **Lệnh hoặc bước tái hiện:** `uv run pytest -q` với regex ban đầu `(�|[#@!%&~]{3,}|0x...)`, và `uv run python script/run_phase1.py`.
- **Nguyên nhân gốc:** GX dùng `Series.str.contains(regex)`; pandas cảnh báo khi pattern có capturing group. Thanh tiến trình bật mặc định trong ephemeral context.
- **Cách xử lý:** Đổi sang non-capturing group `(?:...)`; đặt `context.variables.progress_bars = ProgressBarsConfig(globally=False)`.
- **Cách xác minh sau khi sửa:** `uv run pytest -q` → `15 passed` không còn warning; log Phase 1 chỉ còn các dòng `[phase1] ...`.
- **Điều học được:** Warning từ thư viện validate phải được xử lý triệt để, vì đó thường là dấu hiệu expectation không làm đúng điều mình tưởng.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Raw JSON từ Crossref được parse thành record, rồi làm sạch thành bảng có `text_for_embedding`. Bảng này phải qua gate GX của mình trước; pass mới được embed bằng MiniLM và ghi vào ChromaDB.
2. Mỗi câu hỏi mang theo DOI đúng. `metrics.py` so DOI với danh sách top-4 để tính Hit Rate (retrieval), và so câu trả lời với ground truth để tính Token F1 và judge (answer).
3. GX trả lời câu hỏi "dữ liệu có hợp lệ không" theo từng dòng/cột. Freshness trả lời câu hỏi "dữ liệu có còn mới không" theo phân bố thời gian của cả tập. Trong bài lab, `stale_date` hoàn toàn hợp lệ với GX nhưng bị Freshness bắt.
4. Dùng chung test set thì biến duy nhất thay đổi là dữ liệu, nên delta metric mới chứng minh được tác động của corruption và repair.
5. Repair thành công khi `repaired_quality_report.json` có `success: true` (8/8), `repaired_freshness_report.json` là `FRESH`, và `repaired_metrics.json` bằng `baseline_metrics.json`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Breakdown: authors 0.67, summary 0.67 khi corrupted |
| `mean_token_f1`      | 1.0000 | 0.8842 | 1.0000 | Summary F1 còn 0.614; authors/date/categories giữ 1.0 |
| `judge_accuracy`     | 1.0000 | 0.9000 | 1.0000 | Heuristic judge vì provider là mock |
| `mean_judge_score`   | 5.0000 | 4.4000 | 5.0000 | Câu nhiễu được 3 điểm, câu rỗng được 1 điểm |
| Quality checks         | 8/8 | 4/8 | 8/8 | 2 expectation mở rộng đóng góp 2 trong 4 lỗi |
| Freshness status       | FRESH | STALE_ALERT | FRESH | 6/22 dòng stale sau `stale_date` |

### Kết luận từ số liệu

1. `inject_noise` → GX regex fail (4 dòng) → eval_005 trả lời bắt đầu bằng `~~~ 0xDEADBEEF ...`, F1 0.84, judge 3/5: vẫn tính là "đúng" dù câu trả lời lẫn rác.
2. Repair từ raw → GX 8/8, FRESH → breakdown mọi `question_type` về 1.0.

Corruption ảnh hưởng rõ nhất là **blank summary** kết hợp **drop latest**: eval_001 vừa mất tài liệu gốc, vừa được trả lời bằng bài có summary rỗng, nên câu trả lời rỗng (F1 0, judge 1).

Kết quả khác kỳ vọng: Token F1 dạng tập hợp khá "dễ dãi" với nhiễu. Chèn rác mỗi 2 từ mà F1 vẫn 0.84, vì mọi token đúng vẫn có mặt và chỉ precision giảm. Nghĩa là metric câu trả lời không đủ để phát hiện dữ liệu bẩn; cần GX regex.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Gate phải đứng *trước* vector store: Phase 1 raise lỗi và không index khi `success = False`.
2. Chỉ 4 expectation bắt buộc là chưa đủ: chúng không bắt được `truncate_title` và `inject_noise`. Cần thiết kế expectation dựa trên các failure mode dự kiến.
3. Benchmark 10 câu chỉ phủ 10/24 paper, nên các lỗi trên paper ngoài test set (stale date, truncate title) "vô hình" với metric RAG.

### Nếu có thêm thời gian

Mình sẽ sinh test set phủ toàn bộ 24 paper × 4 loại câu hỏi (96 câu) và so lại delta của `stale_date`. Cách đo: F1 của nhóm `date` phải giảm tương ứng với 6/24 bài bị lùi ngày.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đỗ Phúc Hưng
**Ngày xác nhận:** 2026-09-25
