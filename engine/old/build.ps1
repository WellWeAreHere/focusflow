# Builds and runs the engine tests.  Usage: .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force build | Out-Null

$failed = $false
foreach ($name in "predictors", "knn") {
    g++ -std=c++17 -O2 -Wall -Wextra -o "build\test_$name.exe" "tests\test_$name.cpp" src\predictors.cpp src\knn.cpp
    if ($LASTEXITCODE -ne 0) { exit 1 }
    & ".\build\test_$name.exe"
    if ($LASTEXITCODE -ne 0) { $failed = $true }
}
if ($failed) { exit 1 }
