#!/usr/bin/env python3
"""Real Safari WebDriver helper. Default plan; preflight does not navigate."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CREDENTIALS = ROOT / "runtime/release-closeout/fixture-credentials.json"
LOOPBACK_ORIGINS = {"http://127.0.0.1:8013", "http://localhost:8013", "http://[::1]:8013"}
RFC1918 = tuple(ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
SAFE_PAGES = {"/", "/workspace/new", "/workspace/tasks", "/workspace/profiles", "/api/docs",
              "/admin/overview", "/admin/users", "/admin/scheduling", "/admin/quotas",
              "/admin/operations", "/admin/audit"}


class BrowserError(ValueError):
    def __init__(self, code, evidence=None):
        super().__init__(code)
        self.evidence = evidence or {}


def fixture_origin(value, *, isolated=False):
    if value in LOOPBACK_ORIGINS:
        return value
    try:
        address = ipaddress.IPv4Address(urlsplit(value).hostname)
        # Exact canonical syntax excludes credentials, DNS, alternative ports,
        # query/fragment data and paths. is_private also includes non-RFC1918 IPs.
        if value != f"http://{address}:8013" or not any(address in network for network in RFC1918):
            raise ValueError
    except (ValueError, TypeError):
        raise BrowserError("only_loopback_or_explicit_rfc1918_fixture_port_8013_is_supported") from None
    if not isolated:
        raise BrowserError("isolated_fixture_acknowledgment_required_for_lan")
    return value


def capture_path(value):
    if value not in SAFE_PAGES and not re.fullmatch(
        r"/workspace/(?:tasks|profiles)/[A-Za-z0-9_-]+|/workspace/examples/(?:quick-demo|mixed-actions|verified-outcome|layup-demo)", value
    ):
        raise BrowserError("capture_route_not_allowed")
    return value


def capabilities(platform, device_udid=None):
    if platform == "mac":
        return {"browserName": "Safari", "platformName": "mac"}
    if platform != "ios" or not isinstance(device_udid, str) or not re.fullmatch(r"[A-Fa-f0-9-]{16,64}", device_udid):
        raise BrowserError("explicit_physical_device_udid_required")
    return {"browserName": "Safari", "platformName": "iOS", "safari:useSimulator": False,
            "safari:deviceType": "iPhone", "safari:deviceUDID": device_udid}


def capture_guard(platform, *, isolated, ios_forwarded, origin="http://127.0.0.1:8013"):
    if not isolated:
        raise BrowserError("isolated_fixture_acknowledgment_required")
    fixture_origin(origin, isolated=isolated)
    if platform == "ios" and origin in LOOPBACK_ORIGINS and not ios_forwarded:
        raise BrowserError("ios_fixture_loopback_reachability_unverified")


def physical_path(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in [path, *path.parents]):
        raise BrowserError("absolute_path_without_links_required")
    return path


def load_fixture_account(path, account, index):
    """Read only the explicitly authorized fixture credential bundle; never log it."""
    try:
        path = physical_path(path)
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_mode & 0o077 or before.st_uid != os.getuid()):
            raise BrowserError("fixture_credentials_must_be_private_regular_file")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            after = os.fstat(stream.fileno())
            if ((before.st_ino, before.st_dev) != (after.st_ino, after.st_dev)
                    or after.st_nlink != 1 or after.st_mode & 0o077):
                raise BrowserError("fixture_credentials_changed")
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise BrowserError("fixture_credentials_invalid")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("fixture") is not True or index < 0:
            raise BrowserError("marked_fixture_credentials_required")
        selected = data["admin"] if account == "admin" else data["accounts"][index]
        token = selected["token"]
        if not isinstance(token, str) or not token or any(ord(c) < 33 for c in token):
            raise BrowserError("fixture_token_invalid")
        return token
    except (OSError, KeyError, TypeError, IndexError, UnicodeError, json.JSONDecodeError):
        raise BrowserError("fixture_credentials_unavailable_or_invalid") from None


def auth_cookie(token):
    return {"name": "access_token", "value": token, "path": "/", "httpOnly": True,
            "secure": False, "sameSite": "Lax"}


def error_record(error, message, *, public=False):
    known = {"session not created", "unknown error", "invalid argument", "invalid session id",
             "unsupported operation", "timeout", "no such window", "javascript error"}
    result = {"webdriver_error": error if error in known else "webdriver_request_failed"}
    # Public diagnostics are used ONLY before any credentials or navigation.
    if public and isinstance(message, str):
        result["message"] = message[:1500]
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebDriver:
    def __init__(self, port, timeout=15):
        self.origin = f"http://127.0.0.1:{port}"
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, method, path, payload=None, *, public=False):
        raw = None if payload is None else json.dumps(payload).encode()
        request = Request(self.origin + path, raw, {"Content-Type": "application/json"}, method=method)
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                body = response.read(32 * 1024 * 1024 + 1)
                status = response.code
            if len(body) > 32 * 1024 * 1024:
                raise BrowserError("webdriver_response_too_large")
            result = json.loads(body)
            value = result.get("value") if isinstance(result, dict) else None
            if status >= 300 or isinstance(value, dict) and "error" in value:
                value = value if isinstance(value, dict) else {}
                raise BrowserError("webdriver_command_failed", {
                    "http_status": status, **error_record(value.get("error"), value.get("message"), public=public)})
            return value
        except BrowserError:
            raise
        except Exception:
            # No URLs, request bodies, cookies, transport exceptions or stacks.
            raise BrowserError("webdriver_transport_or_protocol_error") from None


@contextmanager
def local_driver(port, timeout):
    if not 1024 <= port <= 65535 or port == 8013:
        raise BrowserError("invalid_dedicated_webdriver_port")
    # Never attach to an existing driver or kill another agent's driver.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    process = subprocess.Popen(["/usr/bin/safaridriver", "-p", str(port)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    driver = WebDriver(port, timeout)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BrowserError("safaridriver_exited_before_ready", {"driver_exit_code": process.returncode})
            try:
                driver.request("GET", "/status")
                break
            except BrowserError:
                time.sleep(0.1)
        else:
            raise BrowserError("safaridriver_start_timeout")
        yield driver
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def session_capabilities(value):
    allowed = ("browserName", "browserVersion", "platformName", "safari:platformVersion",
               "safari:deviceUDID", "safari:useSimulator")
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in allowed if isinstance(value.get(key), (str, bool))}


def ensure_page_origin(driver, session, origin):
    current = driver.request("GET", session + "/url")
    if not isinstance(current, str):
        raise BrowserError("unexpected_browser_location")
    parsed = urlsplit(current)
    if f"{parsed.scheme}://{parsed.netloc}" != origin or parsed.query or parsed.fragment:
        raise BrowserError("browser_left_fixture_origin")
    return parsed.path


def write_private(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def capture(driver, session, args, output, report):
    token = load_fixture_account(FIXTURE_CREDENTIALS, args.account, args.account_index)
    report["credentials_read"] = True
    driver.request("POST", session + "/timeouts", {"pageLoad": int(args.timeout * 1000),
                                                   "script": int(args.timeout * 1000), "implicit": 0})
    report["navigation_attempted"] = True
    driver.request("POST", session + "/url", {"url": args.fixture_url + "/login"})
    report["navigation_performed"] = True
    ensure_page_origin(driver, session, args.fixture_url)
    driver.request("POST", session + "/cookie", {"cookie": auth_cookie(token)})
    del token
    # Authenticate in this real Safari session. Do not return any identity/body.
    status = driver.request("POST", session + "/execute/async", {
        "script": "const done=arguments[arguments.length-1]; fetch('/api/v1/users/me',"
                  "{credentials:'same-origin',redirect:'error'}).then(r=>done(r.status)).catch(()=>done(0));",
        "args": []})
    if status != 200:
        raise BrowserError("fixture_browser_authentication_failed")
    driver.request("POST", session + "/url", {"url": args.fixture_url + args.path})
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if ensure_page_origin(driver, session, args.fixture_url) != args.path:
            raise BrowserError("fixture_route_redirected")
        metrics = driver.request("POST", session + "/execute/sync", {
            "script": "return {ready:document.readyState==='complete' && !!document.querySelector(arguments[0])"
                      " && (!document.fonts || document.fonts.status==='loaded'),"
                      "passwordControl:!!document.querySelector('input[type=password]'),"
                      "width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,"
                      "devicePixelRatio:devicePixelRatio};", "args": [args.ready_selector]})
        if isinstance(metrics, dict) and metrics.get("passwordControl"):
            raise BrowserError("credential_control_present_capture_refused")
        if isinstance(metrics, dict) and metrics.get("ready") is True:
            break
        time.sleep(0.1)
    else:
        raise BrowserError("fixture_ready_selector_timeout")
    raw = driver.request("GET", session + "/screenshot")
    try:
        png = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError):
        raise BrowserError("invalid_screenshot_response") from None
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BrowserError("invalid_png_screenshot")
    write_private(output / "screenshot.png", png)
    return {"status": "captured", "authenticated": True, "route": args.path,
            "metrics": {key: metrics.get(key) for key in ("width", "height", "scrollWidth", "devicePixelRatio")},
            "screenshot": "screenshot.png", "sha256": hashlib.sha256(png).hexdigest()}


def run(args):
    origin = fixture_origin(args.fixture_url, isolated=getattr(args, "isolated_fixture", False))
    requested = capabilities(args.platform, args.device_udid)
    report = {"schema_version": 1, "tool": "capture_browser_closeout", "status": "planned",
              "browser_kind": "real_safari", "requested_capabilities": requested,
              "fixture_origin": origin, "operation": "capture" if args.capture else "preflight" if args.preflight else "plan",
              "created_at": datetime.now(timezone.utc).isoformat(), "emulation": False,
              "navigation_performed": False, "credentials_read": False}
    if not args.preflight and not args.capture:
        return report
    output = None
    if args.capture:
        capture_guard(args.platform, isolated=args.isolated_fixture,
                      ios_forwarded=args.ios_localhost_forwarded, origin=origin)
        capture_path(args.path)
        if args.output_dir is None:
            raise BrowserError("explicit_new_output_directory_required")
        output = physical_path(args.output_dir)
        if output.exists() or not output.parent.is_dir():
            raise BrowserError("output_directory_must_be_new_with_existing_parent")
        output.mkdir(mode=0o700)
    try:
        with local_driver(args.driver_port, args.timeout) as driver:
            session = None
            try:
                result = driver.request("POST", "/session", {"capabilities": {"alwaysMatch": requested, "firstMatch": [{}]}}, public=True)
                identifier = result.get("sessionId") if isinstance(result, dict) else None
                if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
                    raise BrowserError("invalid_session_response")
                session = "/session/" + identifier
                report["negotiated_capabilities"] = session_capabilities(result.get("capabilities"))
                actual = report["negotiated_capabilities"].get("platformName", "").lower()
                if actual not in ({"mac", "macos"} if args.platform == "mac" else {"ios"}):
                    raise BrowserError("unexpected_negotiated_platform")
                if report["negotiated_capabilities"].get("safari:useSimulator") is True:
                    raise BrowserError("simulator_session_refused")
                report["status"] = "session_created"
                if args.capture:
                    report.update(capture(driver, session, args, output, report))
            except BrowserError as error:
                report.update(status="blocked", error=str(error), **error.evidence)
            finally:
                if session:
                    try:
                        driver.request("DELETE", session)
                        report["session_cleanup"] = "deleted"
                    except BrowserError:
                        report["session_cleanup"] = "failed_driver_terminated"
    except (OSError, BrowserError) as error:
        report.update(status="blocked", error=str(error) if isinstance(error, BrowserError) else "local_driver_launch_or_permission_error")
        if isinstance(error, BrowserError):
            report.update(error.evidence)
    if output:
        write_private(output / "evidence.json", (json.dumps(report, indent=2) + "\n").encode())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Synthetic in-process safety tests; no Safari or real credentials")
    parser.add_argument("--platform", choices=("mac", "ios"), default="mac")
    parser.add_argument("--device-udid", help="Physical hardware UDID (not CoreDevice identifier); required for iOS")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--preflight", action="store_true", help="Create/delete session only; no navigation/auth/capture")
    operation.add_argument("--capture", action="store_true", help="Parent-run real Safari fixture screenshot")
    parser.add_argument("--fixture-url", default="http://127.0.0.1:8013",
                        help="Loopback or explicit http://RFC1918-IPv4:8013 with --isolated-fixture")
    parser.add_argument("--driver-port", type=int, default=9413)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--isolated-fixture", action="store_true")
    parser.add_argument("--ios-localhost-forwarded", action="store_true",
                        help="Required only for iOS loopback origins: attest phone-to-Mac fixture forwarding")
    parser.add_argument("--account", choices=("user", "admin"), default="user")
    parser.add_argument("--account-index", type=int, default=0)
    parser.add_argument("--path", default="/workspace/tasks")
    parser.add_argument("--ready-selector", default="main", help="Parent-selected CSS condition for page readiness")
    parser.add_argument("--output-dir", type=Path, help="New explicit directory for screenshot and sanitized JSON")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        if not 0 < args.timeout <= 60:
            raise BrowserError("timeout_must_be_positive_and_at_most_60_seconds")
        report = run(args)
    except (OSError, BrowserError) as error:
        report = {"status": "blocked", "error": str(error) if isinstance(error, BrowserError) else "local_io_error"}
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 2 if report["status"] == "blocked" else 0


def self_test():
    """Embedded synthetic tests keep this bounded change within one script."""
    class ContractTests(unittest.TestCase):
        def require(self, name):
            self.assertTrue(callable(globals().get(name)), f"missing helper: {name}")
            return globals()[name]

        def test_real_platform_capabilities(self):
            build = self.require("capabilities")
            self.assertEqual(build("mac"), {"browserName": "Safari", "platformName": "mac"})
            ios = build("ios", "00008140-0016199E2600401C")
            self.assertEqual(ios["platformName"], "iOS")
            self.assertIs(ios["safari:useSimulator"], False)
            self.assertEqual(ios["safari:deviceUDID"], "00008140-0016199E2600401C")

        def test_only_fixture_loopback_origin_is_accepted(self):
            validate = self.require("fixture_origin")
            self.assertEqual(validate("http://127.0.0.1:8013"), "http://127.0.0.1:8013")
            for url in ("https://example.com", "http://127.0.0.1:8000", "http://user:secret@localhost:8013",
                        "http://localhost:8013?token=secret", "http://localhost:8013/elsewhere"):
                with self.assertRaises(ValueError):
                    validate(url)

        def test_capture_requires_fixture_and_physical_ios_ack(self):
            guard = self.require("capture_guard")
            with self.assertRaises(ValueError):
                guard("mac", isolated=False, ios_forwarded=False)
            with self.assertRaises(ValueError):
                guard("ios", isolated=True, ios_forwarded=False)
            guard("ios", isolated=True, ios_forwarded=True)

        def test_explicit_rfc1918_requires_isolated_fixture(self):
            for origin in ("http://10.2.3.4:8013", "http://172.16.2.3:8013", "http://172.31.2.3:8013", "http://192.168.2.3:8013"):
                with self.subTest(origin=origin):
                    with self.assertRaises(ValueError):
                        fixture_origin(origin)
                    self.assertEqual(fixture_origin(origin, isolated=True), origin)

        def test_public_and_non_rfc1918_origins_remain_refused(self):
            for origin in ("http://8.8.8.8:8013", "http://172.15.2.3:8013", "http://172.32.2.3:8013",
                           "http://100.64.1.2:8013", "http://169.254.1.2:8013", "http://192.0.2.1:8013",
                           "http://example.com:8013", "http://mac.local:8013", "http://[fd00::1]:8013",
                           "http://192.168.1.2:8014", "https://192.168.1.2:8013",
                           "http://user:secret@192.168.1.2:8013", "http://192.168.1.2:8013?token=secret",
                           "http://192.168.1.2:8013/", "http://192.168.1.2:8013#secret"):
                with self.subTest(origin=origin), self.assertRaises(ValueError):
                    fixture_origin(origin, isolated=True)

        def test_ios_lan_does_not_require_usb_forwarding(self):
            capture_guard("ios", isolated=True, ios_forwarded=False, origin="http://192.168.2.3:8013")
            with self.assertRaises(ValueError):
                capture_guard("ios", isolated=False, ios_forwarded=False, origin="http://192.168.2.3:8013")
            with self.assertRaises(ValueError):
                capture_guard("ios", isolated=True, ios_forwarded=False, origin="http://127.0.0.1:8013")

        def test_lan_plan_is_network_and_credential_free(self):
            from types import SimpleNamespace
            from unittest.mock import patch
            args = SimpleNamespace(fixture_url="http://192.168.2.3:8013", platform="ios",
                                   device_udid="00008140-0016199E2600401C", preflight=False,
                                   capture=False, isolated_fixture=True)
            with patch.dict(globals(), {"local_driver": lambda *a: self.fail("plan launched driver"),
                                        "load_fixture_account": lambda *a: self.fail("plan read credentials")}):
                report = run(args)
            self.assertEqual(report["status"], "planned")
            self.assertEqual(report["fixture_origin"], args.fixture_url)
            self.assertFalse(report["navigation_performed"])

        def test_credentials_must_be_private_marked_fixture(self):
            load = self.require("load_fixture_account")
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory).resolve() / "fixture-credentials.json"
                path.write_text(json.dumps({"fixture": True, "accounts": [{"token": "synthetic-private-token"}]}))
                path.chmod(0o600)
                self.assertEqual(load(path, "user", 0), "synthetic-private-token")
                path.chmod(0o644)
                with self.assertRaises(ValueError) as caught:
                    load(path, "user", 0)
                self.assertNotIn("synthetic-private-token", str(caught.exception))
                path.chmod(0o600)
                path.write_text('{"fixture": false, "accounts": []}')
                with self.assertRaises(ValueError):
                    load(path, "user", 0)

        def test_cookie_and_redacted_errors(self):
            cookie = self.require("auth_cookie")("synthetic-private-token")
            self.assertEqual(cookie["name"], "access_token")
            self.assertEqual(cookie["value"], "synthetic-private-token")
            self.assertTrue(cookie["httpOnly"])
            self.assertEqual(cookie["sameSite"], "Lax")
            diagnostic = self.require("error_record")(
                "unknown error", "response echoed synthetic-private-token", public=False)
            self.assertNotIn("synthetic-private-token", json.dumps(diagnostic))

        def test_capture_paths_do_not_include_secret_controls(self):
            validate = self.require("capture_path")
            self.assertEqual(validate("/workspace/tasks"), "/workspace/tasks")
            for path in ("/api/keys", "/login", "/workspace/settings", "//example.com", "/workspace/tasks?token=secret"):
                with self.assertRaises(ValueError):
                    validate(path)

        def test_preflight_never_navigates_or_reads_credentials(self):
            from types import SimpleNamespace
            from unittest.mock import patch
            calls = []

            class FakeDriver:
                def request(self, method, path, payload=None, **kwargs):
                    calls.append((method, path))
                    if path == "/session":
                        return {"sessionId": "synthetic-session", "capabilities": {"platformName": "mac"}}
                    return None

            @contextmanager
            def fake_driver(*args):
                yield FakeDriver()

            args = SimpleNamespace(fixture_url="http://127.0.0.1:8013", platform="mac", device_udid=None,
                                   preflight=True, capture=False, driver_port=9413, timeout=1)
            with patch.dict(globals(), {"local_driver": fake_driver,
                                        "load_fixture_account": lambda *a: self.fail("preflight read credentials")}):
                report = run(args)
            self.assertEqual(calls, [("POST", "/session"), ("DELETE", "/session/synthetic-session")])
            self.assertFalse(report["navigation_performed"])
            self.assertFalse(report["credentials_read"])

        def test_failed_credential_read_does_not_claim_navigation(self):
            import tempfile
            from types import SimpleNamespace
            from unittest.mock import patch

            class FakeDriver:
                def request(self, method, path, payload=None, **kwargs):
                    if path == "/session":
                        return {"sessionId": "synthetic-session", "capabilities": {"platformName": "mac"}}
                    self_test_case.assertEqual(method, "DELETE")

            self_test_case = self

            @contextmanager
            def fake_driver(*args):
                yield FakeDriver()

            def missing(*args):
                raise BrowserError("fixture_credentials_unavailable_or_invalid")

            with tempfile.TemporaryDirectory() as directory:
                args = SimpleNamespace(fixture_url="http://127.0.0.1:8013", platform="mac", device_udid=None,
                                       preflight=False, capture=True, driver_port=9413, timeout=1,
                                       isolated_fixture=True, ios_localhost_forwarded=False,
                                       path="/workspace/tasks", output_dir=Path(directory).resolve() / "capture",
                                       account="user", account_index=0)
                with patch.dict(globals(), {"local_driver": fake_driver, "load_fixture_account": missing}):
                    report = run(args)
                self.assertEqual(report["status"], "blocked")
                self.assertFalse(report["navigation_performed"])
                self.assertFalse(report["credentials_read"])

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
