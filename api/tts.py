"""Sinh giọng nói tiếng Việt phía SERVER (edge-tts) — Vercel Serverless Function.

Nhận {"text": "..."} qua POST, trả về file MP3 (audio/mpeg) để trình duyệt phát.
Dùng edge-tts (giọng Microsoft online) — MIỄN PHÍ, không cần API key, giọng nữ
tiếng Việt `vi-VN-HoaiMyNeural` (cùng giọng bản robot desktop). Nhờ vậy giọng nói
KHÔNG phụ thuộc vào giọng cài sẵn trong máy/trình duyệt người dùng.

ENV (tuỳ chọn):
  TTS_VOICE  giọng edge-tts, mặc định 'vi-VN-HoaiMyNeural'
             (giọng nam: 'vi-VN-NamMinhNeural')
  TTS_RATE   tốc độ, vd '+0%', '-10%', '+10%' (mặc định '+0%')
"""
from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler

import edge_tts

TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")
MAX_CHARS = 1200  # chặn văn bản quá dài


async def _synth(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            text = (data.get("text") or "").strip()[:MAX_CHARS]
            if not text:
                self._json(400, {"error": "Thiếu 'text'."})
                return
            audio = asyncio.run(_synth(text))
            if not audio:
                self._json(502, {"error": "Không sinh được âm thanh."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(audio)
        except Exception as err:  # noqa: BLE001
            self._json(500, {"error": str(err)})
