"""The privileged proxy must refuse raw Engine control and unsafe options."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import controller

NET = "cyberlab-1234abcd"
NAME = "lab-1234abcd-5678abcd"
CID = "a" * 64


def create_payload():
    return {
        "Image": "alpine:3.20",
        "Cmd": ["sh", "-c", "sleep infinity"],
        "Tty": True,
        "AttachStdout": False,
        "HostConfig": {
            "NetworkMode": NET,
            "NanoCpus": 1_000_000_000,
            "Memory": 512 * 1024**2,
            "MemorySwap": 512 * 1024**2,
            "PidsLimit": 256,
        },
    }


class AuthorizationTests(unittest.TestCase):
    def test_all_lab_actions_are_allowlisted(self):
        cases = [
            ("GET", "/_ping", b""),
            ("GET", f"/v1.24/networks/{NET}", b""),
            ("POST", "/v1.24/networks/create", json.dumps({
                "Name": NET, "Driver": "bridge", "Internal": True, "CheckDuplicate": True
            }).encode()),
            ("POST", f"/v1.24/containers/create?name={NAME}",
             json.dumps(create_payload()).encode()),
            ("POST", f"/v1.24/containers/{CID}/start", b""),
            ("POST", f"/v1.24/containers/{CID}/stop?t=2", b""),
            ("GET", f"/v1.24/containers/{CID}/json", b""),
            ("GET", f"/v1.24/containers/{CID}/logs?stdout=1&stderr=1&tail=100", b""),
            ("DELETE", f"/v1.24/containers/{CID}?force=1&v=1", b""),
        ]
        for method, target, payload in cases:
            with self.subTest(method=method, target=target):
                controller.authorize(method, target, payload)

    def test_privileged_and_unrelated_engine_operations_are_denied(self):
        unsafe = [
            ("GET", "/containers/json", b""),
            ("GET", "/v1.24/info", b""),
            ("POST", "/v1.24/containers/create?name=database", b"{}"),
            ("POST", "/v1.24/containers/create?name=lab-../other", b"{}"),
            ("DELETE", f"/v1.24/containers/{CID}?force=0&v=1", b""),
            ("GET", f"/v1.24/containers/{CID}/logs?stdout=1&stderr=1&tail=all", b""),
            ("POST", "/v1.24/networks/create", json.dumps({
                "Name": NET, "Driver": "bridge", "Internal": False, "CheckDuplicate": True
            }).encode()),
        ]
        for method, target, payload in unsafe:
            with self.subTest(target=target), self.assertRaises(controller.Denied):
                controller.authorize(method, target, payload)

    def test_mounts_privileged_flags_and_network_escape_are_denied(self):
        for key, value in [
            ("Privileged", True),
            ("Binds", ["/:/host"]),
            ("CapAdd", ["SYS_ADMIN"]),
            ("NetworkMode", "host"),
        ]:
            body = create_payload()
            body["HostConfig"][key] = value
            with self.subTest(key=key), self.assertRaises(controller.Denied):
                controller.authorize(
                    "POST", f"/v1.24/containers/create?name={NAME}",
                    json.dumps(body).encode()
                )


class ProxyProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_allowed_request_is_forwarded_and_denied_request_is_not(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine_path = str(Path(temp_dir) / "engine.sock")
            control_path = str(Path(temp_dir) / "controller.sock")
            requests = []

            async def fake_engine(reader, writer):
                requests.append(await reader.readuntil(b"\r\n\r\n"))
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            engine = await asyncio.start_unix_server(fake_engine, engine_path)
            controller.ENGINE_SOCKET = engine_path
            service = await asyncio.start_unix_server(controller._handle, control_path)
            try:
                async def send(request):
                    reader, writer = await asyncio.open_unix_connection(control_path)
                    writer.write(request)
                    await writer.drain()
                    result = await reader.read()
                    writer.close()
                    await writer.wait_closed()
                    return result

                denied = await send(
                    b"POST /v1.24/containers/create?name=root HTTP/1.1\r\n"
                    b"Host: docker\r\nContent-Length: 2\r\n\r\n{}"
                )
                self.assertIn(b"403", denied.split(b"\r\n", 1)[0])
                self.assertEqual(requests, [])

                allowed = await send(b"GET /_ping HTTP/1.1\r\nHost: docker\r\n\r\n")
                self.assertIn(b"200 OK", allowed)
                self.assertEqual(len(requests), 1)
            finally:
                service.close()
                engine.close()
                await service.wait_closed()
                await engine.wait_closed()


if __name__ == "__main__":
    unittest.main()
