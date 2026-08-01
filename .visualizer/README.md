# AI-Kit Visualizer

Visualizer dùng layout dashboard từ `diagram.html`, đã tách thành `index.html` (markup), `style.css` (CSS) và `app.js` (script). Header có search, view tabs **Evolution / Architecture / Runtime / Replay / DAG**; trung tâm là Architecture canvas, hai sidebar là module tree, thống kê, agent/event stream và inspector.

## DAG tab

`architecture.json` graphs **contexts/modules** ("kiến trúc rộng bao nhiêu"); it has no task dependency edges, so it can't answer "task nào chặn task nào" or "đường tới hạn ở đâu". The **DAG** tab answers that instead, from a separate `dag.json` payload — deliberately kept as its own standalone page (`dag.html`, embedded via iframe) rather than another toggle-able layer on the Architecture canvas, since the two graphs answer different questions and sharing one canvas is why the Architecture canvas already needs a layer toggle to stay readable.

`dag.html` is a zero-dependency, vanilla JS + SVG page — open it directly (works via `file://` too, showing an empty embedded snapshot) or serve it alongside the other JSON files for a live view. It reads `dag.json` for:

- **Edges** (`needs`, with an `unlocked` flag = has the upstream task reached `done`)
- **`layer`** — longest-path layering (wave number); columns in the DAG are waves
- **`stage`** — index 0-5 in the linear `todo → done` lifecycle; `blocked` is `-1` (a branch, not a stage) and renders as a red hatch instead of the 6-segment progress rail
- **`history`** — first timestamp each task reached each status, driving the replay scrubber
- **`ready`**, **`critical_path`** — precomputed server-side (critical path is weighted by *remaining* stages, so a nearly-done task doesn't count as "critical" just because its chain is long)

Rows in the DAG are lanes: `context` if set, else `owner` — with G6 `module_boundary` on, that's the same file-ownership boundary the engine already enforces.

## Canvas và tương tác

- Canvas vẽ node động từ `Object.keys(architecture.json)`, tự xếp theo tầng dependency hoặc vòng tròn; không phụ thuộc tên module cụ thể.
- Các layer **Architecture (deps)**, **Owner groups**, **Revision heat** và **Impact propagation** đọc dữ liệu thật từ `architecture.json`/`impact.json`. Evolution tab hiển thị kanban từ `board.json`.
- Click node khi Impact propagation bật sẽ highlight/dim dependents; khi tắt sẽ mở Inspector với info, dependencies, impact, tasks và events.
- Replay timeline dùng timestamp thật trong `events.json`. Slider, click event và nút Play đều cập nhật replay state, ẩn/hiện module theo `add-task`, tính trạng thái tại mốc và fade-in lần đầu module xuất hiện. Nút **Về hiện tại** trả về live view.
- Zoom, pan, search, refresh/diff và layout LTR/Radial vẫn được hỗ trợ; canvas chiếm phần lớn workspace desktop. Dữ liệu tự regenerate sau mỗi lệnh `ai-kit` mutate; cũng có thể chạy thủ công `python3 .ai/engine/ai_kit.py visualizer generate`.

## Chạy và kiểm tra

```bash
python3 .ai/engine/ai_kit.py visualizer generate
python3 -m http.server 8080 --directory .visualizer
```

Mở `http://localhost:8080/index.html`. `workflow.json` được thử đọc từ repository root khi static server cho phép; `board.json` là fallback dữ liệu đã export an toàn.

## Nguồn dữ liệu

- `architecture.json`: Module Registry của project qua `ai-kit --json context list`.
- `impact.json`: kết quả `ai-kit --json context impact <module>` cho từng module trong `architecture.json`; danh sách module được đọc động, không hardcode.
- `board.json`: workflow hiện tại qua `ai-kit board --format json`, kèm tags/files/acceptance_count.
- `events.json`: 200 runtime events gần nhất từ `.ai-work/logs/events.jsonl`.
- `dag.json`: task dependency graph (edges, layer/wave, stage, history, ready, critical_path) computed by `_generate_dag_payload()` from the current workflow state — see the "DAG tab" section above.
