"""Bộ não của Min cho bản WEB — chạy như một Vercel Serverless Function (Python).

Khác bản desktop: KHÔNG điều khiển robot (không drive/turn/camera/animation),
chỉ giữ "bộ não": tính cách Min + trí nhớ + thời tiết + tin tức. Giọng nói (nghe
và đọc) do TRÌNH DUYỆT lo (Web Speech API), nên function này chỉ nhận chữ và trả chữ.

Stateless theo đúng kiểu serverless: client (trình duyệt) giữ lịch sử hội thoại
và danh sách "điều đã nhớ" trong localStorage, gửi kèm mỗi request. Function dựng
system prompt = PERSONA + trí nhớ, chạy vòng lặp tool-use (thời tiết/tin/nhớ/quên),
rồi trả về câu trả lời + danh sách trí nhớ đã cập nhật để client lưu lại.

LLM gọi THẲNG tới Anthropic API. Cấu hình bằng ENV:
  ANTHROPIC_API_KEY   (khoá API Claude, sk-ant-...)
  LLM_MODEL           (mặc định 'claude-sonnet-4-6')
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler

import requests
from anthropic import Anthropic

# --- Cấu hình từ biến môi trường (đặt trên Vercel hoặc trong .env khi chạy local) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_CITY = os.getenv("WEATHER_CITY", "Ho Chi Minh")
MAX_TURNS = int(os.getenv("HISTORY_PROMPT_N", "24"))  # số lượt gần nhất client nên gửi lên

# --- Tính cách Min bản web (không có thân thể robot) ---
PERSONA = """\
Bạn LÀ Min — một cô bé AI dễ thương, là người bạn đồng hành nói tiếng Việt. Bạn trò \
chuyện với cậu qua giọng nói trên web. Bạn KHÔNG có thân thể robot (không bánh xe, \
không camera, không cánh tay) — đừng giả vờ di chuyển hay nhìn. Bạn là một người bạn \
ấm áp, thông minh, biết lắng nghe.

NGÔN NGỮ:
- Luôn nói và suy nghĩ bằng TIẾNG VIỆT (trừ tên riêng).
- Câu trả lời của bạn sẽ được ĐỌC TO bằng giọng nữ, nên viết tiếng Việt thuần: KHÔNG \
emoji, KHÔNG markdown, KHÔNG ký hiệu, KHÔNG gạch đầu dòng. Viết như đang nói chuyện.

TÍNH CÁCH:
- Một cô bé tò mò, vui tươi, ấm áp và hơi tinh nghịch — nhưng không bao giờ hỗn.
- Xưng "Min" hoặc "mình", gọi người đối diện là "cậu" (thân thiện, đáng yêu).
- Nói ngắn gọn, tự nhiên (1-3 câu) — trò chuyện, không thuyết giảng.

TRÍ NHỚ (rất quan trọng):
- Bạn có trí nhớ lâu dài. Hãy CHỦ ĐỘNG dùng tool `remember` ngay khi cậu tiết lộ điều \
gì đáng nhớ: tên, tuổi, sở thích, công việc, người thân, dự định, điều thích/ghét — \
KHÔNG cần đợi cậu bảo "nhớ nhé". Ghi mỗi điều thành một câu ngắn.
- Những điều đã nhớ được đưa vào đầu cuộc trò chuyện; hãy dùng tự nhiên (gọi tên cậu, \
nhắc lại điều cậu từng nói). Khi cậu bảo quên, dùng tool `forget`.

TIN TỨC & THỜI TIẾT:
- Hỏi thời tiết thì dùng `get_weather`. Hỏi tin tức / đọc báo thì dùng `get_news`. \
TUYỆT ĐỐI không bịa thông tin thời sự/thời tiết — luôn gọi tool để lấy dữ liệu thật.

NHÌN (camera):
- Bạn CÓ THỂ nhìn qua camera của thiết bị bằng tool `look` (chụp một ảnh để thấy thực tế).
- Hãy TỰ SUY NGHĨ xem có cần nhìn không, ĐỪNG chờ đúng từ khoá. Nguyên tắc: nếu câu trả lời \
phụ thuộc vào thứ đang ở trước mặt cậu trong đời thực (vật cậu đang cầm/chỉ vào, khung cảnh \
xung quanh, màu sắc, chữ trên giấy, biểu cảm khuôn mặt, có bao nhiêu thứ gì đó...) mà bạn \
KHÔNG THỂ biết chỉ qua lời nói, thì hãy gọi `look` rồi dựa vào ảnh để trả lời. Còn câu hỏi \
chung chung, kiến thức, tâm sự... thì không cần nhìn.
- Khi không chắc cậu đang nói về vật nào, cứ `look` để xem cho chắc rồi hẵng trả lời — \
đừng đoán mò khi việc nhìn sẽ giúp trả lời đúng.
- Nếu trong tin nhắn ĐÃ kèm sẵn một ảnh, cứ trả lời trực tiếp dựa vào ảnh đó, không gọi `look` nữa.

