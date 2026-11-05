# Benchmark: C++ engine vs pure-Python port

Median of repeated runs on one machine (Windows 11, Python 3.11, g++ 14 -O2). Both versions produce identical answers (see `test_equivalence.py`). The C++ column includes the cost of the ctypes bridge. Numbers vary by machine.

| Operation | Python | C++ via ctypes | Speed-up |
|---|---|---|---|
| predict, 100 history rows, 20 tasks | 7.0 ms | 501 us | 14x |
| predict, 500 history rows, 20 tasks | 165.4 ms | 6.5 ms | 25x |
| predict, 2000 history rows, 20 tasks | 2733.0 ms | 91.9 ms | 30x |
| plan, 50 tasks, 480-minute budget | 4.7 ms | 63 us | 74x |
| plan, 200 tasks, 480-minute budget | 19.4 ms | 226 us | 86x |
| plan, 500 tasks, 1440-minute budget | 174.0 ms | 1.7 ms | 100x |
