# Safari helper and permission preflight — 2026-09-07

Final parent-run outcome: both real Safari sessions were established after the
user enabled the settings. The concentrated Mac flow stopped at the sync-entry
WebDriver click; the iPhone flow stopped at the draft-navigation wait. Neither
completed sync confirmation. Final records, screenshots and scope are in
[release acceptance](../release-acceptance.md) and
[the evidence index](../acceptance/2026-09-07/README.md). The detailed notes below
retain the earlier setup and handoff history; their pending statements describe
that earlier point in time. The temporary fixture server and LAN proxy were
stopped after measurement

This records helper implementation, session-only preflights and one subsequently
blocked capture attempt. **No authenticated browser navigation, screenshots or
final browser acceptance were completed by this helper task.** No production
service was accessed. Parent owns the fixture server and final acceptance document
and has taken over all further Safari preflight and capture.
Parent-reported setup progress after handoff is recorded separately below; it is
not final browser acceptance.

This bounded change owns only `scripts/capture_browser_closeout.py` and this note.
It does not change the earlier recovery/measurement scripts or the parent's files.

## Observed host and device

Read-only commands and their relevant results:

| Command | Observed result |
| --- | --- |
| `/usr/bin/sw_vers` | macOS 26.6.2, build 25G83 |
| `/usr/bin/safaridriver --version` | `Included with Safari 26.6.2 (21624.5.1.11.3)` |
| `plutil -extract CFBundleShortVersionString raw /Applications/Safari.app/Contents/Info.plist` | 26.6.2 |
| `man safaridriver` | Installed manual supports native `platformName: mac` and `platformName: iOS`, physical-device UDID selection, and `safari:useSimulator: false` |
| `xcrun devicectl list devices` inside the sandbox | CoreDevice XPC connection invalidated, then initialization timed out; this is an environment/tooling failure, not evidence that the phone is absent |
| `xcrun devicectl device info details --device '<COREDEVICE_ID>' --timeout 12` outside the sandbox | Exit 0 with partial-information warning: Developer Mode disabled; physical iPhone 16 Pro, iOS 26.6.1, paired, wired, booted |

The supplied UUID is the **CoreDevice identifier**, distinct from the hardware
UDID needed for the Safari capability request. The hardware UDID was read from
the connected device's metadata and used for the actual iOS preflight.

Command records and capability examples in this tracked note redact these values
as `<COREDEVICE_ID>` and `<DEVICE_UDID>`. Private ignored runtime preflight records
may retain actual identifiers. Device name, serial number, network addresses and
other unrelated metadata are omitted here. Reported driver error messages remain
verbatim.

## Initial native Safari requests and blockers

The helper starts its own `/usr/bin/safaridriver -p PORT`, sends standard W3C
WebDriver requests over loopback, and stops only that child process. It never runs
`safaridriver --enable`, `--diagnose`, defaults writes, AppleScript setting changes
or simulator commands. The driver's diagnostic logging is deliberately not enabled.

Mac request, 2026-09-07 **04:27:22 UTC**:

```sh
.venv/bin/python scripts/capture_browser_closeout.py --preflight \
  --platform mac --driver-port 9413 --timeout 12
```

```json
{"capabilities":{"alwaysMatch":{"browserName":"Safari","platformName":"mac"},"firstMatch":[{}]}}
```

Actual response: **HTTP 500**, WebDriver error **`session not created`**, helper
exit **2**, `status: blocked`. Exact returned message:

```text
Could not create a session: You must enable 'Allow remote automation' in the Developer section of Safari Settings to control Safari via WebDriver.
```

The initial sandboxed Mac attempt stopped with
`local_driver_launch_or_permission_error` before obtaining a WebDriver response.
The outside-sandbox attempt above established the actual Safari permission blocker.

Physical iPhone request, 2026-09-07 **04:28:00 UTC**:

```sh
.venv/bin/python scripts/capture_browser_closeout.py --preflight \
  --platform ios --device-udid '<DEVICE_UDID>' \
  --driver-port 9414 --timeout 15
```

```json
{"capabilities":{"alwaysMatch":{"browserName":"Safari","platformName":"iOS","safari:useSimulator":false,"safari:deviceType":"iPhone","safari:deviceUDID":"<DEVICE_UDID>"},"firstMatch":[{}]}}
```

Actual response: **HTTP 500**, WebDriver error **`session not created`**, helper
exit **2**, `status: blocked`. Exact returned message, including its trailing
newline, was:

```json
"Could not create a session: Some devices were found, but could not be used:\n"
```

