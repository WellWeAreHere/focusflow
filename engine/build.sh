#!/usr/bin/env bash
# Linux/macOS twin of build.ps1 (used by CI): runs the engine tests, then builds the shared library
# that Python loads. Usage: bash engine/build.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build

SOURCES="src/predictors.cpp src/selector.cpp src/planner.cpp"

# 1. Tests
g++ -std=c++17 -O2 -Wall -Wextra -o build/test_engine tests/test_engine.cpp $SOURCES
./build/test_engine

# 2. Shared library for Python. -fPIC = "position independent code", required for shared libraries on Linux.
g++ -std=c++17 -O2 -Wall -Wextra -shared -fPIC -o build/libfocusflow.so src/c_api.cpp $SOURCES
echo "built build/libfocusflow.so"
