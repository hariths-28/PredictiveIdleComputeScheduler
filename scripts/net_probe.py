"""Network reachability probe for the Phase 0 network test (PRD H-P0-4). Standard library only.

On the coordinator laptop:
    python scripts/net_probe.py serve --port 8000
On every other laptop (LAN IP, Tailscale IP or MagicDNS name of the coordinator):
    python scripts/net_probe.py check http://100.101.102.103:8000
Record the printed result line in docs/runbook/network.md.
"""

import argparse
import json
import platform
import socket
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server naming)
        if self.path.rstrip("/") != "/healthz":
            self.send_error(404, "only /healthz is served")
            return
        body = json.dumps(
            {
                "status": "ok",
                "service": "net_probe",
                "host": socket.gethostname(),
                "os": platform.system(),
                "server_time": time.time(),
                "client": self.client_address[0],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[net_probe] {self.client_address[0]} {fmt % args}")


def serve(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"[net_probe] serving http://{host}:{port}/healthz on {socket.gethostname()} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def check(url: str, count: int, timeout: float) -> int:
    target = url.rstrip("/")
    if not target.endswith("/healthz"):
        target += "/healthz"
    latencies, last_error = [], None
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(target, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
            latencies.append((time.perf_counter() - t0) * 1000)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
        time.sleep(0.2)
    me = f"{socket.gethostname()} ({platform.system()})"
    if latencies:
        latencies.sort()
        median = latencies[len(latencies) // 2]
        print(
            f"RESULT OK   from {me} to {target}: {len(latencies)}/{count} replies, "
            f"median {median:.0f} ms, server={payload.get('host')}"
        )
        return 0
    print(f"RESULT FAIL from {me} to {target}: 0/{count} replies ({last_error})")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="IdleGrid network probe")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run on the coordinator laptop")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    c = sub.add_parser("check", help="run on each worker laptop")
    c.add_argument("url", help="e.g. http://100.101.102.103:8000")
    c.add_argument("--count", type=int, default=5)
    c.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    if args.cmd == "serve":
        serve(args.host, args.port)
        return 0
    return check(args.url, args.count, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
