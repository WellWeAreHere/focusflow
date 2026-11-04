#include <iostream>
#include <string>
#include <vector>
using namespace std;

// A box that describes ONE finished task.
struct Task {
    int category;      // 0 = study, 1 = gym, 2 = coding
    double guessed;
    double actual;
};

// Average ratio, but only counting tasks of one category.
// If there are none, we say 1.0 ("no correction").
double average_ratio_for(const vector<Task>& tasks, int category) {
    double total = 0;
    int count = 0;
    for (size_t i = 0; i < tasks.size(); i++) {
        if (tasks[i].category == category) {
            total = total + tasks[i].actual / tasks[i].guessed;
            count = count + 1;
        }
    }
    if (count == 0) return 1.0;
    return total / count;
}

int main() {
    // All my history in ONE list.
    vector<Task> history = {
        {0, 30, 45},
        {0, 60, 80},
        {0, 20, 25},
        {1, 60, 60},
        {1, 45, 50},
        {2, 90, 150},
        {2, 40, 60},
    };

    vector<string> names = {"study", "gym", "coding"};

    // Adding a task is one line, with no size to update anywhere.
    history.push_back({2, 30, 50});

    for (size_t c = 0; c < names.size(); c++) {
        double ratio = average_ratio_for(history, (int)c);
        cout << names[c] << ": ratio = " << ratio
             << ", a 60 min guess becomes " << 60 * ratio << " min" << endl;
    }

    // A category with no history at all.
    cout << "reading (no history): ratio = " << average_ratio_for(history, 5) << endl;

    return 0;
}
