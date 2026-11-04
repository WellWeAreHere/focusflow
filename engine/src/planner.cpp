#include "planner.hpp"

using namespace std;

vector<int> choose(const vector<int>& minutes, const vector<double>& values, int budget) {
    vector<int> chosen;
    if (budget <= 0 || minutes.size() != values.size()) return chosen;

    int n = minutes.size();

    // dp[i][t] = best total value using only the first i tasks with t minutes available.
    vector<vector<double>> dp(n + 1, vector<double>(budget + 1, 0));

    for (int i = 1; i <= n; i++) {
        for (int t = 0; t <= budget; t++) {
            dp[i][t] = dp[i - 1][t];                       // skip task i-1
            if (minutes[i - 1] <= t) {                     // or take it, if it fits
                double take = dp[i - 1][t - minutes[i - 1]] + values[i - 1];
                if (take > dp[i][t]) dp[i][t] = take;
            }
        }
    }

    // Walk backwards through the table to find which tasks were taken.
    int t = budget;
    for (int i = n; i >= 1; i--) {
        if (dp[i][t] != dp[i - 1][t]) {
            chosen.push_back(i - 1);
            t = t - minutes[i - 1];
        }
    }
    return chosen;
}
