"""WebDriver protocol diagnostics; synthetic transport, no browser or credentials."""
import io
import json
import socket
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from scripts.capture_browser_closeout import BrowserError, WebDriver, local_driver


class DriverErrorTests(unittest.TestCase):
    def test_http_click_error_preserves_status_and_standard_code_only(self):
        driver = WebDriver(9415)
        body = json.dumps({"value": {
            "error": "element not interactable",
            "message": "https://fixture/?token=synthetic-secret Cookie=secret",
            "stacktrace": "synthetic-secret",
        }}).encode()
        response = HTTPError(driver.origin, 400, "Bad Request", {}, io.BytesIO(body))
        with patch.object(driver.opener, "open", side_effect=response):
            with self.assertRaises(BrowserError) as caught:
                driver.request("POST", "/session/test/element/test/click", {})
        self.assertEqual(caught.exception.evidence, {
            "http_status": 400, "webdriver_error": "element not interactable",
        })
        self.assertNotIn("synthetic-secret", str(caught.exception.evidence))

    def test_arbitrary_server_error_code_is_not_exposed(self):
        driver = WebDriver(9415)
        body = json.dumps({"value": {"error": "secret-token", "message": "secret"}}).encode()
        response = HTTPError(driver.origin, 500, "Error", {}, io.BytesIO(body))
        with patch.object(driver.opener, "open", side_effect=response):
            with self.assertRaises(BrowserError) as caught:
                driver.request("POST", "/session/test/element/test/click", {})
        self.assertEqual(caught.exception.evidence, {
            "http_status": 500, "webdriver_error": "webdriver_request_failed",
        })


class DriverPortTests(unittest.TestCase):
    def test_recently_closed_port_does_not_block_a_new_owned_driver(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', 0))
            port = server.getsockname()[1]
            server.listen()
            with socket.create_connection(('127.0.0.1', port)) as client:
                connection, _ = server.accept()
                connection.close()  # Server actively closes; its port enters TIME_WAIT.
                self.assertEqual(client.recv(1), b'')
        failure = None
        with patch('scripts.capture_browser_closeout.subprocess.Popen') as start, \
             patch.object(WebDriver, 'request', return_value={}):
            start.return_value.poll.return_value = None
            try:
                with local_driver(port, 1):
                    pass
            except OSError as error:
                failure = error.errno
        self.assertIsNone(failure, 'TIME_WAIT must not be mistaken for an active driver')

    def test_live_listener_is_never_attached_to_or_replaced(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', 0))
            server.listen()
            with patch('scripts.capture_browser_closeout.subprocess.Popen') as start:
                with self.assertRaises(OSError):
                    with local_driver(server.getsockname()[1], 1):
                        self.fail('attached to active listener')
                start.assert_not_called()
