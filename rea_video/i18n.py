"""Report language.

Chinese is the source language of every user-facing string; English sits next to it. Two helpers:

  T("中文", "English")          pick the string for the current report language (optional .format kwargs)
  LangDict(zh={...}, en={...})  a code -> text mapping that resolves per language, so existing `X_ZH[code]`
                                lookups (and the `*_zh` fields they fill in breakdown.json) follow the language

The language is set once per run (`set_lang`), from `--lang` / prefs, and stored in breakdown["lang"] so
`finalize` / `summary` / `apply-review` render later in the same language. Default: zh.
"""
from __future__ import annotations

import contextvars
import re
from collections.abc import Mapping
from typing import Iterator

LANGS = ("zh", "en", "vi")
LANG_NAMES = {"zh": "中文", "en": "English", "vi": "Tiếng Việt"}
_lang: contextvars.ContextVar[str] = contextvars.ContextVar("rea_video_lang", default="zh")

VI_PHRASES = [('Mixed production: ', 'Sản xuất hỗn hợp: '), ('混合制作：', 'Sản xuất hỗn hợp: '), ('3D render', 'Render 3D'), ('3D 渲染', 'Render 3D'), ('code / template render', 'Render từ code / template'), ('代码/模板渲染', 'Render từ code / template'), ('AI-generated video', 'Video AI'), ('AI 生成视频', 'Video AI'), ('AI video', 'Video AI'), ('live action', 'Quay thật'), ('实拍', 'Quay thật'), ('talking avatar', 'Avatar kỹ thuật số'), ('数字人口播', 'Avatar kỹ thuật số'), ('AI avatar (talking head)', 'Avatar kỹ thuật số'), ('screen recording / screenshot', 'Quay màn hình / Ảnh chụp'), ('屏幕录制/截图', 'Quay màn hình / Ảnh chụp'), ('screen recording', 'Quay màn hình'), ('still image + pan/zoom', 'Pan/zoom ảnh tĩnh'), ('静态图 + 推拉动效', 'Pan/zoom ảnh tĩnh'), ('pan/zoom over still image', 'Pan/zoom ảnh tĩnh'), ('static hold', 'Ảnh tĩnh'), ('静帧停留', 'Ảnh tĩnh'), ('2D animation', 'Hoạt hình 2D'), ('2D 动画', 'Hoạt hình 2D'), ('stop motion', 'Stop motion'), ('定格动画', 'Stop motion'), ('film footage', 'Footage từ phim'), ('影视片段', 'Footage từ phim'), ('rendered by the creator', 'người làm tự tạo / tự dựng'), ('AI-generated', 'tạo bằng AI'), ('reshot', 'quay lại'), ('real material', 'tư liệu thực tế'), ('stock library', 'kho tư liệu có sẵn'), ('to confirm', 'cần xác nhận thêm'), ('tool measurements', 'phép đo công cụ'), ('seen by VLM', 'nhận diện bởi VLM'), ('user corrections', 'hiệu chỉnh từ người dùng'), ('overlays: ', 'lớp phủ: '), ('code / editor overlays', 'lớp phủ code / dựng phim'), ('brings in real material', 'kèm tư liệu thực tế'), ('cuts land on the music beat', 'vết cắt khớp nhịp nhạc'), ('real material used: ', 'tư liệu thật được sử dụng: '), ('references to prepare for the remake: ', 'tư liệu tham khảo cần chuẩn bị để làm lại: '), ('live action AI-processed afterwards: ', 'quay thật xử lý AI hậu kỳ: '), ('subtitles', 'phụ đề'), ('subtitle', 'phụ đề'), ('title', 'tiêu đề'), ('styled text', 'chữ hiệu ứng'), ('text labels', 'nhãn chữ'), ('text label', 'nhãn chữ'), ('text', 'chữ'), ('audio: ', 'âm thanh: '), ('packaging: ', 'đóng gói: '), ('3D render: AI first/last-frame generation gives an approximation; for precise multiple angles, model in 3D and animate', 'Render 3D: tạo khung đầu/cuối bằng AI cho kết quả xấp xỉ; để có nhiều góc chuẩn xác, dựng model 3D và làm chuyển động'), ("Deterministic forensics is reliable on motion, whole-frame pan/zoom, rendered texture and 24→30 fps conversion; telling live action from AI from 3D needs image reading (a VLM or an AI assistant's review), and a look at the frames yourself.", 'Đo đạc kỹ thuật xác thực tin cậy về chuyển động, pan/zoom toàn khung, bề mặt render và chuyển đổi 24→30 fps; việc phân biệt quay thật / AI / 3D cần thêm VLM đọc ảnh hoặc người dùng tự đối chiếu.'), ('Platform transcoding usually strips metadata; missing metadata proves nothing.', 'Nền tảng chia sẻ thường xóa metadata khi nén; việc thiếu metadata không khẳng định được video không phải quay thật.'), ('The full data is in `breakdown.json`; the package for models starts at `VIDEO.md`.', 'Toàn bộ dữ liệu chi tiết nằm trong `breakdown.json`; tài liệu phân tích cho AI bắt đầu tại `VIDEO.md`.')]

