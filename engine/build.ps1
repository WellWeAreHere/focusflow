# Builds the engine, runs its tests, and builds the DLL that Python loads.
# Usage: .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force build | Out-Null

$sources = "src\predictors.cpp", "src\selector.cpp", "src\planner.cpp"

# 1. Tests
g++ -std=c++17 -O2 -Wall -Wextra -o build\test_engine.exe tests\test_engine.cpp @sources
if ($LASTEXITCODE -ne 0) { exit 1 }
.\build\test_engine.exe
if ($LASTEXITCODE -ne 0) { exit 1 }

# 2. DLL for Python. -static bundles the C++ runtime (and libwinpthread) into the DLL, so
#    Python can load it without needing C:\msys64\ucrt64\bin on its search path.
g++ -std=c++17 -O2 -Wall -Wextra -shared -static -o build\focusflow.dll src\c_api.cpp @sources
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "built build\focusflow.dll"
