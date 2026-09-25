# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Bùi Đức Thông              |
| MSSV               | 2A202602931                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | Sydneybadboy               |
| Vai trò chính    | Data Ingestion & Cleaning owner |
| Repository         | https://github.com/DucVinhBui/K4-Day10-Sydneybadboy |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Raw ingestion | `src/ingestion/crossref.py`: `fetch_source_records`, `_request_crossref`, `parse_crossref_payload`, `load_raw_records` | Crossref `/works` (query, filter, rows=24) hoặc snapshot local | `data/raw/crossref_response.json`, `data/raw/crossref_records.json`, `list[PaperRecord]` | Hoàn thành |
| Cleaning & data model | `src/ingestion/cleaning.py`: `build_clean_dataframe`, `refresh_derived_columns`, `build_text_for_embedding`, `save_clean_artifacts` | `list[PaperRecord]`, `run_date` | `data/clean/papers_clean.{csv,json}` (24 dòng × 16 cột) | Hoàn thành |
| Raw/clean schema contract | `CLEAN_COLUMNS`, dataclass `PaperRecord` | — | Schema dùng chung cho quality, index, corruption, repair | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tách `refresh_derived_columns` để corruption và repair dùng lại | Bùi Đức Vinh — `corruption.py`, `corruption_flow.py` | Dữ liệu hỏng có `text_for_embedding` được dựng lại nhất quán; repair gọi lại đúng `build_clean_dataframe` |
| Kiểm tra dữ liệu sau repair | Bùi Đức Vinh — repair | `matches_baseline = True` trong `data/reports/corruption_report.md` |
| Viết test cho ingestion/cleaning | Đỗ Phúc Hưng — `tests/` | `tests/test_ingestion.py`, `tests/test_cleaning.py` pass |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Gọi API có retry 3 lần cho 429/500/502/503/504 và lỗi mạng, tôn trọng `Retry-After`; hết lượt thì fallback snapshot | `_request_crossref`, `fetch_source_records` | Pipeline chạy được khi offline; snapshot chỉ bị ghi đè khi API trả record hợp lệ | `test_fetch_falls_back_to_snapshot_when_api_fails` |
| Parse payload, bỏ thẻ `<jats:p>`, giải mã HTML entity, fallback nhiều trường ngày | `parse_crossref_payload` | 24 records khớp 100% với `crossref_records.json` gốc | `test_parse_snapshot_matches_raw_records` |
| Làm sạch, dedup, `age_days`, `text_for_embedding` | `build_clean_dataframe` | `data/clean/papers_clean.csv`, `.json` | Lệnh CP1 in `Clean thành công 24 dòng` |

Output cụ thể: `data/clean/papers_clean.json` gồm 24 paper, mới nhất 2026-07-22, cũ nhất 2026-03-28. Mỗi dòng có `text_for_embedding` 5 phần; đây là input cho Quality Gate, ChromaDB và test set.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu Crossref có abstract bọc thẻ JATS XML, ngày tháng nằm ở nhiều trường khác nhau (`published`, `published-online`, `issued`, `created`), tên tác giả tách thành `given`/`family`, và API có thể trả 429. Phần của mình biến dữ liệu thô này thành một bảng sạch, có khóa duy nhất, sẵn sàng để embed. Đồng thời phải giữ nguyên bản raw để phục vụ repair.

### Cách triển khai

