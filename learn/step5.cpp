#include <iostream>
#include <string>
#include <vector>
using namespace std;

struct Item {
    string name;
    double value;
    int minutes;
};

// dp[i][t] = the best total value we can get using only the FIRST i tasks
//            when we have t minutes available.
void best_plan(const vector<Item>& items, int budget) {
    int n = items.size();

    // A table with (n+1) rows and (budget+1) columns, all zeros to start.
    vector<vector<double>> dp(n + 1, vector<double>(budget + 1, 0));

    for (int i = 1; i <= n; i++) {
        const Item& item = items[i - 1];        // row i looks at task number i-1
        for (int t = 0; t <= budget; t++) {
            // Option 1: skip this task. Same result as without it.
            dp[i][t] = dp[i - 1][t];

            // Option 2: take it, if it fits. We get its value plus the best
            // we could do with the remaining time and the earlier tasks.
            if (item.minutes <= t) {
                double take = dp[i - 1][t - item.minutes] + item.value;
                if (take > dp[i][t]) dp[i][t] = take;
            }
        }
    }
    for(int i = 0 ; i <= n ; i++){
        for(int t = 0 ; t <= budget ; t++){
            cout << dp[i][t] << " " ;
        }
        cout << endl ;
    }
    cout << "Budget: " << budget << " min" << endl;
    cout << "  best total value = " << dp[n][budget] << endl;

    // Walk backwards through the table to find WHICH tasks were chosen.
    int t = budget;
    for (int i = n; i >= 1; i--) {
        if (dp[i][t] != dp[i-1][t]) {         // value changed, so task i-1 was taken
            cout << "  pick " << items[i - 1].name << " (" << items[i - 1].minutes
                 << " min, value " << items[i - 1].value << ")" << endl;
            t = t - items[i - 1].minutes;
        }
    }
}

int main() {
    // The trap from step 4. Greedy got 160. What does DP get?
    vector<Item> trap = {
        {"A", 6, 1},
        {"B", 10, 2},
        {"C", 12, 3},
    };
    best_plan(trap, 5);

    cout << endl;

    // The X, Y, Z question. Greedy picks only Z (70). What is best?
    vector<Item> xyz = {
        {"X", 50, 30},
        {"Y", 50, 30},
        {"Z", 70, 40},
    };
    best_plan(xyz, 60);

    return 0;
}
