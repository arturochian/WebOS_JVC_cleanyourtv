<#
.SYNOPSIS
    Runs the offline verification test suite for WebOS JVC CleanYourTV on Windows.

.DESCRIPTION
    Executes tools/test_suite.py across Tiers 1-4 without requiring an active network
    connection or physical TV hardware. Validates static code integrity, icon assets,
    mock SSAP communication, and backup/rollback state fidelity.

.PARAMETER Tier
    Specify a single tier (1, 2, 3, 4) or 0 for all tiers (default: 0).

.PARAMETER VerboseOutput
    Enables detailed assertion tracing and diagnostic output.

.PARAMETER Json
    Outputs structured machine-readable JSON to stdout for CI/CD integration.

.PARAMETER FailFast
    Halts test execution immediately upon encountering the first failure.

.EXAMPLE
    .\test.ps1
    Runs the full test suite across all 4 tiers.

.EXAMPLE
    .\test.ps1 -Tier 1 -VerboseOutput
    Runs Tier 1 static syntax and schema checks with verbose logging.

.EXAMPLE
    .\test.ps1 -Json
    Outputs JSON summary of all test results.
#>
[CmdletBinding()]
param(
    [ValidateSet(0, 1, 2, 3, 4)]
    [int]$Tier = 0,

    [switch]$VerboseOutput,

    [switch]$Json,

    [switch]$FailFast
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "tools\test_suite.py"

if (-not (Test-Path $scriptPath)) {
    Write-Error "Test suite runner not found at: $scriptPath"
    exit 2
}

$pythonArgs = @($scriptPath)

if ($Tier -ne 0) {
    $pythonArgs += @("--tier", [string]$Tier)
} else {
    $pythonArgs += @("--tier", "all")
}

if ($VerboseOutput) {
    $pythonArgs += @("--verbose")
}

if ($Json) {
    $pythonArgs += @("--json")
}

if ($FailFast) {
    $pythonArgs += @("--failfast")
}

# Execute python test suite
& python @pythonArgs
exit $LASTEXITCODE
