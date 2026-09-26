# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Sydneybadboy               |
| Repository         | https://github.com/DucVinhBui/K4-Day10-Sydneybadboy |
| Ngày hoàn thành | 2026-09-25                 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Bùi Đức Vinh | 2A202602801 | Trưởng nhóm, Corruption & Integration owner | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `src/retrieval/index.py`, môi trường `uv` + CI |
| 2 | Bùi Đức Thông | 2A202602931 | Data Ingestion & Cleaning owner | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, `data/raw/`, `data/clean/` |
| 3 | Đỗ Phúc Hưng | 2A202602762 | Evaluation & Observability owner | `src/evaluation/testset.py`, `src/observability/quality.py`, `reporting.py`, `dashboard.py`, `tests/` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm đã hoàn thành toàn bộ 7 tầng của pipeline: ingestion từ Crossref (live API có retry/backoff cho 429/5xx, tự fallback về snapshot offline), cleaning & data model (`text_for_embedding` 5 phần, `age_days`, khử trùng lặp theo `paper_id`), Quality Gate chuẩn Great Expectations 1.x (ephemeral context, 8 expectations) kèm Freshness SLA, embedding MiniLM + ChromaDB, benchmark 10 câu hỏi trên 4 nhóm nghiệp vụ, bộ 6 corruption có seed cố định, và repair idempotent từ raw snapshot.

Baseline đạt Hit Rate = 1.0, Token F1 = 1.0 trên 24 tài liệu. Khi tiêm lỗi, Quality Gate fail 4/8 expectations (duplicate `paper_id`, title bị cắt, summary rỗng, summary chứa ký tự rác) và Freshness chuyển sang `STALE_ALERT` (stale ratio 0.2727 > 0.25). Agent **không hề báo lỗi** nhưng Hit Rate giảm còn 0.80, Token F1 còn 0.8842 — đúng hiện tượng silent failure. Corruption gây hại rõ nhất là **drop latest records** (làm mất 2/10 tài liệu ground-truth) và **blank summary** (trả lời rỗng). Repair tái tạo từ `data/raw/crossref_records.json` cho fingerprint trùng khớp baseline, chạy lại 2 lần cho kết quả giống hệt nhau, và phục hồi 100% cả 4 metric.