- **Ingestion:** mặc định chạy chế độ offline-first, đọc snapshot để kết quả tái lập được. Khi đặt `REFRESH_SOURCE=1` thì gọi API. `last_fetch_mode` (`live`/`snapshot`) được ghi vào `phase1_report.md` để truy vết lineage.
- **Parse:** DOI chuyển sang lowercase làm `paper_id`. Bỏ record thiếu DOI, title, abstract hoặc ngày. Ngày được chuẩn hóa về `YYYY-MM-DD`; nếu thiếu tháng/ngày thì mặc định là 01. `pdf_url` lấy từ link có content-type chứa `pdf`, không có thì dùng URL DOI.
- **Cleaning:** gom khoảng trắng, lọc row rỗng, dedup theo `paper_id` (sắp theo `updated` giảm dần rồi giữ bản đầu), tính `age_days = (run_date UTC − published).days`, dựng `text_for_embedding`, sắp theo `published` giảm dần.
- **Lưu file:** JSON giữ `authors`/`categories` dạng list; CSV ghép list thành `a; b` để dễ đọc.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref payload `{"message": {"items": [...]}}` hoặc list record JSON; `run_date` (datetime, có hoặc không timezone) |
| Output | DataFrame 16 cột theo `CLEAN_COLUMNS`; `paper_id` duy nhất, `published` là chuỗi ISO, `age_days` là int |
| Module phụ thuộc | `core/config.py` (paths, query/filter), `core/utils.py` |
| Module sử dụng output | `observability/quality.py`, `retrieval/index.py`, `evaluation/testset.py`, `ingestion/corruption.py`, `pipelines/corruption_flow.py` (repair) |
| Điều kiện lỗi cần xử lý | HTTP 429/5xx, timeout, JSON hỏng, item thiếu trường, DOI trùng, ngày chỉ có năm |

### Cách xác minh

```bash
uv run python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); r=fetch_source_records(s); print(f'Tín hiệu hoàn thành: Đã tải {len(r)} bài báo')"
uv run python -c "from datetime import datetime, timezone; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s=load_settings(); df=build_clean_dataframe(load_raw_records(s.paths.raw_records_json), datetime.now(timezone.utc)); print(f'Tín hiệu hoàn thành: Clean thành công {len(df)} dòng')"
uv run pytest tests/test_ingestion.py tests/test_cleaning.py -q
```

- **Kết quả mong đợi:** 24 bài báo, 24 dòng sạch, test pass.
- **Kết quả thực tế:** `Đã tải 24 bài báo`, `Clean thành công 24 dòng`, 8/8 test ingestion/cleaning pass; `git diff data/raw/crossref_records.json` rỗng sau khi chạy lại (parse ổn định).
- **Artifact/log:** `data/raw/`, `data/clean/`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Row có summary rỗng thì nên bị cleaning lọc bỏ, hay để Quality Gate bắt?
- **Các phương án đã cân nhắc:** (1) Không lọc gì, để GX báo lỗi. (2) Lọc ở cleaning các row không thể dùng cho RAG (thiếu khóa, title, summary, ngày). (3) Tự điền summary mặc định.
- **Phương án đã chọn:** (2).
- **Lý do:** Bản ghi thiếu abstract từ nguồn là không hợp lệ theo contract, nên lọc ngay ở cleaning. Corruption được tiêm *sau* cleaning, nên việc lọc này không che mất tín hiệu của Quality Gate. Phương án (3) sẽ tạo dữ liệu bịa, làm sai câu trả lời.
- **Bằng chứng quyết định phù hợp:** `test_dedup_and_filter_bad_rows` (row summary rỗng bị loại). Trên dữ liệu corrupted, GX vẫn fail `expect_column_value_lengths_to_be_between(summary)` với 3 unexpected (`data/quality/corrupted_quality_report.json`).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Trong `data/results/agent_demo_answers.json`, câu trả lời cho câu "How can Great Expectations be used for automated data quality profiling?" là *"An extended empirical study on mbedding quality checks directly into data pipelines enables fail-closed governance."* Chữ "Embedding" bị mất chữ "E", nên mới nghi cleaning cắt nhầm ký tự.
- **Lệnh hoặc bước tái hiện:** `grep -o "[^ ]*mbedding quality[^.]*" data/raw/crossref_response.json data/raw/crossref_records.json`
- **Nguyên nhân gốc:** Lỗi nằm ngay trong raw snapshot của đề (paper `10.1145/3637528.3671822`, cả `crossref_response.json` lẫn `crossref_records.json` đều có "study on mbedding"). Regex bỏ thẻ `<[^>]+>` và `normalize_whitespace` của cleaning không làm mất ký tự.
- **Cách xử lý:** Không sửa file raw, vì raw phải bất biến để giữ lineage và để repair tái tạo đúng. Mình ghi nhận vào phần giới hạn của `report/group_report.md`. Nếu cần sửa thì phải làm ở một bước cleaning có ghi log, không sửa raw.
- **Cách xác minh sau khi sửa:** `test_parse_snapshot_matches_raw_records` xác nhận parse từ `crossref_response.json` ra đúng từng ký tự như `crossref_records.json`, tức pipeline không tự làm hỏng text.
- **Điều học được:** Khi thấy output lạ, phải truy ngược theo lineage (answer → clean → raw records → raw response) trước khi sửa code; bảo toàn raw giúp khoanh vùng lỗi nhanh.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref trả JSON. Mình lưu nguyên văn vào `crossref_response.json`, parse thành `PaperRecord` rồi lưu vào `crossref_records.json`. Cleaning tạo `text_for_embedding`, rồi Quality Gate kiểm tra. Nếu gate pass thì MiniLM embed từng document và nạp vào ChromaDB collection `papers-baseline` với ID `<doi>::<index>`.
2. Mỗi câu hỏi trong `test_set.json` có `ground_truth_doc_ids` là DOI. Hit Rate kiểm tra DOI đó có nằm trong top-4 retrieved hay không; Token F1 so câu trả lời với `ground_truth`.
3. Quality check (GX) kiểm tra tính hợp lệ của từng giá trị: null, unique, độ dài, ký tự rác. Freshness kiểm tra độ cũ của cả tập (tỉ lệ `age_days > 180`). Dữ liệu có thể hợp lệ nhưng vẫn cũ.
4. Nếu đổi test set thì chênh lệch metric có thể do đề thi đổi chứ không do dữ liệu. Giữ cố định mới quy được nguyên nhân về corruption.
5. Repair được coi là thành công khi: GX 8/8 trong `repaired_quality_report.json`, Freshness `FRESH`, `repaired_metrics.json` bằng baseline, và fingerprint dữ liệu trùng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Giảm do mất 2 tài liệu ground-truth (drop latest) |
| `mean_token_f1`      | 1.0000 | 0.8842 | 1.0000 | Summary rỗng làm câu trả lời rỗng |
| `judge_accuracy`     | 1.0000 | 0.9000 | 1.0000 | Heuristic judge (provider mock) |
| `mean_judge_score`   | 5.0000 | 4.4000 | 5.0000 |  |
| Quality checks         | 8/8 | 4/8 | 8/8 | Lỗi nằm trong các cột do cleaning định nghĩa |
| Freshness status       | FRESH | STALE_ALERT | FRESH | Stale ratio 0.0417 → 0.2727 → 0.0417 |

