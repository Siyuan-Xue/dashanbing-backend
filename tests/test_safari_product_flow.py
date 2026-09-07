"""Offline step-runner tests only; never starts Safari or reads credentials."""
import unittest
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from scripts.verify_safari_product_flow import Flow, run, run_steps
from scripts.capture_browser_closeout import BrowserError


class StepTests(unittest.TestCase):
    def test_session_failure_preserves_protocol_evidence(self):
        class Driver:
            def request(self, *args, **kwargs):
                raise BrowserError('webdriver_command_failed', {
                    'http_status': 500, 'webdriver_error': 'session not created',
                    'message': 'synthetic-private-token'})
        @contextmanager
        def driver(*args):
            yield Driver()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'runtime').mkdir()
            args = SimpleNamespace(platform='mac', device_udid=None, account_index=1,
                fixture_url='http://127.0.0.1:8013', task_id='synthetic-draft',
                execute_isolated_fixture=True, output_dir=root/'runtime'/'result')
            with patch('scripts.verify_safari_product_flow.ROOT', root), \
                 patch('scripts.verify_safari_product_flow.local_driver', driver):
                report = run(args)
        self.assertEqual(report['error'], 'webdriver_command_failed')
        self.assertEqual(report['diagnostic'], {
            'http_status': 500, 'webdriver_error': 'session not created'})
        self.assertNotIn('synthetic-private-token', str(report))

    def test_step_keeps_safe_protocol_failure_evidence(self):
        def fail():
            raise BrowserError("webdriver_command_failed", {
                "http_status": 400, "webdriver_error": "element not interactable",
                "message": "synthetic-private-token", "url": "https://example/?secret",
            })
        records = []
        self.assertFalse(run_steps([("click", fail)], records))
        self.assertEqual(records[0].get("diagnostic"), {
            "http_status": 400, "webdriver_error": "element not interactable",
        })
        self.assertNotIn("synthetic-private-token", str(records))
        self.assertNotIn("https://", str(records))

    def test_failure_stops_flow_and_never_leaks_exception_text(self):
        visited, records = [], []
        def first():
            visited.append("first")
            return {"count": 5}
        def fail():
            visited.append("fail")
            raise RuntimeError("synthetic-private-token-response")
        result = run_steps([("first", first), ("fail", fail),
                            ("never", lambda: visited.append("never"))], records)
        self.assertFalse(result)
        self.assertEqual(visited, ["first", "fail"])
        self.assertEqual(records[0]["details"], {"count": 5})
        self.assertEqual(records[1]["error"], "unexpected_error")
        self.assertNotIn("synthetic-private-token", str(records))

    def test_success_is_once_per_step_and_timing_has_no_pass_threshold(self):
        visited, records = [], []
        def action():
            visited.append("clicked")
            return {"count": 4}
        self.assertTrue(run_steps([("select", action)], records))
        self.assertEqual(visited, ["clicked"])
        self.assertEqual(records[0]["status"], "matched")
        self.assertGreaterEqual(records[0]["elapsed_ms"], 0)


