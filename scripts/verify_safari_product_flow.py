#!/usr/bin/env python3
"""Parent-run Safari flow: fresh unconfirmed draft per platform, iOS LAN URL, new absolute runtime output. Default plan; no emulation."""
import argparse
import base64
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.capture_browser_closeout import (BrowserError, ROOT, FIXTURE_CREDENTIALS, WebDriver,
    local_driver, load_fixture_account, auth_cookie, capabilities, capture_guard, fixture_origin,
    physical_path, session_capabilities, write_private, error_record)

CAMERAS = [f"cam_0{i}" for i in range(1, 5)]
SAFE_ERRORS = {"assertion_failed", "condition_timeout", "credential_controls_present",
               "webdriver_command_failed", "webdriver_transport_or_protocol_error",
               "native_click_not_observed"}


def need(value):
    if not value:
        raise BrowserError("assertion_failed")


def safe_failure(error):
    code = str(error) if isinstance(error, BrowserError) and str(error) in SAFE_ERRORS else 'unexpected_error'
    record = {'error': code}
    if isinstance(error, BrowserError):
        diagnostic = {}
        status = error.evidence.get('http_status')
        if type(status) is int and 100 <= status <= 599:
            diagnostic['http_status'] = status
        if 'webdriver_error' in error.evidence:
            diagnostic.update(error_record(error.evidence['webdriver_error'], None))
        if diagnostic:
            record['diagnostic'] = diagnostic
    return record


def run_steps(steps, records):
    for name, action in steps:
        start = time.monotonic()
        try:
            details = action()
            records.append({"step": name, "status": "matched", "details": details,
                            "elapsed_ms": (time.monotonic() - start) * 1000})
        except Exception as error:
            records.append({"step": name, "status": "failed", **safe_failure(error),
                            "elapsed_ms": (time.monotonic() - start) * 1000})
            return False
    return True