VI_TRANSLATIONS = {'- Text track ({k}/{b}): ': '- Track chữ ({k}/{b}): ', '- 文字轨（{k}/{b}）：': '- Track chữ ({k}/{b}): ', '**Visible on screen** (check against the frames)': '**Những gì nhìn thấy trên khung hình** (có thể đối chiếu ảnh chụp)', '**画面里看得到的**（可以对照截图核实）': '**Những gì nhìn thấy trên khung hình** (có thể đối chiếu ảnh chụp)', '**How it was made, as inferred by the tools** (inferred, not seen)': '**Cách làm theo suy luận của công cụ** (suy luận kỹ thuật, không phải thấy trực tiếp)', '**工具推断的制作方式**（是推断，不是看到的）': '**Cách làm theo suy luận của công cụ** (suy luận kỹ thuật, không phải thấy trực tiếp)', '- Inference: ': '- Suy luận: ', '- 推断：': '- Suy luận: ', 'To confirm': 'Cần xác nhận', '待确认': 'Cần xác nhận', 'Disputed': 'Có ý kiến khác biệt', '有分歧': 'Có ý kiến khác biệt', '- Material: {o}': '- Nguồn tư liệu: {o}', '- 素材来源：{o}': '- Nguồn tư liệu: {o}', '- Remake: {n}': '- Cách làm lại: {n}', '- 复刻：{n}': '- Cách làm lại: {n}', '- Basis (tool measurements, not necessarily visible to the eye):': '- Cơ sở phán đoán (phép đo công cụ, mắt thường khó nhận ra):', '- 判断依据（工具测量，肉眼不一定看得出）：': '- Cơ sở phán đoán (phép đo công cụ, mắt thường khó nhận ra):', '- Camera / lighting: {c}': '- Góc máy / Ánh sáng: {c}', '- 拍法/打光：{c}': '- Góc máy / Ánh sáng: {c}', 'crop': 'ảnh trích', '截图': 'ảnh trích', ' · runner-up {l} {p:.0%}': ' · phương án phụ {l} {p:.0%}', ' · 次选 {l} {p:.0%}': ' · phương án phụ {l} {p:.0%}', '# Shot {i} · {a}–{z}s · {v}': '# Cảnh {i} · {a}–{z}s · {v}', '# 镜头 {i} · {a}–{z}s · {v}': '# Cảnh {i} · {a}–{z}s · {v}', 'low confidence': 'độ tin cậy thấp', '低置信': 'độ tin cậy thấp', 'shape / text block': 'khối hình / khối chữ', '图形/文字块': 'khối hình / khối chữ', 'x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%}': 'x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%}', 'x {x:.0%}–{x2:.0%}，y {y:.0%}–{y2:.0%}': 'x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%}', 'text “{t}”': 'chữ “{t}”', '文字「{t}」': 'chữ “{t}”', '{w} (x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%})': '{w} (x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%})', '{w}（x {x:.0%}–{x2:.0%}，y {y:.0%}–{y2:.0%}）': '{w} (x {x:.0%}–{x2:.0%}, y {y:.0%}–{y2:.0%})', 'Edit': 'Cắt dựng', '剪辑': 'Cắt dựng', 'jump cut': 'cắt nhảy (jump cut)', '跳切': 'cắt nhảy (jump cut)', 'appears': 'xuất hiện', '出现': 'xuất hiện', '- Motion beats within the shot: ': '- Nhịp chuyển động trong cảnh: ', '- 镜头内动效节拍：': '- Nhịp chuyển động trong cảnh: ', 'text in the picture': 'chữ trong nội dung hình', '画面内容文字': 'chữ trong nội dung hình', 'middle': 'ở giữa', '中': 'ở giữa', 'top': 'phía trên', '上': 'phía trên', ' · follows an object': ' · bám theo vật thể', '·跟随物体': ' · bám theo vật thể', '{l} {n} shot{s}': '{n} cảnh {l}', '{l} {n} 镜': '{n} cảnh {l}', '- Confidence {c:.0%}, based on: {by}': '- Độ tin cậy {c:.0%}, dựa trên: {by}', '- 判断可靠度 {c:.0%}，依据：{by}': '- Độ tin cậy {c:.0%}, dựa trên: {by}', '- ⚠️ {n} points are uncertain, see “Open questions”': '- ⚠️ Có {n} điểm chưa chắc chắn, xem phần “Câu hỏi cần rà soát”', '- ⚠️ 有 {n} 处拿不准，见「不确定点」': '- ⚠️ Có {n} điểm chưa chắc chắn, xem phần “Câu hỏi cần rà soát”', 'music: find a track with the same tempo and mood': 'nhạc nền: chọn bài cùng tempo và cảm xúc', '配乐：按节奏和情绪找同类曲': 'nhạc nền: chọn bài cùng tempo và cảm xúc', '{n} sound effects': '{n} hiệu ứng âm thanh', '音效 {n} 处': '{n} hiệu ứng âm thanh', 'effects: add from a library at the listed times': 'SFX: chèn từ kho hiệu ứng theo mốc thời gian', '音效：按时间点从音效库加': 'SFX: chèn từ kho hiệu ứng theo mốc thời gian', 'AI in {k} generation{s}': 'Tạo bằng AI qua {k} lần', 'AI 分 {k} 次生成': 'Tạo bằng AI qua {k} lần', 'screen recording / motion graphics in code': 'quay màn hình / hiệu ứng đồ họa bằng code', '录屏 / 代码做动效': 'quay màn hình / hiệu ứng đồ họa bằng code', '**Plan the content**: go through the shot list, note what each part says, then write your own version': '**Lên kịch bản**: xem danh sách cảnh quay, nắm ý từng đoạn rồi viết kịch bản riêng của bạn', '**定内容**：先看一遍分镜表，记下每段在讲什么，再写你自己的版本': '**Lên kịch bản**: xem danh sách cảnh quay, nắm ý từng đoạn rồi viết kịch bản riêng của bạn', '**Collect material**: see “What to prepare” below': '**Chuẩn bị tư liệu**: xem mục “Tư liệu cần chuẩn bị” bên dưới', '**备素材**：见下方「要准备的素材」': '**Chuẩn bị tư liệu**: xem mục “Tư liệu cần chuẩn bị” bên dưới', 'What to prepare': 'Tư liệu cần chuẩn bị', '要准备的素材': 'Tư liệu cần chuẩn bị', '**Generate**: {c} generation{s}, see “AI generation” below': '**Tạo bằng AI**: {c} lượt tạo, xem mục “Tạo bằng AI” bên dưới', '**AI 生成**：{c} 次生成，见下方「AI 生成」': '**Tạo bằng AI**: {c} lượt tạo, xem mục “Tạo bằng AI” bên dưới', 'Code build': 'Dựng bằng code', '代码合成': 'Dựng bằng code', '**Screen and motion graphics**: see “Code build” below': '**Quay màn hình & đồ họa**: xem mục “Dựng bằng code” bên dưới', '**录屏和动效**：见下方「代码合成」': '**Quay màn hình & đồ họa**: xem mục “Dựng bằng code” bên dưới', 'Local rebuild': 'Dựng lại cục bộ', '本地重建': 'Dựng lại cục bộ', '**Stills / moves**: see “Local rebuild” below': '**Ảnh tĩnh / Chuyển động**: xem mục “Dựng lại cục bộ” bên dưới', '**静帧 / 推拉**：见下方「本地重建」': '**Ảnh tĩnh / Chuyển động**: xem mục “Dựng lại cục bộ” bên dưới', 'Film / TV source': 'Nguồn phim / TV', '影视原片': 'Nguồn phim / TV', '**Film / TV clips**: see “Film / TV source” below': '**Trích đoạn phim**: xem mục “Nguồn phim / TV” bên dưới', '**影视片段**：见下方「影视原片」': '**Trích đoạn phim**: xem mục “Nguồn phim / TV” bên dưới', '**Edit**: see “Edit” below': '**Cắt dựng**: xem mục “Cắt dựng” bên dưới', '**剪辑**：见下方「剪辑」': '**Cắt dựng**: xem mục “Cắt dựng” bên dưới', '- Cut in the order and lengths of the shot list': '- Cắt dựng theo đúng thứ tự và thời lượng của danh sách cảnh', '- 按「分镜表」的顺序和时长剪': '- Cắt dựng theo đúng thứ tự và thời lượng của danh sách cảnh', '- Rhythm: {e}': '- Nhịp điệu: {e}', '- 节奏：{e}': '- Nhịp điệu: {e}', '; transitions {t}': '; chuyển cảnh {t}', '；转场 {t}': '; chuyển cảnh {t}', '**Packaging**: ': '**Đóng gói**: ', '**包装**：': '**Đóng gói**: ', 'styles and timeline under “Packaging layer”': 'kiểu dáng và timeline xem tại “Lớp đóng gói cắt dựng”', '样式和时间轴见「剪辑包装层」': 'kiểu dáng và timeline xem tại “Lớp đóng gói cắt dựng”', '**Sound**: see “Sound”; every effect can be played first': '**Âm thanh**: xem “Âm thanh”, mọi hiệu ứng đều có thể nghe thử trước', '**声音**：见「声音」，每处音效都能先试听': '**Âm thanh**: xem “Âm thanh”, mọi hiệu ứng đều có thể nghe thử trước', '**Compare**: watch yours next to the original: shot lengths, subtitle positions, where the music comes in and drops': '**So sánh kiểm tra**: đối chiếu video của bạn song song với bản gốc: độ dài cảnh, vị trí phụ đề, điểm vào/ngắt của âm nhạc', '**对照检查**：成片和原片并排看一遍：镜头长短、字幕位置、音乐起落对不对得上': '**So sánh kiểm tra**: đối chiếu video của bạn song song với bản gốc: độ dài cảnh, vị trí phụ đề, điểm vào/ngắt của âm nhạc', 'Each shot has two parts: what is visible on screen, and how the tools infer it was made (with the basis); remake prompts last. Folded by default.': 'Mỗi cảnh chia làm hai phần: những gì nhìn thấy trên khung hình và cách làm theo suy luận của công cụ (kèm bằng chứng kỹ thuật); cuối cùng là prompt làm lại. Mặc định thu gọn, bấm để mở.', '每个镜头分两块：画面里看得到的，和工具推断的制作方式（附判断依据）；最后是复刻提示词。默认折叠，点开看。': 'Mỗi cảnh chia làm hai phần: những gì nhìn thấy trên khung hình và cách làm theo suy luận của công cụ (kèm bằng chứng kỹ thuật); cuối cùng là prompt làm lại. Mặc định thu gọn, bấm để mở.', '- Encoder: `{e}`': '- Trình mã hóa: `{e}`', '- 编码器：`{e}`': '- Trình mã hóa: `{e}`', 'Voice': 'Giọng nói', 'Music': 'Nhạc nền', 'Sound effects': 'Hiệu ứng âm thanh (SFX)', 'Listen': 'Nghe thử', 'Type': 'Loại', 'Times used': 'Số lần', 'At': 'Mốc thời gian', 'On screen': 'Trên khung hình', 'all {n} distinct effects (with audio)': 'toàn bộ {n} loại hiệu ứng (kèm file âm thanh)', '全部 {n} 种音效（可试听）': 'toàn bộ {n} loại hiệu ứng (kèm file âm thanh)', '- Text on objects in the scene (not subtitles): ': '- Chữ trên đồ vật trong bối cảnh (không phải phụ đề): ', '- 画面里物体上的字（不是后期字幕）：': '- Chữ trên đồ vật trong bối cảnh (không phải phụ đề): ', 'loudness {r} dBFS, peak {p} dBFS': 'độ lớn {r} dBFS, đỉnh {p} dBFS', '响度 {r} dBFS，峰值 {p} dBFS': 'độ lớn {r} dBFS, đỉnh {p} dBFS', '- Sources: {s}': '- Nguồn âm thanh: {s}', '- 来源判断：{s}': '- Nguồn âm thanh: {s}', '**Voice**': '**Giọng nói (Voice)**', '**人声**': '**Giọng nói (Voice)**', '{r:.0%} of the duration': '{r:.0%} thời lượng', '占 {r:.0%} 时长': 'chiếm {r:.0%} thời lượng', 'gender unclear': 'giới tính chưa rõ', '性别不确定': 'giới tính chưa rõ', 'pitch about {f}Hz ({g})': 'cao độ khoảng {f}Hz ({g})', '基频约 {f}Hz（{g}）': 'cao độ khoảng {f}Hz ({g})', '**Music**': '**Nhạc nền (BGM)**', '**背景音乐**': '**Nhạc nền (BGM)**', '{bpm} BPM (or {alt})': '{bpm} BPM (hoặc {alt})', '{bpm} BPM（也可能是 {alt}）': '{bpm} BPM (hoặc {alt})', 'key {t} {m} (confidence {c})': 'giọng {t} {m} (độ tin cậy {c})', '调性 {t} {m}（置信 {c}）': 'giọng {t} {m} (độ tin cậy {c})', '{r:.0%} of the duration ({s}–{e}s)': '{r:.0%} thời lượng ({s}–{e}s)', '占 {r:.0%} 时长（{s}–{e}s）': 'chiếm {r:.0%} thời lượng ({s}–{e}s)', 'section changes at {p}': 'đổi đoạn tại {p}', '段落变化点 {p}': 'đổi đoạn tại {p}', 'ending: {e}': 'kết thúc: {e}', '片尾{e}': 'kết thúc: {e}', '- Tempo: ': '- Nhịp điệu: ', '- 节奏：': '- Nhịp điệu: ', '- Cuts vs beat: {r:.0%} of cuts land on a beat (chance: about {c:.0%})': '- Cắt dựng theo nhịp: {r:.0%} vết cắt rơi đúng nhịp phách (ngẫu nhiên khoảng {c:.0%})', '- 剪辑与节拍：{r:.0%} 的切点落在节拍上（随机约 {c:.0%}）': '- Cắt dựng theo nhịp: {r:.0%} vết cắt rơi đúng nhịp phách (ngẫu nhiên khoảng {c:.0%})', '**Sound effects**': '**Hiệu ứng âm thanh (SFX)**', '**音效**': '**Hiệu ứng âm thanh (SFX)**', 'Made with (inferred): {m}': 'Cách làm (suy luận): {m}', '制作方式（推断）：{m}': 'Cách làm (suy luận): {m}', '**Verdict** (inferred): {v}': '**Kết luận** (suy luận): {v}', '**结论**（推断）：{v}': '**Kết luận** (suy luận): {v}', '**Made with** (inferred, by duration): ': '**Cách làm** (suy luận, theo thời lượng): ', '**制作方式**（推断，按时长）：': '**Cách làm** (suy luận, theo thời lượng): ', '**Remake**: {p}': '**Làm lại**: {p}', '**复刻**：{p}': '**Làm lại**: {p}', '## Next steps': '## Các bước tiếp theo', '## 下一步': '## Các bước tiếp theo', '## Map': '## Bản đồ tài liệu', '## 地图': '## Bản đồ tài liệu', '## How to read': '## Hướng dẫn đọc báo cáo', '## 读法': '## Hướng dẫn đọc báo cáo'}

