# Project: WebOS_JVC_cleanyourtv

Windows-native webOS TV enhancement suite for JVC Smart TVs (LG webOS Hub) based on `webos-vibehack`, with automated SSAP backup/rollback, native PowerShell + Python automation, predecessor attribution, and offline dry-run verification suite.

## Architecture
- **Web App Layer (`app/`)**: Lightweight Apple TV-style launcher (`com.gathin.tvhome`) optimized for JVC SoC (hardware-accelerated CSS `transform`/`opacity` at 60 FPS, remote control key handling [Back 461, OK 13, D-Pad 37-40], Luna Bus `PalmServiceBridge` integration, Outfit font).
- **Communication Layer (`lgtv.py`)**: WebSocket TLS client (`wss://<TV>:3001`) with unsigned client manifest avoiding 403 certificate blacklist on webOS Hub, client key caching (`.lgtv-key.json`), and offline mock mode.
- **App Inventory & Sync (`sync-apps.py`)**: Queries `listLaunchPoints` and `getExternalInputList`, downloads app icons, generates `app/apps.js`.
- **State Snapshot & Rollback Engine (`backup.py`, `restore.py`, `restore.ps1`)**: Automated timestamped snapshots in `backup/<timestamp>/`, SHA-256 manifests (`snapshot.json`), atomic verification, and single-command rollback.
- **Deployment Automation (`install.ps1`)**: Windows-native PowerShell orchestrator validating dependencies, executing pre-flight backup, icon generation, app sync, IPK build (`npx.cmd @webos-tools/cli ares-package`), installation (`ares-install`), and launch (`ares-launch`).
- **Offline Dry-Run Verification Suite (`tools/test_suite.py`, `test.ps1`)**: 4-tier automated test harness with mock SSAP server, static code analysis, icon dimension verification, and backup/restore roundtrip integrity.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | WebOS App Base Structure | Clean Apple TV-style webOS web app (`com.gathin.tvhome`), `appinfo.json` with required ACG permissions, `index.html`, `style.css`, `app.js`, `config.js`, `apps.js`, Outfit typography | M1 | Survey R1 |
| 2 | Python Icon Resizing Tooling | `tools/generate_icons.py` with Pillow engine and .NET `System.Drawing` fallback producing 80x80 (`icon.png`) and 130x130 (`largeIcon.png`), eliminating macOS `sips` | M1 | Survey R1 |
| 3 | Windows PowerShell Deployment | `install.ps1` with parameter parsing (`-TvHost`, `-Device`, `-Skip*`), `npx.cmd` `@webos-tools/cli` integration, pre-flight checks, IPK package & installation | M1 | Survey R1 |
| 4 | Core SSAP Communication & Watcher | `lgtv.py` unsigned manifest pairing, `sync-apps.py` app/input extraction, `home-watch.py` Home button redirection | M1 | Survey R1 |
| 5 | SSAP Snapshot Backup Subsystem | `backup.py` querying `listLaunchPoints`, `getExternalInputList`, `getSystemInfo`, saving timestamped snapshot in `backup/<timestamp>/`, SHA-256 manifest `snapshot.json`, and `latest.json` | M2 | Survey R2 |
| 6 | Rollback & Restore Engine | `restore.py` with SHA-256 integrity validation, local asset restoration (`apps.js`, `config.js`, `icons/`), and TV app reconfiguration/rollback | M2 | Survey R2 |
| 7 | Windows PowerShell Rollback Utility | `restore.ps1` native wrapper supporting `-Latest`, `-Snapshot <path>`, `-List`, `-VerifyOnly`, `-ReinstallToTV`, `-UninstallFromTV` | M2 | Survey R2 |
| 8 | Workflow Safety Integration | `install.ps1` pre-flight automated snapshot, error trapping, and automatic rollback guidance upon failure | M2 | Survey R2 |
| 9 | Predecessor Project Attribution | `README.md` dedicated section prominently thanking `Gathin23/cleanyourtv`, `OmkarK97/webos-vibehack`, `Razdva122/clean-your-tv-lg-webos`, and `lasharor/cleanyourtv-WebOS` | M3 | Survey R3 |
| 10 | Windows Documentation & JVC Guide | `README.md` documenting Windows prerequisites (Python, Node.js, PowerShell), execution policy, JVC LT-32KB116 remote Quick Access button 1, debloating guide, and 5 safety guarantees | M3 | Survey R3 |
| 11 | Offline Test Harness & Mock SSAP | `tools/test_suite.py` mock WebSocket server emulating SSAP handshake, `listLaunchPoints`, `getExternalInputList` without connected TV | M4 / Test Track | Survey R4 |
| 12 | Static Syntax & Schema Verification | Tier 1 test cases: Python AST validation on all `.py` files, JavaScript syntax verification, JSON schema validation (`appinfo.json`, `snapshot.json`), PowerShell syntax | M4 / Test Track | Survey R4 |
| 13 | Icon Generation Verification | Tier 2 test cases: Programmatic validation of 80x80 and 130x130 PNG magic headers, dimensions, and color channels | M4 / Test Track | Survey R4 |
| 14 | Backup & Rollback Verification | Tier 3 & 4 test cases: Verification of backup creation, JSON validation, checksum verification, corrupt snapshot refusal, and 100% roundtrip rollback fidelity | M4 / Test Track | Survey R4 |
| 15 | Cross-Feature Integration & E2E Validation | Tier 4 real-world test cases: End-to-end dry-run workflow testing on Windows with exit code 0 | M4 / Test Track | Survey R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Port of webos-vibehack to Windows | Web app (`app/`), `tools/generate_icons.py`, `lgtv.py`, `sync-apps.py`, `home-watch.py`, `install.ps1` (F1-F4) | none | DONE |
| M2 | SSAP Backup & Rollback System | `backup.py`, `restore.py`, `restore.ps1`, `install.ps1` safety integration (F5-F8) | M1 contracts | DONE |
| M3 | Windows-Centric Documentation & Attribution | `README.md` full update with 4 predecessor attributions, Windows setup, JVC LT-32KB116 guide, safety guarantees (F9-F10) | none | DONE |
| M4 | Final Milestone: Offline Verification Suite & 100% E2E Pass | `tools/test_suite.py`, `test.ps1`, pass 100% of E2E test suite (F11-F15) | M1, M2, M3 | DONE |

