# Test Infrastructure Specification: WebOS JVC CleanYourTV

## 1. Overview & Strategy

This document details the architecture, design, and operational procedures for the offline verification test suite of `WebOS_JVC_cleanyourtv`.

The primary design principle of the test suite is **100% Offline, Zero-Hardware Independence**:
- Validates all functional, structural, and security aspects of the project on Windows workstations without requiring an active network connection or a physical LG webOS / JVC Smart TV.
- Provides progressive verification across four well-defined tiers, from static syntax checks to end-to-end rollback state machine simulation.
- Guarantees strict exit codes (`0` for success, non-zero for failure) to integrate seamlessly with PowerShell automation and CI/CD pipelines.

---

## 2. Test Architecture & Directory Structure

```
c:\Users\ArturoChianNunez\Documents\GitHub\WebOS_JVC_cleanyourtv\
├── tools/
│   └── test_suite.py       # Main Python 3 test harness (Tiers 1-4)
├── test.ps1                # Native Windows PowerShell test runner
├── TEST_INFRA.md           # This infrastructure specification
└── TEST_READY.md           # Test readiness report & verification matrix
```

### Core Components:
1. **`tools/test_suite.py`**:
   - Standalone test engine implemented in Python 3 standard library (zero external dependencies required for core execution).
   - Dynamically leverages `PIL`/Pillow if available for image assertions; includes built-in binary PNG IHDR parser fallback.
   - Built-in mock SSAP server and protocol emulator for offline request-response validation.
   - Isolated filesystem sandboxing using `tempfile.TemporaryDirectory` to prevent polluting the working tree.
2. **`test.ps1`**:
   - Native PowerShell runner with parameter binding (`-Tier`, `-VerboseOutput`, `-Json`).
   - Propagates Python exit codes to PowerShell `$LASTEXITCODE`.

---

## 3. Detailed Verification Tiers

### Tier 1: Static Syntax, Schemas & Static Analysis
Verifies code integrity and platform schema compliance across all languages and configuration formats used in the repository:
1. **Python AST Validation (`test_python_syntax`)**:
   - Parses every `.py` file in the project (`lgtv.py`, `sync-apps.py`, `home-watch.py`, `backup.py`, `restore.py`, `tools/generate_icons.py`, `tools/test_suite.py`).
   - Uses `ast.parse()` to guarantee syntax correctness before execution.
2. **JavaScript Syntax Verification (`test_javascript_syntax`)**:
   - Validates `app/app.js`, `app/apps.js`, and `app/config.js`.
   - Uses `node --check` when Node.js is present; provides static lexical parser fallback.
3. **WebOS Application Manifest Schema (`test_appinfo_schema`)**:
   - Parses `app/appinfo.json`.
   - Asserts mandatory webOS Hub keys: `id` (matching `^[a-zA-Z0-9_\-\.]+$`), `version` (semver), `type` (`"web"`), `main` (`"index.html"`), `title`, `icon` (`"icon.png"`), and `largeIcon` (`"largeIcon.png"`).
4. **PowerShell Script Integrity (`test_powershell_scripts`)**:
   - Validates `install.ps1`, `restore.ps1`, and `test.ps1`.
   - Checks UTF-8 encoding without BOM corruption.
   - Asserts zero macOS-specific commands (such as `sips` or `pbcopy`).
   - Checks PowerShell syntax using the PowerShell parser if available.

### Tier 2: Asset & Icon Generation Verification
Ensures webOS icon assets meet strict dimension and format constraints required by the webOS Application Manager:
1. **Icon Generation Execution (`test_icon_generation_execution`)**:
   - Runs `tools/generate_icons.py` against a source test image into an isolated sandbox.
   - Asserts exit code `0` and generation of `icon.png` and `largeIcon.png`.
2. **Dimension Verification (`test_icon_dimensions`)**:
   - Reads PNG binary headers:
     - `icon.png`: exactly 80 x 80 pixels.
     - `largeIcon.png`: exactly 130 x 130 pixels.
3. **Format & Magic Header Integrity (`test_icon_format_integrity`)**:
   - Validates standard 8-byte PNG header (`\x89PNG\r\n\x1a\n`).
   - Inspects IHDR chunk: 8-bit depth, RGB (2) or RGBA (6) color type.