### Kết luận từ số liệu

1. `drop_latest_records` (5 bài mới nhất) → `latest_published` lùi từ 2026-07-22 xuống 2026-06-12 → Hit Rate giảm 0.2 (eval_001, eval_002 không tìm được tài liệu đúng).
2. Repair đọc lại `crossref_records.json` và chạy lại `build_clean_dataframe` → 24 dòng, GX 8/8, FRESH → mọi metric về 1.0.

Corruption ảnh hưởng rõ nhất là **drop latest records**: dữ liệu biến mất thì không bước nào phía sau bù được. Đây chính là kịch bản "quên cập nhật Vector Store" trong README.

Kết quả khác kỳ vọng: mình nghĩ `stale_date` sẽ làm sai câu hỏi `date`, nhưng không có câu `date` nào hỏi về 6 bài bị lùi ngày (đối chiếu DOI trong `corruption_log.json` với `test_set.json`), nên metric không đổi. Chỉ Freshness bắt được lỗi này.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Luôn giữ raw bất biến: nhờ vậy repair chỉ cần chạy lại code, không phải sửa tay.
2. Dữ liệu sạch cần một contract rõ ràng (tên cột, kiểu, khóa) thì các module khác mới validate được.
3. Một bài báo biến mất khỏi corpus có thể không làm câu trả lời sai (eval_002 vẫn đúng tác giả nhờ bài "Advanced Perspectives" cùng tác giả), nhưng agent đang dựa trên nguồn sai.

### Nếu có thêm thời gian

Mình sẽ chạy live API (`REFRESH_SOURCE=1`) theo lịch và so số record, `latest_published` giữa các lần để phát hiện ingestion bị hụt. Cách đo: thêm trường `raw_records` vào freshness report và cảnh báo khi số record giảm quá 20% so với lần trước.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Đức Thông
**Ngày xác nhận:** 2026-09-25
