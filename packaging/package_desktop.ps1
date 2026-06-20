$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistRoot = Join-Path $ProjectRoot "dist"
$BundleRoot = Join-Path $DistRoot "YingmingPet"
$AppRoot = Join-Path $BundleRoot "app"
$RuntimeRoot = Join-Path $BundleRoot "runtime\python"
$PythonRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python"
$Csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (!(Test-Path $PythonRoot)) {
    throw "Python runtime not found: $PythonRoot"
}

if (!(Test-Path $Csc)) {
    $Csc = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
}

$ProjectRootPath = [System.IO.Path]::GetFullPath($ProjectRoot)
$BundleRootPath = [System.IO.Path]::GetFullPath($BundleRoot)
if (!$BundleRootPath.StartsWith($ProjectRootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Bundle path is outside the project root: $BundleRootPath"
}

$RunningBundleProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.ExecutablePath -and ([System.IO.Path]::GetFullPath($_.ExecutablePath)).StartsWith($BundleRootPath, [System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.CommandLine -and $_.CommandLine.Contains($BundleRootPath))
}
if ($RunningBundleProcesses) {
    throw "YingmingPet is running from the dist bundle. Close it before packaging."
}

$DataBackup = Join-Path ([System.IO.Path]::GetTempPath()) ("yingming-data-backup-" + [System.Guid]::NewGuid().ToString("N"))
if (Test-Path (Join-Path $BundleRoot "app\data")) {
    Copy-Item -LiteralPath (Join-Path $BundleRoot "app\data") -Destination $DataBackup -Recurse
}

if (Test-Path $BundleRoot) {
    Remove-Item -LiteralPath $BundleRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $AppRoot, $RuntimeRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $ProjectRoot "yingming.py") -Destination $AppRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "yingming_pet.pyw") -Destination $AppRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $AppRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "yingming_core") -Destination $AppRoot -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "personas") -Destination $AppRoot -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "data") -Destination $AppRoot -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "web") -Destination $AppRoot -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "imports") -Destination $AppRoot -Recurse

if (Test-Path $DataBackup) {
    Remove-Item -LiteralPath (Join-Path $AppRoot "data") -Recurse -Force
    Copy-Item -LiteralPath $DataBackup -Destination (Join-Path $AppRoot "data") -Recurse
    Remove-Item -LiteralPath $DataBackup -Recurse -Force
}

Copy-Item -LiteralPath (Join-Path $PythonRoot "python.exe") -Destination $RuntimeRoot
Copy-Item -LiteralPath (Join-Path $PythonRoot "pythonw.exe") -Destination $RuntimeRoot
Copy-Item -Path (Join-Path $PythonRoot "python*.dll") -Destination $RuntimeRoot -ErrorAction SilentlyContinue
Copy-Item -LiteralPath (Join-Path $PythonRoot "vcruntime140.dll") -Destination $RuntimeRoot -ErrorAction SilentlyContinue
Copy-Item -LiteralPath (Join-Path $PythonRoot "vcruntime140_1.dll") -Destination $RuntimeRoot -ErrorAction SilentlyContinue
Copy-Item -LiteralPath (Join-Path $PythonRoot "DLLs") -Destination $RuntimeRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PythonRoot "Lib") -Destination $RuntimeRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PythonRoot "tcl") -Destination $RuntimeRoot -Recurse -ErrorAction SilentlyContinue

$LauncherSource = Join-Path $PSScriptRoot "YingmingPetLauncher.cs"
$LauncherExe = Join-Path $BundleRoot "YingmingPet.exe"
& $Csc /nologo /target:winexe /out:$LauncherExe /reference:System.Windows.Forms.dll $LauncherSource

$Readme = @(
    "Yingming Desktop Pet",
    "",
    "Double-click YingmingPet.exe to start.",
    "",
    "Notes:",
    "- This is a portable bundle. You do not need to open a browser or start a local web server.",
    "- app\data\memory.json stores long-term memory.",
    "- app\data\profile.md stores the user profile.",
    "- Click the Connect button in the pet window to save DeepSeek settings locally.",
    "- app\data\local_settings.json stores local model settings and is not meant for GitHub backup.",
    "- You can also use DEEPSEEK_API_KEY or YINGMING_API_KEY in system environment variables."
) -join [Environment]::NewLine
$Readme | Set-Content -LiteralPath (Join-Path $BundleRoot "README.txt") -Encoding UTF8

Write-Host "Packaged: $LauncherExe"