No device-specific reason followed the colon. This is an attempted native physical
iPhone capability request, not a created session or a rendering pass. A preceding
iOS attempt on reused driver port 9413 stopped with the generic local-driver error
before any WebDriver response; switching to 9414 allowed the request above. The
generic local error did not report an errno, so its exact bind/launch cause was
not established. No other agent's driver was killed or reused.

Both actual WebDriver responses recorded `navigation_performed: false`,
`credentials_read: false`, and `emulation: false`. No automation setting was changed.

## Initial setup directions and prerequisite observations

These directions were given before the user confirmed Safari settings enabled.
The successful later preflights and subsequent capture failure are recorded below;
the initial errors are retained as history, not current assertions that the toggles
remain disabled.

1. **Confirmed Mac blocker:** open **Safari → Settings → Developer → Allow remote
   automation** and enable it if the user wants to authorize automation. If the
   Developer section is hidden, first enable **Settings → Advanced → Show features
   for web developers**. The first path comes directly from the installed driver's
   error; WebKit documents the Developer settings panel and how to expose web
   developer features. [Developer settings](https://webkit.org/blog/14445/webkit-features-in-safari-17-0/),
   [enable developer features](https://webkit.org/web-inspector/enabling-web-inspector/).
2. **iPhone Safari prerequisite to check manually:** in the iPhone's Settings,
   locate **Safari → Advanced**, then check **Web Inspector** and **Remote
   Automation**. Apple documents both toggles for device WebDriver. Their actual
   state was **not read or changed** in this task. Keep the paired phone connected
   and unlocked for the parent's next preflight. The generic device error above
   does not prove either toggle is disabled.
   [Apple's device WebDriver setup](https://developer.apple.com/documentation/safari-developer-tools/ios-enabling-webdriver),
   [WebKit's connected/unlocked-device prerequisites](https://webkit.org/blog/9395/webdriver-is-coming-to-safari-in-ios-13/).
3. **Separately observed CoreDevice limitation:** Developer Mode is disabled, and
   `devicectl` returned only partial information. This does **not** establish that
   Developer Mode is the sole Safari failure or that enabling it will fix Safari.
   If the parent needs CoreDevice developer services, enabling it is an explicit
   user action in **Settings → Privacy & Security → Developer Mode**, followed by
   the device's restart and confirmation. No such change or restart was performed.
   [Apple's Developer Mode instructions](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device).
4. **Phone loopback requires explicit routing:** `localhost` and
   `127.0.0.1` in iPhone Safari refer to the phone, while the parent's fixture
   listens on the Mac's loopback port 8013. USB pairing alone does not establish
   the required HTTP routing. The helper does not expose the server on a LAN,
   install forwarding tools, start a tunnel, or substitute an external URL. The
   parent must independently arrange and verify an authorized device-local
   connection before acknowledging `--ios-localhost-forwarded` for a loopback URL.
   Within the user's real-device testing scope, the parent selected a temporary
   isolated private-LAN fixture as a routine setup proposal. An explicit RFC1918
   Mac IPv4 origin with `--isolated-fixture` is supported and does not require a
   USB-forwarding acknowledgment. Parent waited for Safari enablement and successful
   native preflight before preparing the LAN listener described below. No phone-side
   navigation reached the fixture in this helper task. Parent subsequently reported
   phone-side LAN navigation after handoff, as recorded below.
   This reachability limitation does not prevent a session-only preflight.

These steps describe user-controlled settings and parent-controlled setup. They
are not an instruction for another agent to change settings silently. There is no
browser-emulation fallback or automatic retry/optimization loop.

### Conditional fixture connection proposal for the parent

The user requested testing on the actual iPhone. The parent selected a temporary
isolated private-LAN fixture as necessary routine setup within that scope; the
user did not explicitly request or separately approve the LAN method. This is a
parent-selected setup decision. Parent subsequently prepared the LAN listener after
the user confirmed Safari enablement and both native preflights succeeded. This
helper task did not configure the listener or USB forwarding:

- **Trusted LAN:** keep the existing fixture backend bound to `127.0.0.1:8013`.
  Run a temporary proxy bound to one chosen **private Mac interface address**, on
  port 8013, forwarding solely to that backend. Parent selected an exact fixture-token
  gate for every API request and mutation; this setup does not require a phone-IP
  allowlist. Do not bind all interfaces, create router port forwarding or expose a
  public tunnel. Parent owns the dedicated interface and access gate within the
  real-device testing scope; macOS or iPhone settings changes still require explicit
  user action. The phone would
  navigate to `http://<selected-private-Mac-IP>:8013`. The helper accepts this exact
  origin with `--isolated-fixture`, only for numeric RFC1918 addresses. It does not
  discover interfaces, bind a listener or infer that a private service is a fixture.
- **Trusted USB:** use an independently established and verified reverse connection
  from a phone-local port 8013 to the Mac's loopback fixture. Wired pairing and the
  CoreDevice tunnel are not evidence that such forwarding exists, especially with
  DDI services unavailable. Do not install forwarding tools or change device/network
  settings silently. If the parent verifies this exact route, the helper's existing
  localhost restriction and `--ios-localhost-forwarded` acknowledgment can be used.

These fixture connection choices leave the existing production SSH tunnel untouched. They do not
deploy an application or require a public endpoint. Parent owns listener setup,
reachability verification and cleanup, and must preserve failures as evidence.

The execution sandbox blocks local network access in this environment. Parent
WebDriver/fixture HTTP commands may need `require_escalated` to reach local ports.
A sandbox connection failure must be recorded separately from Safari's HTTP 500
permission response. The actual Mac and iOS responses were obtained outside the
sandbox. A later unauthenticated Mac-side request read only the fixture's login
HTML to check the requested build, as recorded below.

## After enablement: obtained results and parent handoff

After the user confirmed that Mac and iPhone Safari settings were complete, the
helper ran native session-only preflights serially, outside the sandbox:

| Time (2026-09-07 UTC) | Target / port | Actual negotiated capabilities | Result |
| --- | --- | --- | --- |
| 04:57:36 | Mac / 9413 | `browserName: Safari`, `browserVersion: 26.6.2`, `platformName: macOS`, `safari:platformVersion: 26.6.2`, `safari:useSimulator: false` | Exit 0, `session_created`, cleanup `deleted` |
| 04:57:59 | Physical iPhone / 9414 | `browserName: Safari`, `browserVersion: 26.6.1`, `platformName: iOS`, `safari:platformVersion: 26.6.1`, `safari:useSimulator: false`; hardware UDID matched `<DEVICE_UDID>` | Exit 0, `session_created`, cleanup `deleted` |

Both results recorded `credentials_read: false`, `navigation_performed: false`,
and `emulation: false`. There was no device-connection blocker during those two
preflights. Exact commands and private responses are saved under the ignored local
directory `runtime/release-closeout/evidence/safari-preflight/20260907T045736Z/`.

Parent then reported preparing a temporary proxy on the chosen RFC1918 Mac address,
port 8013, forwarding to loopback 8013. Parent's `serve_closeout_phone.py` gates all
API requests and mutations initially using fixture-user index 0's token or the
fixture-admin token; anonymous registration is not exposed. The later switch to
index 1 is recorded below. This is the parent's routine setup
within real-device testing scope, not a separately requested LAN method from the
user. Parent owns the listener and cleanup; this helper did not change its process.

At **05:04:12 UTC**, a Mac-side unauthenticated `GET /login` returned HTTP 200 and
referenced `/assets/index-DpFZHJls.js` and `/assets/index-D1_U1vK7.css`, matching the
parent's requested build. This checked served HTML, not reachability from the phone.

At **05:04:41 UTC**, one physical-iPhone capture attempt was made for
`/workspace/tasks`, using `--account user --account-index 0`, readiness selector
`.task-table tbody tr`, native driver port 9416, and the exact parent-provided LAN
fixture origin. It failed **before session creation, credentials or navigation**:

```json
{"status":"blocked","http_status":500,"webdriver_error":"session not created","message":"Could not create a session: Some devices were found, but could not be used:\n","credentials_read":false,"navigation_performed":false}
```

No screenshot was produced. This later failure does not erase the earlier
successful preflight, and the generic message does not identify a lock, disconnect
or setting as its cause. Only `devicectl ... lockState --help` was inspected; no
device lock-state query was executed before the parent took over. The failed
capture was not retried by this helper task.

The build receipt and failed capture JSON are preserved under the ignored local
directory `runtime/release-closeout/evidence/iphone-native-lan-20260907T050412Z/`.
The parent took over Safari preflight/capture after this attempt. **Do not launch
further Safari sessions from this helper task without a new parent instruction.**
No code changes, settings changes, proxy cleanup or production SSH changes accompanied
this handoff. Later parent results belong in the parent's acceptance record.

### Parent setup update after handoff — still nonfinal

Parent subsequently obtained native `session_created` results for Mac Safari
26.6.2 and physical-iPhone Safari 26.6.1. This helper task read only the saved JSON
status fields and confirmed both results. Their private, ignored raw records are
`runtime/release-closeout/safari-mac-enabled-preflight.json` and
`runtime/release-closeout/safari-ios-enabled-preflight.json`.

Parent reports that its first iPhone LAN capture reached the fixture but failed
authentication because a Chrome logout had invalidated the shared fixture-user
index 0 token. This is a separate, later failure from this helper task's
05:04:41 session-creation failure. Parent retains that raw authentication failure
and switched both its private proxy gate and Safari to the independent fixture-user
index 1. No token or other credential is included in this note.

At this update, parent reports `connectivity002` running. Its outcome and any
authenticated capture remain pending here; no successful capture or final
acceptance is claimed. Parent owns all capture/driver operations, evidence and
listener cleanup. This helper task has not launched another Safari session.

## Helper contract for the parent

The script uses only Python's standard library. It does not import the application,
read `.env`, use a saved browser profile, or consume the normal Safari cookie jar.
The default command prints a plan; `--preflight` creates/deletes a native session
without navigating or reading credentials. An existing WebDriver listener on the
selected port is refused; run sessions serially with a free dedicated port.

For later capture, `--capture --isolated-fixture` is required. Supported origins are
`http://127.0.0.1:8013`, `http://localhost:8013`, `http://[::1]:8013`, and an explicit
canonical `http://<RFC1918-IPv4>:8013` with `--isolated-fixture`. LAN origins require
that flag even in a network-free plan. RFC1918 means exactly `10.0.0.0/8`,
`172.16.0.0/12` and `192.168.0.0/16`; validation does not use the broader
`ipaddress.is_private` property. DNS/public/CGNAT/link-local/documentation/IPv6-LAN
addresses, other ports, HTTPS, URL credentials, queries, fragments and trailing
paths are refused. The parent supplies one explicit test origin; the helper does
not discover addresses or decide whether a private listener contains production
data. Only the dedicated temporary fixture/test account is authorized.

Driver requests use a separate local port, disable environment proxies and refuse
redirects. Browser navigations and final location checks are limited to the exact
selected fixture origin and an allowlist of application pages. The trusted fixture
must also use only authorized assets; the helper does not intercept every browser
subresource. iOS loopback capture still requires `--ios-localhost-forwarded`; iOS
RFC1918 capture does not.

Authentication reads only
`runtime/release-closeout/fixture-credentials.json` in this worktree, and only
during an explicit capture. The bundle must be a private regular file owned by
the current user, have no symlink/hardlink indirection and contain `fixture: true`.
`--account user --account-index 0` selects `accounts[0].token`; `--account admin`
selects `admin.token`. The `jwt_secret` and passwords are neither used nor emitted.

The helper navigates to the local login origin, adds the token using the WebDriver
cookie endpoint as an **HttpOnly, SameSite=Lax `access_token` cookie**, and checks
`/api/v1/users/me` from that Safari session. It records only the status, never the
response body or account identity. No token is put in URLs, JavaScript source,
local storage, screenshots of login fields, evidence JSON or command arguments.
Only session-creation errors before any authentication retain their raw public
diagnostic message; errors after authentication use fixed codes. It never dumps
HTML, cookies, storage, response bodies or WebDriver request payloads.

Example parent-run commands, **not executed here**:

```sh
# Use a new absolute output directory whose parent already exists.
.venv/bin/python scripts/capture_browser_closeout.py --capture --platform mac \
  --fixture-url http://127.0.0.1:8013 --isolated-fixture \
  --account user --account-index 0 --path /workspace/tasks --ready-selector main \
  --driver-port 9415 --output-dir /absolute/new-safari-mac-capture

# Only after independently verified phone-to-fixture loopback routing.
.venv/bin/python scripts/capture_browser_closeout.py --capture --platform ios \
  --device-udid '<DEVICE_UDID>' --ios-localhost-forwarded \
  --fixture-url http://127.0.0.1:8013 --isolated-fixture \
  --account user --account-index 0 --path /workspace/tasks --ready-selector main \
  --driver-port 9416 --output-dir /absolute/new-safari-iphone-capture

# Parent-selected LAN proposal, only after Safari enablement.
# Parent supplies the actual numeric private Mac IP within the real-device scope.
# This placeholder is deliberately not a runnable URL; no LAN listener is started.
.venv/bin/python scripts/capture_browser_closeout.py --capture --platform ios \
  --device-udid '<DEVICE_UDID>' \
  --fixture-url http://MAC_PRIVATE_IPV4:8013 --isolated-fixture \
  --account user --account-index 0 --path /workspace/tasks --ready-selector main \
  --driver-port 9416 --output-dir /absolute/new-safari-iphone-lan-capture
```

Choose a page-specific `--ready-selector` that proves the intended fixture view
has loaded; the default `main` proves only that the main element exists, document
loading is complete and fonts have loaded. The helper records viewport dimensions,
scroll width, pixel ratio, sanitized negotiated Safari capabilities and screenshot
SHA-256. It does not resize to a mobile viewport, spoof a user agent, run a
simulator, synthesize a browser screenshot, or calculate performance metrics.

On success, a new mode-0700 output directory contains `screenshot.png` and
`evidence.json`, both mode 0600. Existing directories/files are never overwritten.
Failures after directory creation leave sanitized blocked evidence and retain any
already-produced screenshot; they are not converted to passes. Capturing is not
final acceptance. Page render and screenshot behavior remain unverified on actual
Safari until the parent runs capture after permissions and reachability are ready.
Exit 0 describes a plan/session/capture result; exit 2 indicates blocked/refused.
Inspect `session_cleanup` too; driver/session cleanup failures remain explicit.

## Focused test and preflight record

`--self-test` embeds synthetic unit tests in the helper to respect the two-file
ownership boundary. These tests do not launch Safari or read the private fixture.

| Stage | Actual result |
| --- | --- |
| Tests written before helper implementation | 6 failures for missing helper functions |
| First implementation self-test | 5 passed, 1 error: macOS temporary-directory alias hit the deliberate symlink refusal |
| Test fixture path changed to its physical path | 6 passed; the production path restriction remained intact |
| Added preflight and failed-credential-read lifecycle tests | 7 passed, 1 failed: attempted capture incorrectly marked navigation as performed before loading credentials |
| Corrected evidence flags to update only after the corresponding operation | `.venv/bin/python scripts/capture_browser_closeout.py --self-test`: **8 tests passed in 0.026s**, exit 0 |
| `--help` and native iOS capability plan | Exit 0; plan had `platformName: iOS`, exact hardware UDID and `safari:useSimulator: false` |
| Actual Mac session preflight outside sandbox | Exit 2, HTTP 500: Remote Automation explicitly disabled/unavailable as quoted above |
| Actual iOS session preflight outside sandbox on port 9414 | Exit 2, HTTP 500: devices found but unusable, no further reason |
| Tests added first for the parent-selected RFC1918 fixture proposal and LAN/USB guard distinction | Exit 1: 12 tests ran; 21 subtest/test errors because the new keyword/behavior was not implemented |
| After RFC1918 support | `.venv/bin/python scripts/capture_browser_closeout.py --self-test`: **12 tests passed in 0.017s**, exit 0 |
| `.venv/bin/python scripts/capture_browser_closeout.py --platform ios --device-udid '<DEVICE_UDID>' --fixture-url http://192.168.2.3:8013 --isolated-fixture` | Exit 0: network-free plan, no credentials read/navigation; device identifier is redacted here; numeric IP was a synthetic validation example, not a discovered or contacted Mac address |

These outcomes preserve implementation failures and actual platform blockers.
The self-test timings are synthetic test-run times, not browser measurements.
The two assigned files also passed whitespace checks, and the helper compiled in
memory. Git reported `codex/ai-analyst`; neither file was staged or committed.


## Parent connectivity check after settings were enabled

On 2026-09-07 the user confirmed both Safari settings enabled. Native sessions then succeeded for macOS Safari 26.6.2 and physical iPhone Safari 26.6.1 (no simulator). The iPhone reached the dedicated temporary private-interface fixture and authenticated as isolated account index 1, capturing `/workspace/new` at CSS viewport 402×714, DPR 3, document width 402. No horizontal overflow was measured in this connectivity capture. These are setup checks preceding the final product-flow measurements, not a full browser acceptance claim.

The first device-page attempt retained an authentication failure: Chrome logout checks had invalidated account index 0's pre-issued fixture token. Using a separate fixture account isolates the two browser workflows. No application authentication bypass was added. Raw setup outcomes remain in ignored `runtime/release-closeout/safari-*-preflight.json` and `safari-ios-connectivity*`.

The parent's `scripts/serve_closeout_phone.py` binds one explicit RFC1918 interface on port 8013 and forwards only to loopback port 8013. Static public UI may load anonymously; API and mutation requests require an exact private test-session token, so other LAN clients cannot register or read fixture business data. Production remains behind its existing SSH tunnel. The temporary proxy is closed after testing.