## Interface Contracts

### 1. `lgtv.py` ↔ `sync-apps.py` / `backup.py` / `restore.py`
- `lgtv.session(host: str, client_key_path: str = '.lgtv-key.json', mock: bool = False)`:
  - Connects to `wss://<host>:3001` with TLS certificate validation disabled (`ssl.CERT_NONE`, `check_hostname = False`).
  - Performs pairing handshake with unsigned manifest.
  - If `mock=True` or `--offline-mock` flag is passed, returns a mock session.
- `lgtv.call(ws, uri: str, payload: dict = None) -> dict`:
  - Sends SSAP request and returns response dictionary.
  - Supported URIs:
    - `ssap://com.webos.applicationManager/listLaunchPoints` -> `{"returnValue": true, "launchPoints": [...]}`
    - `ssap://tv/getExternalInputList` -> `{"returnValue": true, "devices": [...]}`
    - `ssap://system/getSystemInfo` -> `{"returnValue": true, "modelName": "...", "features": {...}}`
    - `ssap://system.notifications/createToast` -> `{"returnValue": true, "toastId": "..."}`

### 2. Backup & Rollback System (`backup.py`, `restore.py`, `restore.ps1`)
- **Snapshot Directory**: `backup/<YYYYMMDD_HHMMSS>/`
- **Snapshot Contents**:
  - `snapshot.json`: Metadata, timestamp, TV host, files map with SHA-256 hashes.
  - `launch_points.json`: JSON output from `listLaunchPoints`.
  - `inputs.json`: JSON output from `getExternalInputList`.
  - `system_info.json`: JSON output from `getSystemInfo`.
  - `apps.js`: Copy of `app/apps.js` at time of backup.
  - `config.js`: Copy of `app/config.js` at time of backup.
  - `appinfo.json`: Copy of `app/appinfo.json` at time of backup.
  - `icons/`: Copy of cached app icons.