# Merge additional baseline translations
VI_TRANSLATIONS.update({
    "live action": "Quay thật",
    "AI-generated video": "Video AI",
    "AI video": "Video AI",
    "talking avatar": "Avatar kỹ thuật số",
    "3D render": "Render 3D",
    "code / template render": "Render từ code / template",
    "screen recording": "Quay màn hình",
    "pan/zoom over still image": "Pan/zoom ảnh tĩnh",
    "static hold": "Ảnh tĩnh",
    "2D animation": "Hoạt hình 2D",
    "stop motion": "Stop motion",
    "film footage": "Footage từ phim",
    "live_action": "Quay thật",
    "ai_video": "Video AI",
    "avatar": "Avatar kỹ thuật số",
    "cg_3d": "Render 3D",
    "code_render": "Render từ code / template",
    "screen_capture": "Quay màn hình",
    "still_motion": "Pan/zoom ảnh tĩnh",
    "static_hold": "Ảnh tĩnh",
    "anim_2d": "Hoạt hình 2D",
    "stop_motion": "Stop motion",
    "film_footage": "Footage từ phim",
    "rendered by the creator": "người làm tự tạo / tự dựng",
    "AI-generated": "tạo bằng AI",
    "reshot": "quay lại",
    "real material": "tư liệu thực tế",
    "stock library": "kho tư liệu có sẵn",
    "to confirm": "cần xác nhận thêm",
    "to confirm, leaning stock library music": "cần xác nhận thêm, nghiêng về nhạc kho",
    "subtitle": "phụ đề",
    "subtitles": "phụ đề",
    "title": "tiêu đề",
    "label": "nhãn chữ",
    "text labels": "nhãn chữ",
    "text": "chữ",
    "static graphic": "đồ họa tĩnh",
    "static graphics": "đồ họa tĩnh",
    "graphic": "đồ họa",
    "layout template": "template bố cục",
    "styled text": "chữ hiệu ứng",
    "animated sticker / GIF": "sticker động / GIF",
    "static sticker": "sticker tĩnh",
    "picture-in-picture": "hình trong hình (PiP)",
    "pip": "hình trong hình (PiP)",
    "huazi": "chữ hiệu ứng",
    "static": "góc máy cố định",
    "static (subject moves)": "cố định (chủ thể cử động)",
    "whole-frame zoom / pan": "zoom / lia toàn khung",
    "handheld shake": "rung lắc cầm tay",
    "smooth move": "chuyển động mượt",
    "hard in": "xuất hiện ngay",
    "pop": "bật nảy (pop)",
    "fade in": "mờ dần vào",
    "slide in": "trượt vào",
    "type-on": "hiện từng chữ",
    "hard out": "biến mất ngay",
    "shrink out": "thu nhỏ biến mất",
    "fade out": "mờ dần ra",
    "slide out": "trượt ra",
    "Music": "Nhạc nền",
    "Voice": "Giọng nói",
    "Sound effects": "Hiệu ứng âm thanh (SFX)",
    "voice": "giọng nói",
    "voice: ": "giọng nói: ",
    "music": "nhạc nền",
    "effects": "hiệu ứng âm thanh (SFX)",
    "sound effects": "hiệu ứng âm thanh (SFX)",
    "TTS": "Giọng đọc AI (TTS)",
    "human": "Giọng người thật",
    "human + TTS": "Người thật + TTS",
    "none": "không có",
    "silent": "không có âm thanh",
    "male-leaning": "thiên về giọng nam",
    "female-leaning": "thiên về giọng nữ",
    "ends naturally": "kết thúc tự nhiên",
    "fades out": "nhỏ dần (fade out)",
    "cut off hard": "cắt đột ngột",
    "heard": "nghe thấy",
    "on the effects track": "phát hiện trên track hiệu ứng",
    "signal candidate (low confidence)": "tín hiệu ứng viên (độ tin cậy thấp)",
    "signal candidate at a text / sticker pop (low confidence)": "tín hiệu khớp với xuất hiện chữ/sticker (độ tin cậy thấp)",
    "agent review": "Agent rà soát",
    "heard + signal": "nghe thấy + tín hiệu",
    "TTS voice-over": "lời bình TTS",
    "TTS voice": "giọng đọc TTS",
    "AI generation": "Tạo bằng AI",
    "reshoot": "Quay thật lại",
    "TTS + avatar": "TTS + avatar",
    "AI generation / 3D render": "Tạo AI / Render 3D",
    "code render": "Render bằng code",
    "screen recording": "Quay lại màn hình",
    "local ffmpeg move": "Chuyển động ffmpeg cục bộ",
    "static frame": "Giữ khung hình tĩnh",
    "AI generation (2D animation)": "Tạo hoạt hình 2D bằng AI",
    "stop motion shoot": "Quay stop motion",
    "cut from the source film": "Cắt từ phim gốc",
    "high": "cao",
    "medium": "trung bình",
    "low": "thấp",
    "seen by VLM": "nhận diện bởi VLM",
    "tool measurements": "phép đo công cụ",
    "user corrections": "hiệu chỉnh từ người dùng",
    " (AI image reading did not run; tools only)": " (chưa bật VLM nhận diện ảnh; chỉ dựa trên công cụ)",
    "vertical": "khung hình dọc",
    "horizontal": "khung hình ngang",
    "square": "khung hình vuông",
    "Vertical 9:16": "Khung dọc 9:16",
    "Horizontal 16:9": "Khung ngang 16:9",
    "Square 1:1": "Khung vuông 1:1",
    "Vertical 3:4": "Khung dọc 3:4",
    "Horizontal 4:3": "Khung ngang 4:3",
    "Mixed production: ": "Sản xuất hỗn hợp: ",
    "brings in real material ({k})": "kèm tư liệu thực tế ({k})",
    "overlays: {k} (composited in code / an editor)": "lớp phủ: {k} (ghép trong code hoặc phần mềm dựng)",
    "# How this video was made: {f}": "# Video này được làm như thế nào: {f}",
    "# 这条视频是怎么做的：{f}": "# Video này được làm như thế nào: {f}",
    "**In one line**: {x}": "**Tóm tắt**: {x}",
    "**一句话**：{x}": "**Tóm tắt**: {x}",
    "**How it was made**: {v}": "**Cách làm**: {v}",
    "**怎么做的**：{v}": "**Cách làm**: {v}",
    "- {d} · {o} {ar} · {n} shots, {avg}s each on average": "- {d} · {o} {ar} · {n} cảnh quay, trung bình {avg}s một cảnh",
    "- {d} · {o} {ar} · {n} 个镜头，平均 {avg} 秒一个": "- {d} · {o} {ar} · {n} cảnh quay, trung bình {avg}s một cảnh",
    "Confidence {c}%, based on: {m}": "Độ tin cậy {c}%, dựa trên: {m}",
    "置信度 {c}%，来自{m}": "Độ tin cậy {c}%, dựa trên: {m}",
    "! {n} points are uncertain, see “Open questions”": "⚠️ Có {n} điểm chưa chắc chắn, xem phần “Câu hỏi cần rà soát”",
    "！有 {n} 处存疑，见文末「待复核问题」": "⚠️ Có {n} điểm chưa chắc chắn, xem phần “Câu hỏi cần rà soát”",
    "Breakdown: ": "Phân tích: ",
    "拆解：": "Phân tích: ",
    "## What makes it work": "## Điểm cốt lõi của video",
    "## 核心看点": "## Điểm cốt lõi của video",
    "## At a glance: picture, packaging, sound": "## Tổng quan 3 tầng: Hình ảnh, Đóng gói, Âm thanh",
    "## 一眼看懂：画面、包装、声音三层": "## Tổng quan 3 tầng: Hình ảnh, Đóng gói, Âm thanh",
    "Layer": "Tầng",
    "In this video": "Trong video này",
    "How to make it": "Cách thực hiện",
    "Detail": "Chi tiết",
    "**Picture** (base)": "**Hình ảnh** (Lớp nền)",
    "“Remake it yourself”": "“Tự làm lại”",
    "**Packaging** (on top)": "**Đóng gói** (Lớp phủ trên)",
    "“Packaging layer”": "“Lớp đóng gói cắt dựng”",
    "**Sound**": "**Âm thanh**",
    "“Sound”": "“Âm thanh”",
    "## Remake it yourself: do it in this order": "## Hướng dẫn làm lại: Làm theo thứ tự này",
    "## 自己复刻：按这个顺序做": "## Hướng dẫn làm lại: Làm theo thứ tự này",
    "## Content and structure": "## Nội dung và cấu trúc",
    "## 内容与结构": "## Nội dung và cấu trúc",
    "## Cast, scenes and props": "## Nhân vật, bối cảnh và đạo cụ",
    "## 角色、场景与道具": "## Nhân vật, bối cảnh và đạo cụ",
    "## Sound": "## Âm thanh",
    "## 声音": "## Âm thanh",
    "## Camera and lighting": "## Góc quay và ánh sáng",
    "## 拍法与打光": "## Góc quay và ánh sáng",
    "## Camera, lighting and editing": "## Góc quay, ánh sáng và dựng phim",
    "## 拍法、打光与剪辑": "## Góc quay, ánh sáng và dựng phim",
    "## Packaging layer (subtitles / styled text / stickers / sound-effect hits)": "## Lớp đóng gói cắt dựng (phụ đề / chữ hiệu ứng / sticker / SFX)",
    "## 剪辑包装层（字幕 / 花字 / 贴纸 / 音效卡点）": "## Lớp đóng gói cắt dựng (phụ đề / chữ hiệu ứng / sticker / SFX)",
    "## Remake plan": "## Kế hoạch làm lại (Remake)",
    "## 复刻方案": "## Kế hoạch làm lại (Remake)",
    "### Real material in the picture (the original files are needed)": "### Tư liệu thật trong khung hình (cần file gốc)",
    "### 画面里的真实素材（必须拿到原文件）": "### Tư liệu thật trong khung hình (cần file gốc)",
    "### Reference material to prepare for the remake": "### Tư liệu tham khảo cần chuẩn bị để remake",
    "### 复刻要准备的参考素材": "### Tư liệu tham khảo cần chuẩn bị để remake",
    "### Acting and emotion": "### Diễn xuất và cảm xúc",
    "### 表演与情绪": "### Diễn xuất và cảm xúc",
    "## Shot list": "## Danh sách cảnh quay",
    "## 分镜表": "## Danh sách cảnh quay",
    "## Open questions": "## Câu hỏi cần rà soát",
    "## 不确定点": "## Câu hỏi cần rà soát",
    "## Appendix": "## Phụ lục",
    "## 附录": "## Phụ lục",
    "### Shot by shot": "### Bằng chứng kỹ thuật từng cảnh",
    "### 逐镜取证": "### Bằng chứng kỹ thuật từng cảnh",
    "### Metadata clues": "### Manh mối từ metadata",
    "### 元数据线索": "### Manh mối từ metadata",
    "### Notes": "### Ghi chú",
    "### 说明": "### Ghi chú",
    "Frames": "Khung hình",
    "Time": "Thời gian",
    "Length": "Thời lượng",
    "Picture": "Hình ảnh",
    "Camera": "Góc máy",
    "Overlays": "Lớp phủ",
    "Made with (inferred)": "Cách làm (suy luận)",
    "Material (inferred)": "Tư liệu (suy luận)",
    "Remake": "Làm lại",
    "Plan the content": "Lên kế hoạch nội dung",
    "go through the shot list, note what each part says, then write your own version": "xem danh sách cảnh quay, ghi lại thông điệp từng đoạn và viết kịch bản của riêng bạn",
    "Prepare the assets": "Chuẩn bị tư liệu",
    "Make the picture shots": "Tạo các cảnh quay hình ảnh",
    "Add packaging in the editor": "Thêm đóng gói trong phần mềm dựng",
    "Sound: voice, music, SFX": "Âm thanh: lời bình, nhạc nền, SFX",
    "Copy the method and the rhythm, not the pictures.": "Học theo phương pháp và nhịp điệu, không sao chép hình ảnh nguyên bản.",
    "Any short video splits into three layers: the picture, what is laid on top of it (subtitles, styled text, stickers), and the sound. Remake it one layer at a time.": "Mọi video ngắn đều chia thành ba tầng: hình ảnh nền, lớp đóng gói bên trên (phụ đề, chữ hiệu ứng, nhãn dán) và âm thanh. Hãy làm lại từng tầng một.",
    "Picture, Camera and Overlays are what is visible on screen; Made with and Material are the tools' inference, with the basis in the shot-by-shot appendix.": "Hình ảnh, Góc máy và Lớp phủ là những gì nhìn thấy trên màn hình; Cách làm và Tư liệu là suy luận của công cụ, có cơ sở trong phần phụ lục.",
    "The whole video's content was not analysed this time (needs AI image reading); subtitle text is under “Packaging layer”": "Nội dung toàn bộ video chưa được phân tích sâu ở lượt này (cần bật VLM đọc ảnh); lời thoại và phụ đề xem tại mục 'Lớp đóng gói cắt dựng'",
    "No narrative line this time (what each shot is doing in the story needs AI image reading); the “Picture” column of the shot list is a start": "Chưa có tuyến dẫn dắt câu chuyện ở lượt này (cần bật VLM để hiểu diễn biến từng cảnh); có thể tham khảo cột 'Hình ảnh' trong danh sách cảnh quay",
    "add in the editor: subtitles, styled text and stickers by the timeline": "thêm trong trình dựng: phụ đề, chữ hiệu ứng và sticker theo timeline",
    "voice: TTS voice-over; music: find a track with the same tempo and mood; effects: add from a library at the listed times": "lời bình: dùng giọng TTS; nhạc nền: chọn bài cùng tempo và cảm xúc; hiệu ứng: thêm từ thư viện theo mốc thời gian",
    "No VLM; live action / AI / 3D are told apart from pixel statistics only, so confidence is limited. An agent that can see images: run rea-video review, look at each shot and merge with apply-review; otherwise configure a VLM (any OpenAI-compatible multimodal model, e.g. Gemini / GPT-4o / Doubao / Qwen-VL): set REA_VLM_BASE_URL, REA_VLM_API_KEY and REA_VLM_MODEL (several models comma-separated as fallbacks), then rerun with --vlm": "Không dùng VLM; việc phân biệt quay thật / AI / 3D chỉ dựa vào đặc tính điểm ảnh nên độ tin cậy ở mức ước lượng. Có thể cấu hình VLM (Gemini / GPT-4o / Doubao / Qwen-VL) qua REA_VLM_BASE_URL, REA_VLM_API_KEY và REA_VLM_MODEL rồi chạy lại với cờ --vlm để độ chính xác cao hơn.",
    "{base} + code / editor overlays ({kinds})": "{base} + lớp phủ code/dựng phim ({kinds})",
    " ({r:.0%} of the duration is live action or AI, to confirm: the platform transcode erased the noise evidence, needs a VLM pass or a human look at the frames)": " (trong đó {r:.0%} thời lượng là quay thật hay AI cần xác nhận: nén video nền tảng đã làm mờ nhiễu cảm biến, cần VLM hoặc mắt người rà soát)",
    " ({r:.0%} of the duration carries film / TV hints (letterbox layout), possibly a film recap or compilation, to confirm by looking)": " (trong đó {r:.0%} thời lượng có manh mối phim ảnh (khung viền đen), có thể là review phim hoặc cắt ghép)",
    " ({r:.0%} of the duration lacks evidence for live action vs AI, to confirm)": " (trong đó {r:.0%} thời lượng chưa đủ bằng chứng giữa quay thật và AI, cần xác nhận thêm)",
})