class Flow:
    def __init__(self, driver: WebDriver, session, args, output):
        self.driver, self.session, self.args, self.output = driver, session, args, output
        self.selected, self.saved, self.anchor = {}, None, None
        self.interactions = []
        self.compact = False
    def command(self, method, suffix, payload=None):
        return self.driver.request(method, self.session + suffix, payload)
    def js(self, script, *args, asynchronous=False):
        return self.command("POST", "/execute/async" if asynchronous else "/execute/sync", {
            "script": "if(location.origin!==arguments[0])throw Error('fixture_origin_mismatch');" + script,
            "args": [self.args.fixture_url, *args]})
    def wait(self, predicate):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)  # Poll readiness only; never repeat clicks or failed steps.
        raise BrowserError("condition_timeout")
    def interaction_state(self, selector):
        return self.js("""
const e=document.querySelector(arguments[1]);
if(!e||!e.getClientRects().length)return {present:false};
const r=e.getBoundingClientRect(),v=visualViewport;
let b={left:v?.offsetLeft||0,top:v?.offsetTop||0,
       right:(v?.offsetLeft||0)+(v?.width||innerWidth),
       bottom:(v?.offsetTop||0)+(v?.height||innerHeight)};
for(let a=e.parentElement;a;a=a.parentElement){
 const s=getComputedStyle(a),q=a.getBoundingClientRect();
 if(/auto|scroll|hidden|clip/.test(s.overflowY)&&q.bottom>b.top&&q.top<b.bottom){
  b.top=Math.max(b.top,q.top);b.bottom=Math.min(b.bottom,q.bottom);
 }
 if(/auto|scroll|hidden|clip/.test(s.overflowX)&&q.right>b.left&&q.left<b.right){
  b.left=Math.max(b.left,q.left);b.right=Math.min(b.right,q.right);
 }
}
const left=Math.max(r.left,b.left),right=Math.min(r.right,b.right),
      top=Math.max(r.top,b.top),bottom=Math.min(r.bottom,b.bottom),
      visible=right>left&&bottom>top,
      x=Math.floor((left+right)/2),y=Math.floor((top+bottom)/2),
      hit=visible&&e.contains(document.elementFromPoint(x,y));
return {present:true,enabled:!e.disabled,hit,x,y,
 scroll_x:Math.floor((b.left+b.right)/2),scroll_y:Math.floor((b.top+b.bottom)/2),
 delta_y:visible?0:Math.round((r.top+r.bottom-b.top-b.bottom)/2)};
""", selector)
    def click(self, selector):
        previous, scrolls = None, 0
        record = {"index": len(self.interactions) + 1, "scroll_actions": 0}
        self.interactions.append(record)
        def positioned():
            nonlocal previous, scrolls
            state = self.interaction_state(selector)
            record.setdefault('before', state)
            record['last'] = state
            if not state.get('present') or not state.get('enabled'):
                return False
            if not state['hit']:
                previous = None
                if state['delta_y'] and scrolls < 8:
                    self.command('POST', '/actions', {'actions': [{
                        'type': 'wheel', 'id': 'flow-scroll', 'actions': [{
                            'type': 'scroll', 'origin': 'viewport', 'duration': 300,
                            'x': state['scroll_x'], 'y': state['scroll_y'],
                            'deltaX': 0, 'deltaY': state['delta_y']}]}]})
                    scrolls += 1
                    record['scroll_actions'] = scrolls
                return False
            position = (state['x'], state['y'])
            stable = position == previous
            previous = position
            return stable
        self.wait(positioned)
        element = self.command("POST", "/element", {"using": "css selector", "value": selector})
        self.js("""
const e=arguments[1],types=['pointerdown','pointerup','mousedown','mouseup','click'];
window.__safariFlowInput={clicked:false,events:[]};
const listener=event=>{if(event.isTrusted){window.__safariFlowInput.events.push(event.type);
 if(event.type==='click')window.__safariFlowInput.clicked=true;}};
for(const type of types)e.addEventListener(type,listener,true);
window.__safariFlowInputCleanup=()=>{for(const type of types)e.removeEventListener(type,listener,true);};
return true;
""", element)
        try:
            self.command("POST", "/element/" + quote(element["element-6066-11e4-a52e-4f735466cecf"], safe="") + "/click", {})
            record['method'] = 'webdriver_element_click'
            def clicked():
                value = self.js('return window.__safariFlowInput;')
                record['native_input'] = value
                return value and value.get('clicked')
            try:
                self.wait(clicked)
            except BrowserError as error:
                if str(error) == 'condition_timeout':
                    raise BrowserError('native_click_not_observed') from None
                raise
        finally:
            try:
                self.js('window.__safariFlowInputCleanup?.();return true;')
            except BrowserError:
                record['observer_cleanup'] = 'unavailable'
    def read(self, kind, camera=None, time_ms=None):
        return self.js("""
const [origin,id,kind,camera,t]=arguments, done=arguments[arguments.length-1], b='/api/v1/tasks/'+encodeURIComponent(id);
const get=async p=>{const r=await fetch(p,{credentials:'same-origin',redirect:'error'});if(!r.ok)throw Error();return r.json()};
(async()=>{if(kind==='auth'){const r=await fetch('/api/v1/users/me',{credentials:'same-origin',redirect:'error'});return {http_status:r.status}}
if(kind==='task'){const d=await get(b);return {draft:d.status==='draft',sequential:d.enrollment_mode==='sequential',count:d.expected_persons,uploaded:d.inputs.filter(x=>x.validation_state==='valid').length}}
if(kind==='status'||kind==='saved'){const d=await get(b+'/sync');const status=['unconfirmed','confirmed','stale','legacy'].includes(d.status)?d.status:'invalid';if(kind==='status')return {status};
return {status,timestamps:Object.fromEntries(['cam_01','cam_02','cam_03','cam_04'].map(c=>[c,Number.isFinite(d.config?.selected_timestamps_ms?.[c])?d.config.selected_timestamps_ms[c]:null]))}}
const p=await get(b+'/sync/preview');if(kind==='preview')return {ready:p.status==='ready',camera_count:Object.keys(p.cameras).length,frame_counts:['cam_01','cam_02','cam_03','cam_04'].map(c=>p.cameras[c]?.frame_count||0)};
const f=await get(b+'/sync/frames/'+camera+'?'+new URLSearchParams({time_ms:String(t),source_version:p.source_versions[camera]}));
return {camera_matches:f.camera===camera,frame_index:f.frame_index,actual_time_ms:f.actual_time_ms,source_pts_ms:f.source_pts_ms};
})().then(done).catch(()=>done({status:'read_failed'}));
""", self.args.task_id, kind, camera, time_ms, asynchronous=True)
    def snapshot(self, name):
        geometry = self.js("return {credentials:!!document.querySelector('.auth-card input,input[type=password],input[name=identity]'),width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,devicePixelRatio};")
        need(isinstance(geometry, dict))
        if geometry.pop("credentials"):
            raise BrowserError("credential_controls_present")
        write_private(self.output / (name + '.geometry.json'), json.dumps(geometry).encode())
        png = base64.b64decode(self.command("GET", "/screenshot"), validate=True)
        need(png.startswith(b'\x89PNG\r\n\x1a\n'))
        write_private(self.output / (name + '.png'), png)
        return geometry
    def authenticate(self):
        self.command("POST", "/url", {"url": self.args.fixture_url + "/login"})
        self.js("return true;")
        self.command("POST", "/cookie", {"cookie": auth_cookie(load_fixture_account(FIXTURE_CREDENTIALS, "user", self.args.account_index))})
        result = self.read("auth"); need(result.get("http_status") == 200)
        return result
    def viewport(self):
        metrics = self.js('return {width:innerWidth,height:innerHeight};')
        if self.args.platform == 'mac':
            outer = self.command('GET', '/window/rect')
            self.command('POST', '/window/rect', {
                'width': 1440 + outer['width'] - metrics['width'],
                'height': 900 + outer['height'] - metrics['height']})
            metrics = self.wait(lambda: (m if m == {'width': 1440, 'height': 900} else None)
                                if (m := self.js('return {width:innerWidth,height:innerHeight};')) else None)
        return metrics
    def expected_cameras(self, camera='cam_01'):
        return {'cam_03', camera if camera != 'cam_03' else 'cam_01'} if self.compact else set(CAMERAS)
    def draft(self):
        self.command("POST", "/url", {"url": self.args.fixture_url + "/workspace/tasks"})
        self.click(f"a.task-title-link[href='/workspace/tasks/{self.args.task_id}']")
        self.wait(lambda: self.js("return location.pathname==='/workspace/new'&&new URLSearchParams(location.search).get('draft')===arguments[1]&&document.querySelectorAll('.upload-card .upload-success').length===5;", self.args.task_id))
        fields = self.js("return [...document.querySelectorAll('.task-registration-fields select')].map(e=>e.value);")
        need(fields == ["sequential", "1"])
        result = self.read("task"); need(result == {"draft": True, "sequential": True, "count": 1, "uploaded": 5})
        return result
    def players(self):
        return self.js("return [...document.querySelectorAll('.video-sync-camera')].filter(e=>!e.hidden).map(e=>({camera:'cam_0'+e.getAttribute('aria-label').match(/[1-4]/)[0],time_ms:Number(e.querySelector('input[type=range]').value),ready:!e.querySelector('.video-sync-select').disabled,selected:e.querySelector('.video-sync-select').getAttribute('aria-pressed')==='true',image:!!e.querySelector('img')?.naturalWidth}));")

    def open(self, number):
        self.selected = {}
        self.click(".task-sync-summary button")
        players = self.wait(lambda: (p if p and all(v['ready'] and v['image'] for v in p) else None) if (p := self.players()) is not None else None)
        layout = self.js("return {width:innerWidth,height:innerHeight,compact:matchMedia('(max-width: 640px)').matches,tabs:!!document.querySelector('.video-sync-tabs')};")
        self.compact = layout['compact']
        need(layout['tabs'] == self.compact and {p['camera'] for p in players} == self.expected_cameras())
        result = self.read("preview"); need(result.get('ready') and result.get('camera_count') == 4 and all(n > 1 for n in result['frame_counts']))
        result['layout'] = layout
        self.anchor = next(p['time_ms'] for p in players if p['camera'] == 'cam_03')
        self.snapshot(f"preview-{number}")
        return result
    def frame(self, direction):
        self.click(f".video-sync-camera.is-anchor .video-sync-frame-controls button:nth-child({3 if direction == 'next' else 2})")
        value = self.wait(lambda: next((p for p in self.players() if p['camera'] == 'cam_03' and p['ready'] and p['image'] and (p['time_ms'] > self.anchor if direction == 'next' else p['time_ms'] == self.anchor)), None))
        return self.frame_json('cam_03', value['time_ms'])
    def frame_json(self, camera, value):
        result = self.read('frame', camera, value)
        need(result.get('camera_matches') and result.get('actual_time_ms') == value and isinstance(result.get('frame_index'), int))
        return result
    def select(self, camera):
        number = int(camera[-1])
        if self.compact and number in (2, 4):
            self.click(f".video-sync-tabs button:nth-child({2 if number == 2 else 3})")
        selector = f'.video-sync-camera:is([aria-label^="Camera {number}"],[aria-label^="机位 {number}"]) .video-sync-select'
        self.click(selector)
        players = self.players(); value = next(p for p in players if p['camera'] == camera)
        need(value['selected'] and value['image'])
        need({p['camera'] for p in players} == self.expected_cameras(camera))
        self.selected[camera] = value['time_ms']
        return {"visible_count": len(players), "selected_count": len(self.selected), **self.frame_json(camera, value['time_ms'])}
    def cancel(self):
        self.click('.video-sync-footer .button-outline')
        self.wait(lambda: self.js("return !document.querySelector('.video-sync-dialog');"))
        return self.status('unconfirmed')
    def status(self, expected):
        value = self.read('status'); need(value.get('status') == expected)
        return value
    def confirm(self):
        self.click('.video-sync-footer .button-primary')
        self.wait(lambda: self.js("return !document.querySelector('.video-sync-dialog')&&!!document.querySelector('.task-sync-summary .is-confirmed');"))
        value = self.read('saved'); need(value.get('status') == 'confirmed' and value.get('timestamps') == self.selected)
        self.saved = value; self.snapshot('confirmed')
        return value
    def persisted(self):
        self.draft()
        self.wait(lambda: self.js("return !!document.querySelector('.task-sync-summary .is-confirmed');"))
        value = self.read('saved'); need(value == self.saved)
        self.snapshot('reopened-confirmed')
        return value