- **Index Pointer**: `backup/latest.json` pointing to the relative path of the most recent snapshot.
- **Restore CLI**:
  - `python restore.py --latest [--offline-mock] [--verify-only]`
  - `python restore.py --snapshot <path> [--offline-mock] [--verify-only]`
  - `python restore.py --list`
- **PowerShell Wrapper**:
  - `.\restore.ps1 [-Latest] [-Snapshot <path>] [-List] [-VerifyOnly] [-ReinstallToTV] [-UninstallFromTV]`

### 3. Icon Generator (`tools/generate_icons.py`)
- CLI: `python tools/generate_icons.py [--source <image_path>] [--output-dir <app_dir>]`
- Defaults: `--source assets/icon.jpg`, `--output-dir app`
- Outputs:
  - `<app_dir>/icon.png` (80x80 RGBA PNG)
  - `<app_dir>/largeIcon.png` (130x130 RGBA PNG)
- Primary engine: `PIL.Image` (Pillow).
- Fallback engine: .NET `System.Drawing.Bitmap` via Python `subprocess` or pure-Python PNG generation.

### 4. Windows Deployment Script (`install.ps1`)
- Parameters:
  - `-TvHost <string>` (Default: `$env:TV_HOST` or `<IP_DEL_TELEVISOR>`)
  - `-Device <string>` (Default: `jvc-tv`)
  - `-AppId <string>` (Default: `com.gathin.tvhome`)
  - `-SkipSync` (Switch)
  - `-SkipIcons` (Switch)
  - `-SkipBuild` (Switch)
  - `-SkipInstall` (Switch)
  - `-SkipLaunch` (Switch)
  - `-SkipBackup` (Switch)
- Pre-flight step:
  - Calls `python backup.py --tv $TvHost` (unless `-SkipBackup` or `-SkipSync`).
- Tooling wrapper:
  - Uses `npx.cmd -y -p @webos-tools/cli <command>` to avoid PowerShell script execution policy issues.
- Error trap:
  - On failure during build or install, suggests `.\restore.ps1 -Latest`.

### 5. Offline Test Suite (`tools/test_suite.py`, `test.ps1`)
- Invocation: `python tools/test_suite.py` or `.\test.ps1`
- Exits with `0` on all passing tests; non-zero on failure.
- Tiers:
  - Tier 1: Static syntax & schema validation.
  - Tier 2: Icon generation dimensions & PNG headers.
  - Tier 3: Mock SSAP protocol handshake & data serialization.
  - Tier 4: Backup creation, corruption detection, and rollback state machine.

## Code Layout
```
c:\Users\ArturoChianNunez\Documents\GitHub\WebOS_JVC_cleanyourtv\
├── app/
│   ├── appinfo.json
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── config.js
│   ├── apps.js
│   ├── assets/
│   │   └── icon.jpg
│   ├── fonts/
│   │   └── outfit.ttf
│   └── icons/
├── backup/
│   └── latest.json
├── docs/
│   └── discovery-cli.png
├── tools/
│   ├── generate_icons.py
│   └── test_suite.py
├── lgtv.py
├── sync-apps.py
├── home-watch.py
├── backup.py
├── restore.py
├── install.ps1
├── restore.ps1
├── test.ps1
├── README.md
├── PROJECT.md
├── TEST_INFRA.md
└── TEST_READY.md
```
