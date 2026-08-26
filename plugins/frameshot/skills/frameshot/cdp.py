#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cdp — 最小 Chrome DevTools Protocol 客户端（纯标准库）

为什么要它：frameshot 单帧模式每帧起一个 Chrome，冷启动实测 2.2 秒，
占了不联网版式总耗时的九成。批量出帧时复用同一个浏览器实例，
这 2.2 秒就只付一次。内存也恒定 —— 始终只有一个 tab，
不会像「把 N 帧堆进一个超高页面」那样把小内存机器撑爆。

只实现够用的部分：握手、发帧、收帧、几条 Page/Emulation 命令。
不做扩展协商、不做分片发送（请求都很小），分片接收有处理。
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


class CDPError(RuntimeError):
    pass


class WebSocket:
    """够用的客户端 WebSocket：RFC6455 的最小子集。"""

    def __init__(self, url, timeout=60):
        if not url.startswith("ws://"):
            raise CDPError("只支持 ws://（本机调试端口），拿到的是 %s" % url[:40])
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        port = int(port or 80)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        )
        self.sock.sendall(req.encode())

        # 读完握手响应头
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("握手时连接被关闭")
            self.buf += chunk
        head, _, self.buf = self.buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise CDPError("握手失败: %s" % head.split(b"\r\n")[0].decode("latin1"))

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CDPError("连接被关闭")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        payload = text.encode("utf-8")
        n = len(payload)
        header = bytearray([0x81])          # FIN + text
        if n < 126:
            header.append(0x80 | n)          # 客户端必须置掩码位
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv(self):
        """返回一条完整文本消息（自动拼分片，自动应答 ping）。"""
        parts = []
        while True:
            b0, b1 = self._recv_exact(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv_exact(8))[0]
            data = self._recv_exact(length) if length else b""

            if opcode == 0x9:                # ping → pong
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if opcode == 0x8:                # close
                raise CDPError("对端关闭了连接")
            if opcode == 0xA:                # pong
                continue
            parts.append(data)
            if fin:
                return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self.sock.sendall(b"\x88\x80" + os.urandom(4))
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Chrome:
    """常驻无头 Chrome，按需截图。用 with 语句保证退出时收干净。"""

    def __init__(self, binary, port=0, extra_args=()):
        self.binary = binary
        self.port = port or self._free_port()
        self.profile = Path(
            os.environ.get("TMPDIR", "/tmp")) / ("frameshot-cdp-%d" % os.getpid())
        args = [
            binary, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-extensions",
            "--no-first-run", "--no-default-browser-check", "--mute-audio",
            "--remote-debugging-port=%d" % self.port,
            "--user-data-dir=%s" % self.profile,
        ] + list(extra_args)
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self.ws = None
        self._id = 0
        self._connect()

    @staticmethod
    def _free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p

    def _connect(self, deadline=30):
        end = time.time() + deadline
        url = None
        while time.time() < end:
            if self.proc.poll() is not None:
                raise CDPError("Chrome 启动即退出（退出码 %s）" % self.proc.returncode)
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list" % self.port, timeout=2) as r:
                    tabs = json.loads(r.read())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.15)
        if not url:
            raise CDPError("等不到 Chrome 调试端口，%ds 超时" % deadline)
        self.ws = WebSocket(url)
        self.call("Page.enable")

    def call(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") != mid:
                continue                      # 事件或别的响应，丢掉
            if "error" in msg:
                raise CDPError("%s: %s" % (method, msg["error"].get("message")))
            return msg.get("result", {})

    def shoot(self, file_url, width, height, scale=1, settle_ms=250,
              transparent=False):
        """导航到页面并截图，返回 PNG 字节。"""
        self.call("Emulation.setDeviceMetricsOverride",
                  width=width, height=height, deviceScaleFactor=scale, mobile=False)
        if transparent:
            self.call("Emulation.setDefaultBackgroundColorOverride",
                      color={"r": 0, "g": 0, "b": 0, "a": 0})
        else:
            self.call("Emulation.setDefaultBackgroundColorOverride")
        self.call("Page.navigate", url=file_url)

        # 等 load 事件；本地字体与本地图片下，load 到齐就够了
        deadline = time.time() + 30
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Page.loadEventFired":
                break
        time.sleep(settle_ms / 1000.0)        # 留一点排版落定的余量
        r = self.call("Page.captureScreenshot", format="png",
                      captureBeyondViewport=False)
        return base64.b64decode(r["data"])

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            import shutil
            shutil.rmtree(self.profile, ignore_errors=True)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