def set_lang(lang: str | None) -> str:
    lang = (lang or "zh").lower()
    if lang not in LANGS:
        raise ValueError(f"unsupported report language {lang!r} (choose from {', '.join(LANGS)})")
    _lang.set(lang)
    return lang


def lang() -> str:
    return _lang.get()


def translate_text(text: str) -> str:
    """Translates known English/Chinese strings to Vietnamese if current lang is 'vi'."""
    if _lang.get() != "vi" or not text or not isinstance(text, str):
        return text
    if text in VI_TRANSLATIONS:
        return VI_TRANSLATIONS[text]
    for prefix in ("- ", "  - ", "   - ", "* ", "• "):
        if text.startswith(prefix):
            sub = text[len(prefix):]
            if sub in VI_TRANSLATIONS:
                return prefix + VI_TRANSLATIONS[sub]
    res = text
    for k, v in VI_PHRASES:
        if k in res:
            res = res.replace(k, v)
    return res


def T(zh: str, en: str | None = None, vi: str | None = None, **kw) -> str:
    """Text for the current language; `vi` translates from dictionary, falls back to `en`, then `zh`."""
    cur = _lang.get()
    if cur == "vi":
        if vi is not None:
            s = vi
        elif en and en in VI_TRANSLATIONS:
            s = VI_TRANSLATIONS[en]
        elif zh in VI_TRANSLATIONS:
            s = VI_TRANSLATIONS[zh]
        elif en:
            s = translate_text(en)
        else:
            s = translate_text(zh)
    elif cur == "en":
        s = en if en is not None else zh
    else:
        s = zh
    return s.format(**kw) if kw else s