Giới hạn chính: pipeline chạy với `LLM_PROVIDER=mock` (không có API key), nên `judge_accuracy`/`mean_judge_score` đến từ heuristic judge dựa trên Token F1 thay vì LLM judge thật; QA dùng trích xuất từ metadata nên baseline đạt tuyệt đối 1.0.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (REFRESH_SOURCE=1)  ──fail/429──►  snapshot data/raw/crossref_response.json
    -> parse_crossref_payload -> data/raw/crossref_records.json          (raw lineage)
    -> build_clean_dataframe  -> data/clean/papers_clean.{csv,json}
    -> GX 1.x Quality Gate + Freshness -> data/quality/*.json            (gate chặn index nếu fail)
    -> MiniLM + ChromaDB (papers-baseline) -> evaluate -> baseline_metrics.json, phase1_report.md
    -> corrupt_clean_dataframe (6 lỗi, seed 42) -> corruption_log.json
    -> GX + Freshness trên dữ liệu hỏng (FAIL) -> bypass gate có chủ đích để đo silent failure
    -> ChromaDB (papers-corrupted) -> evaluate -> corrupted_metrics.json
    -> auto-repair (trigger bởi các vi phạm) từ raw -> GX PASS -> ChromaDB (papers-repaired)
    -> evaluate -> repaired_metrics.json -> corruption_report.md + dashboard.html
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref `/works` hoặc snapshot | Retry 3 lần + exponential backoff/`Retry-After`, bỏ thẻ JATS, parse DOI/title/authors/subject/date | `data/raw/crossref_response.json`, `crossref_records.json` | Bùi Đức Thông |
| Cleaning          | Raw records    | Chuẩn hóa text, ISO date, `age_days`, dedup `paper_id`, lọc row thiếu khóa | `data/clean/papers_clean.{csv,json}` | Bùi Đức Thông |
| Embedding/index   | Clean df       | `all-MiniLM-L6-v2` (normalize), Chroma cosine HNSW | `data/chroma/`, `data/embeddings/*.json` | Bùi Đức Vinh |
| Evaluation        | Clean df, index | Test set 10 câu cố định, Hit Rate / Token F1 / judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Đỗ Phúc Hưng |
| Observability     | Clean/corrupted df | 8 GX expectations + Freshness SLA | `data/quality/*.json` | Đỗ Phúc Hưng |
| Corruption/repair | Clean df / raw | 6 corruption seed 42; repair từ raw | `corruption_log.json`, `papers_clean_{corrupted,repaired}.*` | Bùi Đức Vinh (Thông hỗ trợ kiểm tra dữ liệu repair) |
| Orchestration     | Tất cả         | Phase 1 → Phase 2, gate, auto-repair, report | `data/reports/*.md`, `dashboard.html` | Bùi Đức Vinh (report functions: Đỗ Phúc Hưng) |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `mock`            |
| `LLM_MODEL`                | `mock`            |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24                |
| Retrieval `top_k`           | 4                 |
| Freshness threshold          | `age_days > 180`, tối đa 25% stale |
| Random seed                  | 42 (corruption)   |

### Lệnh cài đặt

```bash
uv sync --extra dev
```

### Lệnh chạy

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run pytest -q                        # 15 tests
uv run python script/build_dashboard.py # tái tạo dashboard từ artifacts
```

Chế độ live API: `REFRESH_SOURCE=1 uv run python script/run_phase1.py` (tự fallback về snapshot khi lỗi mạng/429).

### Kết quả tái hiện

| Lệnh             | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| ----------------- | ---------- | ----------------------- | ---------- |
| Baseline pipeline | Thành công (exit 0) | 2026-09-25 | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow   | Thành công (exit 0) | 2026-09-25 | `data/reports/corruption_report.md`, `data/results/{corrupted,repaired}_metrics.json` |
| Pytest            | 15 passed | 2026-09-25 | `tests/`, `.github/workflows/tests.yml` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API `https://api.crossref.org/works` (lần chạy nộp bài dùng snapshot offline) |
| Query/filter                | `agentic retrieval augmented generation large language model`; `from-pub-date:<today-180d>,has-abstract:true`; `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot có sẵn trong repo; pipeline chạy 2026-09-25 |
| Số record nhận được    | 24 items → 24 records hợp lệ |
| Cơ chế retry/backoff      | 3 lần cho HTTP 429/500/502/503/504 và lỗi mạng; chờ `Retry-After` hoặc 2^n giây (tối đa 30s); hết lượt → fallback snapshot. Snapshot chỉ bị ghi đè khi API trả record hợp lệ. |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | str (DOI, lowercase) | Có | Khóa duy nhất | Thiếu → bỏ record; trùng → giữ bản `updated` mới nhất |
| `title` | str | Có | Tiêu đề | Bỏ thẻ HTML, gom khoảng trắng; rỗng → bỏ record |
| `summary` | str | Có | Abstract | Bỏ thẻ `<jats:*>`, giải mã entity; rỗng → bỏ record |
| `authors` | list[str] | Không | `given family` | Bỏ trùng; rỗng → list rỗng |
| `categories` / `primary_category` | list[str] / str | Không | Subject Crossref | Rỗng → `Uncategorized` |
| `published` / `updated` | str ISO `YYYY-MM-DD` | Có / Không | Ngày xuất bản / cập nhật | Fallback `published → published-online → published-print → issued → created`; thiếu → bỏ record |
| `age_days` | int | Có | `(run_date − published).days` | Tính lại mỗi lần chạy |
| `text_for_embedding` | str | Có | Văn bản đem embed | Luôn dựng lại từ các cột gốc |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Bỏ thẻ JATS/HTML trong abstract | Validity | 24 (mọi abstract trong snapshot đều bọc `<jats:p>`) | `test_parse_strips_jats_and_skips_invalid_items` |
| Loại record thiếu DOI/title/abstract/ngày | Completeness | 0 trên snapshot; 1 trong unit test | `test_dedup_and_filter_bad_rows` |
| Khử trùng lặp theo `paper_id` | Uniqueness | 0 trên snapshot; 1 trong unit test | GX `expect_column_values_to_be_unique` |
| Chuẩn hóa ngày sang ISO + `age_days` | Timeliness/Consistency | 24 | `test_age_days_is_relative_to_run_date` |

`text_for_embedding` gồm đúng 5 dòng `Title / Authors / Published / Categories / Summary`, nên cả truy vấn theo tiêu đề và theo nội dung đều khớp được. Document ID trong Chroma là `<paper_id>::<row_index>`, vì vậy row trùng lặp vẫn nạp được, đúng như khi một pipeline lỗi nạp trùng. `age_days` tính theo ngày UTC của lần chạy, nên kết quả Freshness phụ thuộc vào ngày chạy.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10                            |
| Các `question_type`                    | summary (3), authors (3), date (2), categories (2) |
| Ground-truth document ID                 | DOI của paper được chọn; paper được chọn trải đều theo `published` từ mới nhất đến cũ nhất (deterministic) |
| Embedding model                          | `all-MiniLM-L6-v2`            |
| Vector store/collection                  | ChromaDB persistent, cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired` |
| Retrieval `top_k`                       | 4                             |
| LLM provider/model                       | `mock` → judge dùng heuristic theo Token F1 (≥0.95 → 5, ≥0.5 → 3, còn lại 1) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sha256 prefix `70162f9dc310bb61`) |

Test set được giữ nguyên cho cả ba trạng thái. Phase 1 chỉ sinh lại test set khi `REFRESH_TEST_SET=1` hoặc khi corpus không còn chứa ground-truth ID. Nhờ vậy, mọi chênh lệch metric đều đến từ dữ liệu chứ không đến từ việc đổi đề.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | 24 records, parse khớp 100% file records gốc |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/`   | Có | 3 collections |
| Evaluation set           | `data/eval/test_set.json`            | Có | 10 câu |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | Kèm breakdown theo question type |
| Quality/freshness        | `data/quality/`                      | Có | baseline / corrupted / repaired |
| Baseline report          | `data/reports/phase1_report.md`      | Có |  |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` | 1.0000 | Cả 10 câu đều tìm được đúng tài liệu, vì câu hỏi chứa tiêu đề chính xác và `qa.py` ưu tiên exact lookup |
| `mean_token_f1`      | 1.0000 | QA trích xuất trực tiếp từ metadata nên khớp tuyệt đối với ground truth |
| `judge_accuracy`     | 1.0000 | Heuristic judge (provider mock) |
| `mean_judge_score`   | 5.0000 | Heuristic judge (provider mock) |
| Ragas                | N/A | Không chạy vì cần LLM thật (`RUN_RAGAS=1`) |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Volume | 5–5000 | Pass (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 3 | Completeness | `paper_id`, `title`, `text_for_embedding` không null | Pass (0 null) | như trên |
| `ExpectColumnValuesToBeUnique(paper_id)` | Uniqueness | Không trùng | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Completeness | ≥ 30 ký tự | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween(title)` *(mở rộng)* | Validity | ≥ 8 ký tự | Pass | như trên |
| `ExpectColumnValuesToNotMatchRegex(summary)` *(mở rộng)* | Validity | Không chứa `�`, `[#@!%&~]{3,}`, `0x…` | Pass | như trên |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Clean dataset (`age_days`) — `data/quality/freshness_report.json` |
| Timestamp mới nhất       | 2026-07-22 (65 ngày tuổi)          |
| Ngưỡng freshness         | Stale nếu `age_days > 180`; cảnh báo khi stale ratio > 25% |
| Trạng thái baseline      | Fresh                               |
| Lý do                     | 1/24 bài quá hạn (0.0417 ≤ 0.25) — bài 2026-03-28, tuổi 181 ngày |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| `drop_latest_records` | Bỏ 20% bài mới nhất | 5 | Freshness: `latest_published` lùi | latest 2026-07-22 → 2026-06-12; eval_001 và eval_002 mất tài liệu ground-truth (miss) | Tái tạo từ raw |
| `blank_summary` | Summary = `""` | 3 | GX summary length | GX fail (3 unexpected); eval_001 trả lời rỗng (F1 0) | Tái tạo từ raw |
| `inject_noise` | Chèn token rác mỗi 2 từ | 3 | GX regex | GX fail (4 dòng, tính cả bản trùng); eval_005 F1 0.84, judge 3 | Tái tạo từ raw |
| `truncate_title` | Title[:7] | 3 | GX title length | GX fail (4 dòng, tính cả bản trùng); không câu hỏi nào trỏ vào 3 bài này | Tái tạo từ raw |
| `stale_date` | `published −365` ngày | 6 | Freshness stale ratio | 6/22 = 0.2727 > 0.25 → `STALE_ALERT`; không có câu `date` nào về 6 bài này | Tái tạo từ raw |
| `duplicate_rows` | Nhân bản 3 dòng | 3 | GX unique | GX fail (6 giá trị trùng) | Tái tạo từ raw (dedup) |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: log ghi đủ 6 loại lỗi, seed, số dòng vào/ra (24 → 22), DOI của từng record bị ảnh hưởng, cùng giá trị gốc của title và ngày xuất bản bị sửa.

Repair **không** vá từng ô dữ liệu hỏng. Pipeline đọc lại raw snapshot bất biến (`data/raw/crossref_records.json`), chạy lại đúng hàm `build_clean_dataframe`, qua lại Quality Gate (8/8 pass) rồi index vào collection mới. Pipeline tính fingerprint SHA-256 của dataset (bỏ cột `age_days`): bản repaired trùng bản baseline (`matches_baseline = True`), và hai lần repair liên tiếp cho kết quả giống hệt nhau (`idempotent_rerun_identical = True`). Repair được kích hoạt tự động dựa trên danh sách vi phạm của gate (`trigger_reasons` trong report).

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | 2 tài liệu ground-truth bị drop |
| `mean_token_f1`        | 1.0000 | 0.8842 | 1.0000 | −0.1158 | 100% | Summary rỗng (F1 0) + summary nhiễu (F1 0.84) |
| `judge_accuracy`       | 1.0000 | 0.9000 | 1.0000 | −0.1000 | 100% | Chỉ câu trả lời rỗng bị chấm sai |
| `mean_judge_score`     | 5.0000 | 4.4000 | 5.0000 | −0.6000 | 100% |  |
| Quality checks pass/fail | 8/8 | 4/8 | 8/8 | −4 | 100% | unique, title length, summary length, noise regex |
| Freshness status         | FRESH (0.0417) | STALE_ALERT (0.2727) | FRESH (0.0417) | +0.2310 stale ratio | 100% |  |

Kết luận nhân quả:

1. **Drop latest + blank summary** → Freshness `latest_published` lùi 40 ngày, GX `summary` length fail → câu eval_001 không còn tài liệu đúng; retriever trả về bài có summary bị xóa nên câu trả lời rỗng (Hit Rate −0.2, F1 −0.1).
2. **Silent failure khó thấy nhất**: eval_002 mất tài liệu gốc (retrieval miss), nhưng agent lấy bài "Advanced Perspectives on Synthetic Corruption Testing…" có cùng tác giả, nên câu trả lời vẫn đúng (F1 = 1.0, judge 5). Nếu chỉ nhìn chất lượng câu trả lời thì không phát hiện được lỗi; chỉ Hit Rate và Freshness monitor mới bắt được.
3. **Stale date và truncate title không làm giảm metric** vì test set không hỏi ngày/tiêu đề của các bài bị sửa. Tuy vậy, Freshness (`STALE_ALERT`) và GX (title length) vẫn bắt được. Benchmark cố định chỉ phủ một phần corpus, nên cần observability ở tầng dữ liệu.
4. **Repair từ raw** → GX 8/8, FRESH → cả 4 metric quay về đúng baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Great Expectations crash hoặc cho kết quả sai khi validate dataframe có cột `authors`/`categories` dạng list; ngoài ra `pd.read_json` có thể tự ép kiểu cột ngày.
- **Nguyên nhân:** Pandas execution engine của GX cần giá trị hashable cho một số metric; clean JSON lưu list để giữ cấu trúc.
- **Cách xử lý:** `run_data_quality_checks` chuyển cột list sang chuỗi `"; "` trên bản sao trước khi validate; corruption flow đọc `papers_clean.json` với `dtype={"published": str, "updated": str}`. CSV cũng ghi list dạng `a; b` để dễ đọc.
- **Cách xác minh:** `uv run pytest -q` (`test_quality_gate_passes_on_clean_data`, `test_corruption_injects_six_types_and_is_detected`), cùng các lệnh kiểm tra trong `docs/Guide.md` in `Quality check status = True`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| Chạy với `LLM_PROVIDER=mock` | Judge là heuristic theo F1, không đánh giá ngữ nghĩa | Điền API key vào `.env` và chạy lại; so sánh `judge.reasoning` trong `*_answers.json` |
| QA trích xuất và exact lookup theo tiêu đề | Baseline đạt 1.0, dễ "đẹp" hơn thực tế | Thêm câu hỏi paraphrase không chứa tiêu đề và đo lại Hit Rate |
| Test set không phủ bài bị `stale_date`/`truncate_title` | Metric không phản ánh 2 loại lỗi này | Sinh thêm câu hỏi nhắm vào record bị corrupt, hoặc tăng test set lên toàn bộ corpus |
| Freshness phụ thuộc ngày chạy | Snapshot sẽ dần thành `STALE_ALERT` theo thời gian | Chạy `REFRESH_SOURCE=1` định kỳ; thêm SLA theo `latest_age_days` |
| Raw snapshot có lỗi chính tả gốc ("mbedding" trong bài 10.1145/3637528.3671822) | Không sửa để giữ lineage | Ghi nhận ở tầng cleaning nếu cần; không sửa file raw |

## 13. Bonus đã thực hiện

- **B1 — Dashboard:** `data/reports/dashboard.html` (tự sinh cuối corruption flow hoặc qua `script/build_dashboard.py`): KPI 3 trạng thái, biểu đồ metric, histogram `age_days` sạch/hỏng, bảng GX, log corruption.
- **B2 — Auto-repair:** corruption flow tự suy ra `trigger_reasons` từ các expectation fail và từ Freshness, repair từ raw, kiểm lại gate (raise nếu vẫn fail), và kiểm chứng idempotency bằng fingerprint.
- **B3 — Test suite:** 15 test pytest (ingestion, fallback offline, cleaning, GX, freshness, corruption, test set, index + evaluation) cùng GitHub Actions `.github/workflows/tests.yml`.

## 14. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng (`report/2A202602931_BuiDucThong.md`, `report/2A202602762_DoPhucHung.md`, `report/2A202602801_BuiDucVinh.md`).
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
