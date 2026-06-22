# Min — Bản Web (chỉ "bộ não", deploy lên Vercel)

Phiên bản web của Min: trò chuyện bằng **giọng nói tiếng Việt** ngay trong trình
duyệt, **không** có module điều khiển robot. Chỉ gồm bộ não: tính cách Min, trí nhớ
lâu dài, thời tiết và tin tức.

## Kiến trúc

```
Trình duyệt
  • NGHE: Web Speech API (SpeechRecognition, vi-VN)
  • ĐỌC: phát MP3 nhận từ /api/tts (KHÔNG phụ thuộc giọng cài trong máy)
      │
      ├── POST /api/chat  { text, history, memories }
      │        ▼  Vercel Function api/chat.py  ──(Anthropic SDK)──►  Claude
      │
      └── POST /api/tts   { text }
               ▼  Vercel Function api/tts.py   ──(edge-tts)──►  MP3 giọng vi-VN
```

Khác bản desktop (dùng 9Router qua Tailscale), bản web gọi **thẳng Anthropic API**
bằng API key — không cần tunnel, không phụ thuộc máy công ty.

- **NGHE**: Web Speech API (`SpeechRecognition`) chạy trong trình duyệt — dùng **Chrome**
  (máy tính/Android) để nói được; Safari/iOS hỗ trợ hạn chế (vẫn gõ chữ được).
- **ĐỌC**: server sinh giọng nữ tiếng Việt bằng **edge-tts** (`vi-VN-HoaiMyNeural`, miễn
  phí, không cần key) rồi trả MP3 cho trình duyệt phát. Nhờ vậy giọng luôn đúng tiếng Việt,
  KHÔNG phụ thuộc giọng cài trong máy. Nếu `/api/tts` lỗi, tự lùi về giọng trình duyệt.
- **Trí nhớ + lịch sử lưu ở trình duyệt** (`localStorage`) và gửi kèm mỗi request, nên
  function hoàn toàn *stateless* (đúng kiểu serverless, không cần database). Trí nhớ
  gắn với **trình duyệt/thiết bị** đó.

## Bước 1 — Lấy API key Claude

Vào https://console.anthropic.com/ → **API Keys** → tạo key (`sk-ant-...`).
Cần có credit/billing trong tài khoản Anthropic để gọi API.

## Bước 2 — Deploy lên Vercel

```bash
cd web
npm i -g vercel       # nếu chưa có
vercel                # deploy lần đầu (chọn thư mục web/ làm root)
```

Hoặc nối GitHub repo trong dashboard Vercel và đặt **Root Directory = `web`**.

## Bước 3 — Đặt Environment Variables trên Vercel

Project → **Settings → Environment Variables** (xem `.env.example`):

| Biến | Giá trị |
| --- | --- |
| `ANTHROPIC_API_KEY` | khoá Claude (`sk-ant-...`) |
| `LLM_MODEL` | (tuỳ chọn) mặc định `claude-haiku-4-5-20251001` (rẻ & nhanh) |
| `WEATHER_CITY` | (tuỳ chọn) vd `Ho Chi Minh` |

Sau khi đặt xong, **Redeploy** để biến có hiệu lực.

## Chạy thử local

```bash
cd web
cp .env.example .env     # điền giá trị thật
vercel dev               # mở http://localhost:3000
```

## Cách dùng

- Bấm **🎤 Nhấn để nói** → nói tiếng Việt → Min nghe, suy nghĩ, rồi **đọc to** trả lời.
- Bật **Trò chuyện liên tục** để Min tự nghe lại sau mỗi câu trả lời (không phải bấm lại).
- Hoặc gõ chữ ở ô dưới.
- **Xoá trí nhớ & lịch sử** xoá toàn bộ dữ liệu lưu trên trình duyệt này.

## Khác gì bản desktop?

- **Bỏ** mọi tool điều khiển robot (drive/turn/camera/animation/sleep/cube/timer…).
- **Bỏ** Whisper + edge-tts (giọng nói chuyển sang trình duyệt).
- **Giữ**: persona Min, `remember`/`forget`, `get_weather`, `get_news`, tự bắt thông
  tin cá nhân (`auto_capture`), nhớ ngữ cảnh hội thoại.