class ClickTests(unittest.TestCase):
    def flow(self, driver):
        return Flow(driver, '/session/test', SimpleNamespace(
            platform='mac', fixture_url='http://127.0.0.1:8013'), Path('/tmp'))

    def test_offscreen_control_scrolls_before_one_native_click(self):
        class Driver:
            scrolled = False
            clicks = 0
            def request(self, method, path, payload=None):
                if path.endswith('/execute/sync'):
                    if '__safariFlowInput' in payload['script']:
                        return {'clicked': self.clicks > 0, 'events': []}
                    return {'present': True, 'enabled': True, 'hit': self.scrolled,
                            'x': 500, 'y': 300 if self.scrolled else 1100,
                            'scroll_x': 500, 'scroll_y': 300,
                            'delta_y': 0 if self.scrolled else 800}
                if path.endswith('/actions'):
                    action = payload['actions'][0]
                    if action['type'] == 'wheel' and action['actions'][0]['deltaY'] == 800:
                        self.scrolled = True
                    return None
                if path.endswith('/element'):
                    return {'element-6066-11e4-a52e-4f735466cecf': 'control'}
                if path.endswith('/click'):
                    if not self.scrolled:
                        raise BrowserError('webdriver_command_failed', {
                            'http_status': 400, 'webdriver_error': 'element not interactable'})
                    self.clicks += 1
        driver = Driver()
        failure = None
        try:
            self.flow(driver).click('.task-sync-summary button')
        except BrowserError as error:
            failure = error.evidence
        self.assertIsNone(failure, 'offscreen target must be brought into view before clicking')
        self.assertEqual(driver.clicks, 1)

    def test_obscured_control_never_receives_click(self):
        class Driver:
            clicks = 0
            def request(self, method, path, payload=None):
                if path.endswith('/execute/sync'):
                    return {'present': True, 'enabled': True, 'hit': False,
                            'x': 500, 'y': 300, 'scroll_x': 500, 'scroll_y': 300, 'delta_y': 0}
                if path.endswith('/element'):
                    return {'element-6066-11e4-a52e-4f735466cecf': 'control'}
                if path.endswith('/click'):
                    self.clicks += 1
        driver = Driver()
        with patch('scripts.verify_safari_product_flow.time.monotonic', side_effect=range(100)), \
             patch('scripts.verify_safari_product_flow.time.sleep'):
            with self.assertRaises(BrowserError):
                self.flow(driver).click('.task-sync-summary button')
        self.assertEqual(driver.clicks, 0)

    def test_successful_command_without_a_trusted_click_is_a_failure(self):
        class Driver:
            def request(self, method, path, payload=None):
                if path.endswith('/execute/sync'):
                    if '__safariFlowInput' in payload['script']:
                        return {'clicked': False, 'events': ['pointerdown', 'mousedown']}
                    return {'present': True, 'enabled': True, 'hit': True,
                            'x': 117, 'y': 255, 'scroll_x': 201, 'scroll_y': 357, 'delta_y': 0}
                if path.endswith('/element'):
                    return {'element-6066-11e4-a52e-4f735466cecf': 'control'}
                return None
        with patch('scripts.verify_safari_product_flow.time.monotonic', side_effect=range(100)), \
             patch('scripts.verify_safari_product_flow.time.sleep'):
            with self.assertRaisesRegex(BrowserError, 'native_click_not_observed'):
                self.flow(Driver()).click('a.task-title-link')


class ViewportTests(unittest.TestCase):
    def test_desktop_setup_accounts_for_browser_chrome(self):
        class Driver:
            width, height = 800, 704
            def request(self, method, path, payload=None):
                if path.endswith('/window/rect'):
                    if method == 'POST':
                        self.width, self.height = payload['width'], payload['height']
                    return {'width': self.width, 'height': self.height}
                if path.endswith('/execute/sync'):
                    return {'width': self.width, 'height': self.height - 52}
        driver = Driver()
        flow = Flow(driver, '/session/test', SimpleNamespace(platform='mac',
                    fixture_url='http://127.0.0.1:8013'), Path('/tmp'))
        self.assertTrue(callable(getattr(flow, 'viewport', None)), 'explicit viewport setup is missing')
        metrics = flow.viewport()
        self.assertEqual(metrics, {'width': 1440, 'height': 900})

    def test_camera_expectation_uses_responsive_layout_on_mac_too(self):
        flow = Flow(None, '/session/test', SimpleNamespace(platform='mac'), Path('/tmp'))
        flow.compact = True
        self.assertTrue(callable(getattr(flow, 'expected_cameras', None)), 'layout-aware expectation is missing')
        self.assertEqual(flow.expected_cameras('cam_04'), {'cam_03', 'cam_04'})
        flow.compact = False
        self.assertEqual(flow.expected_cameras('cam_04'), {'cam_01', 'cam_02', 'cam_03', 'cam_04'})


if __name__ == "__main__":
    unittest.main()