def model_name(name: str | None) -> str | None:
    if not name or _lang.get() == "zh":
        return name
    return re.sub(r"\s*（([^）]*)）", lambda m: "" if re.search(r"[\u3400-\u9fff]", m[1]) else f" ({m[1]})", name)


def sep() -> str:
    """List separator: 、 in Chinese, ", " in English."""
    return "、" if _lang.get() == "zh" else ", "


def join(items) -> str:
    return sep().join(str(x) for x in items)


def shot_ids(ids) -> str:
    """Shot numbers as a short list: runs of three or more become a range, "#5、#8–#24"."""
    ids = sorted({int(i) for i in ids or []})
    if not ids:
        return "—"
    runs, out = [[ids[0], ids[0]]], []
    for i in ids[1:]:
        if i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    for a, z in runs:
        out += [f"#{a}–#{z}"] if z - a >= 2 else [f"#{i}" for i in range(a, z + 1)]
    return join(out)


def semi() -> str:
    """Clause separator: ； in Chinese, "; " in English."""
    return "；" if _lang.get() == "zh" else "; "


class LangDict(Mapping):
    """code -> display text, resolved per language. Keys and iteration follow the zh table."""

    def __init__(self, zh: dict, en: dict | None = None, vi: dict | None = None):
        self._zh = dict(zh)
        self._en = dict(en or {})
        self._vi = dict(vi or {})

    def __getitem__(self, key):
        cur = _lang.get()
        if cur == "vi":
            if key in self._vi:
                return self._vi[key]
            en_val = self._en.get(key)
            if en_val and en_val in VI_TRANSLATIONS:
                return VI_TRANSLATIONS[en_val]
            zh_val = self._zh.get(key)
            if zh_val and zh_val in VI_TRANSLATIONS:
                return VI_TRANSLATIONS[zh_val]
            if key in VI_TRANSLATIONS:
                return VI_TRANSLATIONS[key]
            if en_val:
                return translate_text(en_val)
            return translate_text(self._zh.get(key, key))
        if cur == "en" and key in self._en:
            return self._en[key]
        return self._zh[key]

    def __iter__(self) -> Iterator:
        return iter(self._zh)

    def __len__(self) -> int:
        return len(self._zh)

    def __contains__(self, key) -> bool:
        return key in self._zh

    def __repr__(self) -> str:
        return f"LangDict({dict(self.items())!r})"