4. **Resilience & Missing Asset Handling (`test_icon_missing_source_handling`)**:
   - Invokes `generate_icons.py` with non-existent source path.
   - Asserts graceful non-zero exit and clear error logging without raw unhandled tracebacks.

### Tier 3: Mock SSAP Protocol & Data Pipeline
Emulates the Smart Share Application Protocol (SSAP) WebSocket server for offline app discovery and input mapping:
1. **SSAP Registration Handshake (`test_ssap_registration_handshake`)**:
   - Simulates `wss://<host>:3001` handshake with unsigned manifest.
   - Verifies client token storage into `.lgtv-key.json`.
2. **App Discovery Parsing (`test_ssap_list_launch_points`)**:
   - Injects mock response for `ssap://com.webos.applicationManager/listLaunchPoints`.
   - Verifies extraction of installed applications and proper exclusion of `hidden: true` system apps (such as the launcher itself).
3. **External Input Mapping (`test_ssap_external_inputs`)**:
   - Injects mock response for `ssap://tv/getExternalInputList`.
   - Validates translation of HDMI ports into navigable launcher items with correct labels and app IDs.
4. **App Data Pipeline (`test_apps_js_code_generation`)**:
   - Validates generation of `app/apps.js` declaring `window.APPS` or `window.TV_APPS`.
   - Ensures the output file is syntactically valid JavaScript.

### Tier 4: Backup Creation & Rollback State Machine
Validates state preservation, SHA-256 cryptographic manifests, and byte-for-byte rollback fidelity:
1. **Automated Snapshot Creation (`test_backup_creation`)**:
   - Executes backup routine in dry-run/mock mode into a sandboxed directory.
   - Verifies creation of timestamped directory `backup/<YYYYMMDD_HHMMSS>/`.
   - Asserts snapshot contains `snapshot.json`, `launch_points.json`, `inputs.json`, `apps.js`, `config.js`, and `icons/`.
   - Verifies update of `backup/latest.json`.
2. **Snapshot Schema & SHA-256 Manifest (`test_snapshot_schema_and_manifest`)**:
   - Validates `snapshot.json` schema: timestamp, target TV model (`JVC LT-32KB116`), schema version, and `files` hash table.
   - Computes real SHA-256 hashes of each file and asserts 100% match against `snapshot.json`.
3. **Rollback Byte-for-Byte Fidelity (`test_restore_execution_fidelity`)**:
   - Backs up known state $S_0$.
   - Simulates destructive modification or file corruption in the workspace.
   - Executes `restore.py --latest` (or targeted snapshot).
   - Asserts workspace files are restored to identical byte contents of $S_0$.
4. **Corrupted Snapshot Rejection (`test_corrupted_snapshot_handling`)**:
   - Injects deliberate corruption into a file without updating `snapshot.json` hash.
   - Runs `restore.py`.
   - Asserts integrity check failure, complete copy refusal, and non-zero exit code.

---

## 4. Execution & CLI Options

### Running with Python:
```powershell
# Run all tiers (default)
python tools/test_suite.py

# Run specific tier
python tools/test_suite.py --tier 1
python tools/test_suite.py --tier 2
python tools/test_suite.py --tier 3
python tools/test_suite.py --tier 4

# Verbose output with detailed assertion tracing
python tools/test_suite.py -v

# Machine-readable JSON summary for CI/CD
python tools/test_suite.py --json

# Fail fast (stop on first failure)
python tools/test_suite.py -x
```

### Running with PowerShell Wrapper:
```powershell
# Run all tests
.\test.ps1

# Run specific tier with verbose reporting
.\test.ps1 -Tier 2 -VerboseOutput

# Output JSON summary
.\test.ps1 -Json
```

### Exit Codes:
| Code | Status | Meaning |
|:---:|:---|:---|
| **0** | **PASS** | All executed tests passed completely. |
| **1** | **FAIL** | One or more test assertions failed. |
| **2** | **ERROR** | Invalid CLI arguments, configuration error, or missing test environment prerequisites. |

---

## 5. Integration with Deployment Safety

The offline test suite is integrated directly into the `install.ps1` workflow:
- **Pre-flight Gate**: Before sending any network packets to the TV, `install.ps1` runs `python tools/test_suite.py --tier 1`.
- If syntax or schema errors exist, installation aborts immediately before any TV state is touched.
- Rollback tests in Tier 4 verify that should any stage fail, `.\restore.ps1 -Latest` will restore the system reliably.