def run(args):
    args.fixture_url = fixture_origin(args.fixture_url, isolated=True)
    requested = capabilities(args.platform, args.device_udid)
    need(bool(re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args.task_id)) and args.account_index >= 0)
    report = {"status": "planned", "platform": args.platform, "browser": "real_safari", "emulation": False, "steps": []}
    if not args.execute_isolated_fixture:
        return report
    capture_guard(args.platform, isolated=True, ios_forwarded=False, origin=args.fixture_url)
    output = physical_path(args.output_dir); need(output.is_relative_to(ROOT / 'runtime') and not output.exists() and output.parent.is_dir())
    output.mkdir(mode=0o700)
    try:
        with local_driver(9415 if args.platform == 'mac' else 9416, 25) as driver:
            session, flow = None, None
            try:
                result = driver.request('POST', '/session', {'capabilities': {'alwaysMatch': requested, 'firstMatch': [{}]}})
                need(bool(re.fullmatch(r'[A-Za-z0-9_-]{1,128}', result.get('sessionId', ''))))
                session = '/session/' + result['sessionId']; negotiated = session_capabilities(result.get('capabilities'))
                need(negotiated.get('platformName', '').lower() in ({'mac', 'macos'} if args.platform == 'mac' else {'ios'}) and negotiated.get('safari:useSimulator') is not True)
                report['capabilities'] = negotiated
                flow = Flow(driver, session, args, output)
                flow.command('POST', '/timeouts', {'pageLoad': 20000, 'script': 20000, 'implicit': 0})
                steps = [('authenticate', flow.authenticate), ('viewport', flow.viewport), ('open_draft', flow.draft), ('initial_status', lambda: flow.status('unconfirmed'))]
                for number in (1, 2):
                    steps += [(f'open_sync_{number}', lambda n=number: flow.open(n))]
                    if number == 1:
                        steps += [('next_frame', lambda: flow.frame('next')), ('previous_frame', lambda: flow.frame('previous'))]
                    steps += [(f'pass_{number}_select_{c}', lambda c=c: flow.select(c)) for c in ('cam_03', 'cam_01', 'cam_02', 'cam_04')]
                    steps += [('cancel_unconfirmed', flow.cancel)] if number == 1 else [('confirm_saved', flow.confirm)]
                steps += [('reopen_persisted', flow.persisted)]
                report['status'] = 'recorded' if run_steps(steps, report['steps']) else 'failed'
            except Exception as error:
                report.update(status='failed', **safe_failure(error))
            finally:
                if flow:
                    report['interactions'] = flow.interactions
                if flow and report['status'] == 'failed':
                    try: report['error_geometry'] = flow.snapshot('error')
                    except Exception: report['error_capture'] = 'unavailable_or_credential_controls'
                if session:
                    try: driver.request('DELETE', session)
                    except Exception: report['session_cleanup'] = 'failed_driver_terminated'
    except Exception:
        report.update(status='failed', error='local_driver_unavailable')
    write_private(output / 'evidence.json', (json.dumps(report, indent=2, allow_nan=False) + '\n').encode())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['mac', 'ios'], required=True)
    parser.add_argument('--device-udid')
    parser.add_argument('--fixture-url', default='http://127.0.0.1:8013')
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--account-index', type=int, default=1)
    parser.add_argument('--execute-isolated-fixture', action='store_true')
    try: report = run(parser.parse_args())
    except Exception: report = {'status': 'failed', 'error': 'invalid_fixture_arguments_or_output'}
    print(json.dumps({'status': report['status'], 'steps': len(report.get('steps', []))}))
    return 2 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
