import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alert import notify_if_changed
from apple_pickup import fetch_availability


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            result = fetch_availability()
            test = parse_qs(urlparse(self.path).query).get("test", ["0"])[0]
            result["alert"] = notify_if_changed(
                result,
                self.headers.get("Authorization"),
                test=test.lower() in {"1", "true", "yes"},
            )
            if result["available"]:
                summary = "; ".join(
                    f"{item['store']} {item['title']} {item['quote']}"
                    for item in result["available"]
                )
                print(f"IN STOCK: {summary}")
            else:
                print(
                    f"no stock near {result['postcode']} "
                    f"({len(result['stores'])} stores)"
                )
            status = 200
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            print(f"查询失败: {error}")
            status = 500
            body = json.dumps(
                {"error": str(error)},
                ensure_ascii=False,
            ).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
