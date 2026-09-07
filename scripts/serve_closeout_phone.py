"""Temporary private-interface proxy to the isolated port-8013 fixture only.

Public static UI may load without authentication. Every API request requires one
of the private fixture tokens, independently of upstream authentication. This
does not expose registration or production data to other LAN clients.
"""
import argparse
import hmac
import http.client
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


def private_bind(value):
    address = ipaddress.IPv4Address(value)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if str(address) != value or not any(address in ipaddress.IPv4Network(n) for n in networks):
        raise ValueError("Use one explicit RFC1918 interface address")
    return value


def allowed_cookie(raw, tokens):
    try:
        cookie = SimpleCookie()
        cookie.load(raw)
        token = cookie["access_token"].value
        return any(hmac.compare_digest(token, expected) for expected in tokens)
    except (KeyError, ValueError, TypeError, CookieError):
        return False


def serve(bind, tokens):
    excluded = {"connection", "proxy-connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def forward(self):
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not self.path.startswith("/") or "%" in parsed.path or "\\" in parsed.path:
                self.send_error(400)
                return
            if (parsed.path.startswith("/api/") or self.command not in {"GET", "HEAD"}) and not allowed_cookie(self.headers.get("Cookie", ""), tokens):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "2")
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(b"{}")
                self.close_connection = True
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 32 * 1024 * 1024 or self.headers.get("Transfer-Encoding"):
                    raise ValueError
            except ValueError:
                self.send_error(413)
                return
            upstream = http.client.HTTPConnection("127.0.0.1", 8013, timeout=30)
            try:
                headers = {key: value for key, value in self.headers.items() if key.lower() not in excluded}
                headers["Host"] = f"{bind}:8013"
                upstream.request(self.command, self.path, self.rfile.read(length) if length else None, headers)
                response = upstream.getresponse()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in excluded:
                        self.send_header(key, value)
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    while block := response.read(64 * 1024):
                        self.wfile.write(block)
            except (OSError, http.client.HTTPException):
                # No headers, credentials, response body or raw error in logs.
                pass
            finally:
                upstream.close()
                self.close_connection = True

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = forward

    ThreadingHTTPServer((bind, 8013), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=private_bind, required=True)
    parser.add_argument("--execute-isolated-fixture", action="store_true")
    args = parser.parse_args()
    if not args.execute_isolated_fixture:
        parser.error("Explicit isolated-fixture acknowledgment required")
    from scripts.capture_browser_closeout import load_fixture_account
    root = Path(__file__).resolve().parents[1]
    credentials = root / "runtime/release-closeout/fixture-credentials.json"
    # Index 1 is reserved for Safari so Chrome logout checks on index 0 cannot
    # invalidate the device's fixture session during independent preparation.
    tokens = {load_fixture_account(credentials, "user", index) for index in (0, 1)}
    tokens.add(load_fixture_account(credentials, "admin", 0))
    serve(args.bind, tokens)


if __name__ == "__main__":
    # Launch as python -m scripts.serve_closeout_phone from the repository root
    main()
