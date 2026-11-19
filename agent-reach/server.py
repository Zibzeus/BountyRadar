"""Isolated read-only HTTP bridge for the pinned upstream public web channel."""

import hmac
import ipaddress
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from agent_reach.channels.web import WebChannel

slots = BoundedSemaphore(2)


def authorize_url(url):
    approved = set(os.getenv("BOUNTYRADAR_APPROVED_POLICY_URLS", "").splitlines())
    if url not in approved or not url.isascii() or "\\" in url:
        raise ValueError("Policy URL not approved")
    u = urlsplit(url)
    host = (u.hostname or "").lower().rstrip(".")
    if (
        u.scheme != "https"
        or u.username is not None
        or u.password is not None
        or u.fragment
        or u.query
        or host == "immunefi.com"
        or host.endswith(".immunefi.com")
    ):
        raise ValueError("Invalid policy URL")
    ips = [
        ipaddress.ip_address(row[4][0])
        for row in socket.getaddrinfo(host, u.port or 443, type=socket.SOCK_STREAM)
    ]
    if not ips or any(not ip.is_global or ip.is_multicast for ip in ips):
        raise ValueError("Address is restricted")
    return u


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Access logs from the API already identify research runs.

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, code, result):
        data = json.dumps(result).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        if not hmac.compare_digest(
            self.headers.get("Authorization", "").encode(), self.server.authorization
        ):
            self.reply(401, {"error": "Unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.authorized():
            self.reply(
                200, {"provider": "agent_reach"}
            ) if self.path == "/health" else self.reply(404, {})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path not in {"/search", "/read"}:
            return self.reply(404, {})
        if not slots.acquire(blocking=False):
            return self.reply(429, {"error": "All readers busy"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                return self.reply(413, {})
            body = json.loads(self.rfile.read(size))
            url = body["url"]
            u = authorize_url(url)
            channel = WebChannel()
            if self.path == "/search":
                query = f"site:{u.netloc}{u.path} disclosure program policy"
                rows = channel._exa_search(query=query, limit=3, timeout=20)
                return self.reply(
                    200,
                    {
                        "items": [
                            {"url": url, "title": str(x.get("title") or "")[:300]}
                            for x in rows
                            if x.get("url") == url
                        ]
                    },
                )
            text = channel.read(url, timeout=20)
            # Jina embeds upstream access failures in some text responses.
            if any(
                term in text[:5000].lower()
                for term in (
                    "warning: target url returned error",
                    "warning: this page maybe requiring captcha",
                    "warning: target url is blocked",
                )
            ):
                return self.reply(403, {"error": "Source denied access"})
            self.reply(200, {"text": text[:32000]})
        except (ValueError, KeyError, TypeError):
            self.reply(400, {"error": "Invalid request or unapproved URL"})
        except Exception:
            self.reply(502, {"error": "Reader unavailable"})
        finally:
            slots.release()


if __name__ == "__main__":
    path = os.getenv("BOUNTYRADAR_REACH_TOKEN_FILE")
    token = (
        Path(path).read_text().strip()
        if path
        else os.getenv("BOUNTYRADAR_REACH_TOKEN", "")
    )
    if len(token) < 24:
        raise SystemExit("Set a sidecar token of at least 24 characters")
    server = ThreadingHTTPServer(("0.0.0.0", 8787), Handler)
    server.authorization = ("Bearer " + token).encode()
    server.serve_forever()