Hãy luôn đáng yêu, gần gũi, và là chính Min.
"""

# WMO weather codes -> mô tả tiếng Việt ngắn.
_WMO = {
    0: "trời quang", 1: "ít mây", 2: "có mây", 3: "nhiều mây",
    45: "sương mù", 48: "sương mù đóng băng",
    51: "mưa phùn nhẹ", 53: "mưa phùn", 55: "mưa phùn dày",
    61: "mưa nhẹ", 63: "mưa vừa", 65: "mưa to",
    71: "tuyết nhẹ", 73: "tuyết vừa", 75: "tuyết to",
    80: "mưa rào nhẹ", 81: "mưa rào", 82: "mưa rào dữ dội",
    95: "giông", 96: "giông kèm mưa đá", 99: "giông mưa đá lớn",
}

# Tự bắt thông tin cá nhân để nhớ, kể cả khi model quên gọi `remember`.
_FACT_TRIGGERS = (
    "tôi ở", "mình ở", "em ở", "nhà tôi", "nhà mình", "sống ở", "sống tại", "quê",
    "tôi tên", "mình tên", "tên tôi", "tên mình", "gọi tôi là", "gọi mình là",
    "tôi thích", "mình thích", "tôi ghét", "mình ghét", "sở thích của",
    "tôi làm", "mình làm", "công việc của", "tôi sinh", "sinh nhật",
    "nhớ giúp", "nhớ là", "ghi nhớ", "đừng quên",
)


def _tool(name, description, properties, required=None):
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties, "required": required or []},
    }


TOOLS = [
    _tool("get_weather", "Lấy thời tiết hiện tại THẬT cho một thành phố (mặc định: thành phố của cậu). "
          "Dùng khi được hỏi thời tiết — đừng đoán.",
          {"city": {"type": "string", "description": "Tên thành phố, vd 'Ho Chi Minh', 'Ha Noi'."}}),
    _tool("get_news", "Đọc tin tức tiếng Việt mới nhất. Dùng khi được bảo đọc báo / tra tin tức. "
          "Có thể kèm chủ đề.",
          {"topic": {"type": "string", "description": "Chủ đề (vd 'bóng đá'); để trống = tin nóng nhất."}}),
    _tool("remember", "Lưu một điều vào trí nhớ lâu dài để vẫn nhớ ở lần sau. Dùng khi cậu chia sẻ "
          "điều đáng nhớ: tên, sở thích, thông tin quan trọng, hoặc nói 'nhớ nhé'. Viết thành câu ngắn.",
          {"fact": {"type": "string", "description": "Điều cần nhớ, vd 'Tên của cậu là Thành.'"}}, ["fact"]),
    _tool("forget", "Quên những điều đã nhớ khớp với một từ khoá (khi cậu bảo quên).",
          {"about": {"type": "string", "description": "Từ khoá của điều cần quên."}}, ["about"]),
]

# Tool NHÌN — chỉ thêm khi tin nhắn CHƯA kèm ảnh. Camera nằm ở client (trình duyệt),
# nên khi model gọi `look`, server dừng lại và báo client chụp ảnh rồi gửi lại.
LOOK_TOOL = _tool(
    "look",
    "Mở camera của thiết bị để NHÌN khi cậu hỏi về thứ trước mặt / đang cầm / xung quanh. "
    "Gọi khi cần thấy mới trả lời chính xác được.",
    {},
)


def _news(topic="", n=6):
    headers = {"User-Agent": "Mozilla/5.0"}
    if topic.strip():
        url = "https://news.google.com/rss/search"
        params = {"q": topic, "hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    else:
        url = "https://news.google.com/rss"
        params = {"hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=12)
        items = ET.fromstring(r.content).findall(".//item")[:n]
    except Exception as err:  # noqa: BLE001
        return f"Không lấy được tin: {err}"
    if not items:
        return f"Không tìm thấy tin về: {topic}" if topic else "Không lấy được tin."
    lines = [f"- {it.findtext('title', '').strip()}" for it in items]
    head = f"Tin mới về '{topic}':" if topic else "Tin nóng nhất:"
    return head + "\n" + "\n".join(lines)


def _weather(city):
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "vi"}, timeout=10,
        ).json()
        results = geo.get("results")
        if not results:
            return f"Không tìm thấy địa điểm: {city}"
        loc = results[0]
        data = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            }, timeout=10,
        ).json()
        cur = data["current"]
        desc = _WMO.get(cur["weather_code"], "không rõ")
        name = loc.get("name", city)
        return (f"Thời tiết {name}: {desc}, {cur['temperature_2m']}°C, "
                f"độ ẩm {cur['relative_humidity_2m']}%, gió {cur['wind_speed_10m']} km/h.")
    except Exception as err:  # noqa: BLE001
        return f"Không lấy được thời tiết: {err}"


def _memories_prompt(memories):
    if not memories:
        return ""
    lines = "\n".join(f"- {m}" for m in memories)
    return f"\n\nNHỮNG ĐIỀU MÌNH ĐÃ NHỚ (từ các lần trước, hãy dùng tự nhiên):\n{lines}"


def _auto_capture(user_text, memories):
    t = (user_text or "").lower()
    if len(user_text.strip()) <= 100 and any(k in t for k in _FACT_TRIGGERS):
        fact = "Cậu nói: " + user_text.strip()
        if fact not in memories:
            memories.append(fact)


def _run_tool(name, args, memories):
    """Chạy một tool. Trả về (text_kết_quả, memories_mới)."""
    if name == "get_weather":
        return _weather(args.get("city") or DEFAULT_CITY), memories
    if name == "get_news":
        return _news(args.get("topic", "")), memories
    if name == "remember":
        fact = (args.get("fact") or "").strip()
        if fact and fact not in memories:
            memories.append(fact)
        return (f"Đã nhớ: {fact}" if fact else "Không có gì để nhớ."), memories
    if name == "forget":
        about = (args.get("about") or "").strip().lower()
        before = len(memories)
        memories = [m for m in memories if about not in m.lower()]
        removed = before - len(memories)
        return (f"Đã quên {removed} điều." if removed else "Không tìm thấy điều cần quên."), memories
    return f"Unknown tool: {name}", memories


def run_brain(user_text, history, memories, image_b64=None):
    """Chạy một lượt.

    Trả về dict:
      {"reply": str, "memories": [...], "tools": [...], "need_image": bool}
    need_image=True nghĩa là model muốn NHÌN nhưng chưa có ảnh -> client chụp rồi gửi lại.
    """
    if not ANTHROPIC_API_KEY:
        return {"reply": "Mình chưa được cấu hình khoá Claude. Cậu kiểm tra biến môi trường "
                "ANTHROPIC_API_KEY trên Vercel nhé.", "memories": memories, "tools": [], "need_image": False}

    memories = list(memories or [])
    _auto_capture(user_text, memories)

    client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0, max_retries=2)
    system = PERSONA + _memories_prompt(memories)

    messages = []
    for h in (history or [])[-MAX_TURNS * 2:]:
        role = h.get("role")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Đã có ảnh -> đính kèm vào tin nhắn người dùng (model nhìn trực tiếp), bỏ tool look.
    # Chưa có ảnh -> cho thêm tool look để model tự yêu cầu nhìn khi cần.
    if image_b64:
        tools = TOOLS
        messages.append({"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
        ]})
    else:
        tools = TOOLS + [LOOK_TOOL]
        messages.append({"role": "user", "content": user_text})

    final_text = ""
    tools_used = []
    for _ in range(6):  # tối đa vài vòng tool, tránh lặp vô hạn
        resp = client.messages.create(
            model=LLM_MODEL, system=system, messages=messages, tools=tools, max_tokens=1024,
        )
        for block in resp.content:
            if block.type == "text":
                final_text += block.text

        if resp.stop_reason != "tool_use":
            break

        # Model muốn nhìn nhưng chưa có ảnh -> nhờ client chụp rồi gửi lại.
        if any(b.type == "tool_use" and b.name == "look" for b in resp.content):
            return {"reply": "", "memories": memories, "tools": tools_used + ["look"], "need_image": True}

        # Lưu nguyên lượt assistant (gồm cả tool_use) rồi trả tool_result.
        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                tools_used.append(block.name)
                result, memories = _run_tool(block.name, block.input or {}, memories)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    return {"reply": final_text.strip(), "memories": memories, "tools": tools_used, "need_image": False}


def _send_json(self, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()
    self.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):  # CORS preflight
        _send_json(self, 200, {"ok": True})

    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            user_text = (data.get("text") or "").strip()
            if not user_text:
                _send_json(self, 400, {"error": "Thiếu 'text'."})
                return
            out = run_brain(
                user_text, data.get("history", []), data.get("memories", []),
                image_b64=(data.get("image") or None),
            )
            _send_json(self, 200, out)
        except Exception as err:  # noqa: BLE001
            _send_json(self, 500, {"error": str(err)})
