# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `Sydneybadboy`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** [`K4-Day10-Sydneybadboy`](https://github.com/DucVinhBui/K4-Day10-Sydneybadboy)

---

## # Thành viên

Nhóm có 3 thành viên, phân công theo bảng "Nhóm 3 thành viên" trong `report/README.md`.

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Bùi Đức Vinh | [MSSV] | | Trưởng nhóm / Corruption & Integration owner (`corruption.py`, `phase1.py`, `corruption_flow.py`, `retrieval/index.py`, môi trường `uv`) | [`report/MSSV_BuiDucVinh.md`](../report/MSSV_BuiDucVinh.md) |
| 2 | Bùi Đức Thông | 2A202602931 | | Data Ingestion & Cleaning owner (`crossref.py`, `cleaning.py`, raw/clean schema) | [`report/2A202602931_BuiDucThong.md`](../report/2A202602931_BuiDucThong.md) |
| 3 | Đỗ Phúc Hưng | 2A202602762 | | Evaluation & Observability owner (`testset.py`, `quality.py` GX 1.x, `reporting.py`, `dashboard.py`, `tests/`) | [`report/2A202602762_DoPhucHung.md`](../report/2A202602762_DoPhucHung.md) |

---

## # Cá nhân

### ## BuiDucVinh-[MSSV]
- **Vai trò:** Trưởng nhóm, Corruption & Integration owner.
- **Công việc chi tiết đã hoàn thành:**
  - Viết `src/ingestion/corruption.py`: tiêm 6 lỗi (drop latest 20%, blank summary, inject noise, truncate title, stale date −365 ngày, duplicate rows) với seed 42, các tập dòng bị lỗi rời nhau, ghi `data/results/corruption_log.json`.
  - Nối Phase 1 (`src/pipelines/phase1.py`): ingestion → cleaning → Quality Gate chặn index khi fail → ChromaDB → test set cố định → evaluate → report, kèm agent demo có fallback.
  - Nối Phase 2 (`src/pipelines/corruption_flow.py`): corrupt → observability → bypass gate có chủ đích để đo silent failure → auto-repair từ raw → kiểm tra idempotency bằng fingerprint → report 3 trạng thái.
  - Sửa `retrieval/index.py` để manifest embeddings lưu đường dẫn tương đối (`data/chroma`), chạy được trên máy khác.
  - Dựng môi trường bằng `uv sync --frozen`, viết workflow CI `.github/workflows/tests.yml`.
- **Điều học được / Đóng góp chính:**
  - Repair phải tái tạo từ nguồn raw bất biến thì mới idempotent: chạy lại 2 lần cho cùng fingerprint `ccc4c8d703c9c4c1`, trùng baseline.

### ## BuiDucThong-2A202602931
- **Vai trò:** Data Ingestion & Cleaning owner.
- **Công việc chi tiết đã hoàn thành:**
  - Viết `src/ingestion/crossref.py`: gọi Crossref `/works` với retry/backoff cho 429/5xx; khi lỗi thì fallback về snapshot `data/raw/crossref_response.json`; parse DOI/title/abstract (bỏ thẻ JATS)/authors/subject/dates; lưu 2 raw artifact.
  - Viết `src/ingestion/cleaning.py`: chuẩn hóa text, ngày ISO, `age_days`, dedup theo `paper_id` (giữ bản `updated` mới nhất), `text_for_embedding` 5 phần, xuất CSV/JSON.
  - Xác minh parse snapshot khớp 100% với `crossref_records.json` (24/24 records).
- **Điều học được / Đóng góp chính:**
  - Raw snapshot là "bảo hiểm" cho lineage: không sửa raw, kể cả khi phát hiện lỗi chính tả gốc ("mbedding" trong DOI `10.1145/3637528.3671822`).

### ## DoPhucHung-2A202602762
- **Vai trò:** Evaluation & Observability owner.
- **Công việc chi tiết đã hoàn thành:**
  - Viết `src/observability/quality.py`: Quality Gate chuẩn GX 1.x (`get_context(mode="ephemeral")`, `data_sources.add_pandas`) với 4 expectation bắt buộc và 2 expectation mở rộng (title ≥ 8 ký tự, summary không chứa ký tự rác); Freshness SLA (`age_days > 180`, ngưỡng 25%).
  - Viết `src/evaluation/testset.py`: 10 câu hỏi cố định trên 4 nhóm (summary/authors/date/categories), chọn paper trải đều theo thời gian.
  - Viết `src/observability/reporting.py` (phase1 report, corruption report 3 trạng thái, bảng in console) và `src/observability/dashboard.py` (bonus B1).
  - Viết bộ test `tests/` (15 test pytest, bonus B3).
- **Điều học được / Đóng góp chính:**
  - Benchmark cố định không phủ hết corpus: `stale_date` và `truncate_title` không làm giảm metric, chỉ GX và Freshness bắt được.
