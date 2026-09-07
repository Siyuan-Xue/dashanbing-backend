#!/usr/bin/env python3
"""Explicit test-endpoint measurements; defaults to a network-free plan."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
import re
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

USERS = (1, 5, 10, 20)


class MeasurementError(ValueError):
    """Fixed non-sensitive diagnostic code."""


def distribution(values):
    """Nearest-rank percentiles. Missing samples remain null, not zero."""
    values = sorted(values)
    return {"count": len(values), **{
        f"p{percent}": values[math.ceil(len(values) * percent / 100) - 1] if values else None
        for percent in (50, 95, 99)
    }}


def positive(value):
    if not math.isfinite(value) or value <= 0:
        raise MeasurementError("positive_finite_value_required")
    return value


def validate_base_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in ("", "/")
                or any(ord(c) < 33 for c in value) or "\\" in value
                or (port is not None and port == 0)):
            raise ValueError
    except ValueError:
        raise MeasurementError("explicit_origin_url_required_without_credentials") from None
    return value.rstrip("/")


def validate_path(path: str) -> str:
    # No query credentials, absolute URLs, redirects, or ambiguous path decoding.
    if (not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or "//" in path):
        raise MeasurementError("explicit_simple_endpoint_path_required")
    return path


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(method, url, token, payload, timeout):
    """No proxies from environment, no redirects, TLS verification stays enabled.

    Bodies never enter measurement reports. GPU/auth callers may inspect JSON.
    """
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        if url.endswith("/login/access-token"):
            body = urlencode(payload).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise MeasurementError("response_too_large")
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                data = None
            return response.status, data
    except HTTPError as error:
        status = error.code
        error.close()
        return status, None


def safe_error(error):
    if isinstance(error, (TimeoutError, socket.timeout)) or (
        isinstance(error, URLError) and isinstance(error.reason, TimeoutError)
    ):
        return "timeout"
    if isinstance(error, MeasurementError):
        return str(error)
    return "transport_error"


def load_tokens(env_name: str, base_url: str, *, transport=None, timeout=10):
    validate_base_url(base_url)
    transport = transport or http_request
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
        raise MeasurementError("credentials_env_name_invalid")
    raw = os.environ.get(env_name)
    if not raw:
        raise MeasurementError("test_credentials_unavailable")
    try:
        credentials = json.loads(raw)
        if not isinstance(credentials, list) or not credentials:
            raise ValueError
        identities = []
        for item in credentials:
            if not isinstance(item, dict):
                raise ValueError
            if set(item) == {"token"}:
                identity = item["token"]
            elif set(item) == {"username", "password"}:
                identity = item["username"]
                if not isinstance(item["password"], str) or not item["password"]:
                    raise ValueError
            else:
                raise ValueError
            if not isinstance(identity, str) or not identity or any(ord(c) < 32 for c in identity):
                raise ValueError
            identities.append(identity)
        if len(set(identities)) != len(identities):
            raise ValueError
    except (ValueError, TypeError):
        raise MeasurementError("test_credentials_invalid_or_duplicated") from None
    tokens = []
    for item in credentials:
        if "token" in item:
            token = item["token"]
        else:
            try:
                status, data = transport("POST", base_url + "/api/v1/login/access-token", None, item, timeout)
                if not 200 <= status < 300 or not isinstance(data, dict):
                    raise MeasurementError("authentication_failed")
                token = data.get("access_token")
            except Exception:
                raise MeasurementError("authentication_failed") from None
        if not isinstance(token, str) or not token or any(ord(c) < 33 for c in token):
            raise MeasurementError("authentication_token_invalid")
        tokens.append(token)
    if len(set(tokens)) != len(tokens):
        raise MeasurementError("distinct_test_credentials_required")
    return tokens


def measure(base_url, path, tokens, *, samples=3, timeout=10, transport=None, evidence_kind="real"):
    base_url = validate_base_url(base_url)
    path = validate_path(path)
    positive(samples)
    positive(timeout)
    if type(samples) is not int or len(tokens) < max(USERS) or len(set(tokens)) != len(tokens):
        raise MeasurementError("twenty_distinct_test_credentials_required")
    if evidence_kind not in ("real", "mock"):
        raise MeasurementError("invalid_evidence_kind")
    transport = transport or http_request
    report = {"schema_version": 1, "tool": "measure_capacity", "status": "measured",
              "evidence_kind": evidence_kind, "base_url": base_url, "path": path,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "workload": "closed_loop_authenticated_get", "samples_per_user": samples,
              "percentile_method": "nearest_rank", "runs": []}
    total_started = time.perf_counter()
    for users in USERS:
        barrier = threading.Barrier(users)

        def client(user_index):
            outcomes = []
            barrier.wait()
            for sample in range(samples):
                started = time.perf_counter()
                code, error = None, None
                try:
                    code, _ = transport("GET", base_url + path, tokens[user_index], None, timeout)
                    if not 200 <= code < 300:
                        error = "http_error"
                except Exception as exc:
                    error = safe_error(exc)
                outcomes.append({"user": user_index + 1, "sample": sample + 1,
                                 "http_status": code, "ok": error is None, "error": error,
                                 "latency_ms": (time.perf_counter() - started) * 1000})
            return outcomes

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=users) as executor:
            outcomes = [item for rows in executor.map(client, range(users)) for item in rows]
        wall = time.perf_counter() - started
        report["runs"].append({"users": users, "outcomes": outcomes,
                               "errors": sum(not item["ok"] for item in outcomes),
                               "wall_seconds": wall,
                               "latency_ms": distribution([item["latency_ms"] for item in outcomes]),
                               "successful_latency_ms": distribution([item["latency_ms"] for item in outcomes if item["ok"]])})
    report["wall_seconds"] = time.perf_counter() - total_started
    report["errors"] = sum(run["errors"] for run in report["runs"])
    return report


def add_common_arguments(parser):
    parser.add_argument("--base-url", required=True, help="Explicit dedicated test origin; no implicit server")
    parser.add_argument("--credentials-env", required=True, help="JSON array of token or username/password objects")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Actually call the explicit test server")
    mode.add_argument("--dry-run", action="store_true", help="Network-free plan (also the default)")
    parser.add_argument("--test-environment", action="store_true", help="Attest target/accounts/data are isolated test resources")
    parser.add_argument("--evidence-kind", choices=("real", "mock"), default="real")
    parser.add_argument("--timeout", type=float, default=10, help="HTTP socket timeout seconds")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser)
    parser.add_argument("--path", required=True, help="One explicit authenticated GET endpoint, e.g. /api/v1/presets")
    parser.add_argument("--samples-per-user", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        base_url, path = validate_base_url(args.base_url), validate_path(args.path)
        positive(args.samples_per_user)
        positive(args.timeout)
        if not args.execute:
            report = {"schema_version": 1, "status": "planned", "base_url": base_url, "path": path,
                      "evidence_kind": args.evidence_kind, "users": USERS, "runs": [],
                      "samples_per_user": args.samples_per_user, "required_credentials": max(USERS)}
        else:
            if not args.test_environment:
                raise MeasurementError("isolated_test_environment_acknowledgment_required")
            tokens = load_tokens(args.credentials_env, base_url, timeout=args.timeout)
            report = measure(base_url, path, tokens, samples=args.samples_per_user, timeout=args.timeout,
                             evidence_kind=args.evidence_kind)
    except (MeasurementError, OSError) as error:
        print(json.dumps({"status": "unavailable", "error": safe_error(error), "runs": [], "evidence_kind": args.evidence_kind}))
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    # This is execution status, not a performance verdict. Raw failures stay in JSON.
    return 1 if report.get("errors", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
