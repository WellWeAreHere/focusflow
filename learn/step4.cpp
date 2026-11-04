#include <iostream>
#include <string>
#include <vector>
using namespace std;

struct Item {
    string name;
    double value;   // how important / useful this task is
    int minutes;    // predicted time it will take
};

// Greedy plan: repeatedly pick the unused task with the best value per minute
// that still fits in the time we have left.
void greedy_plan(const vector<Item>& items, int budget) {
    vector<bool> used(items.size(), false);   // used[i] = true once we picked task i
    int time_left = budget;
    double total_value = 0;

    cout << "Budget: " << budget << " min" << endl;

    while (true) {
        int best = -1;                         // -1 means "nothing found yet"
        for (size_t i = 0; i < items.size(); i++) {
            if (used[i]) continue;                         // already picked
            if (items[i].minutes > time_left) continue;    // does not fit
            double density = items[i].value / items[i].minutes;
            if (best == -1 || density > items[best].value / items[best].minutes) {
                best = i;
            }
        }
        if (best == -1) break;                 // nothing else fits, we are done

        used[best] = true;
        time_left = time_left - items[best].minutes;
        total_value = total_value + items[best].value;
        cout << "  pick " << items[best].name << " (" << items[best].minutes
             << " min, value " << items[best].value << ")" << endl;
    }
    cout << "  total value = " << total_value << ", unused time = " << time_left << " min" << endl;
}

int main() {
    // Scenario 1: an easy case.
    vector<Item> easy = {
        {"email", 5, 10},
        {"assignment", 40, 60},
        {"revise", 20, 30},
    };
    greedy_plan(easy, 90);

    cout << endl;

    // Scenario 2: a trap.
    vector<Item> trap = {
        {"A", 60, 10},
        {"B", 100, 20},
        {"C", 120, 30},
    };
    greedy_plan(trap, 50);

    return 0;
}
