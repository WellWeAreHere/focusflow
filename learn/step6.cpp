#include <iostream>
#include <string>
#include <vector>
using namespace std;

// ---------- Data ----------

// A finished task from the past (used for learning).
struct Past {
    int category;
    double guessed;
    double actual;
};

// A task I still have to do.
struct Todo {
    string name;
    int category;
    int guessed;     // minutes I think it will take
    int priority;    // 1 (low) to 5 (high)
    int days_left;   // days until the deadline
};

// ---------- Part 1: learning (from steps 1-3) ----------

double average_ratio_for(const vector<Past>& history, int category) {
    double total = 0;
    int count = 0;
    for (size_t i = 0; i < history.size(); i++) {
        if (history[i].category == category) {
            total = total + history[i].actual / history[i].guessed;
            count = count + 1;
        }
    }
    if (count == 0) return 1.0;
    return total / count;
}

// ---------- Part 2: turning a task into numbers for the planner ----------

// How valuable is it to do this task now? Higher priority and nearer deadline = more value.
double value_of(const Todo& t) {
    double urgency = 0;
    if (t.days_left <= 1) urgency = 20;
    else if (t.days_left <= 3) urgency = 10;
    return t.priority * 10 + urgency;
}

// ---------- Part 3: the planner (from step 5) ----------

// Gets the minutes and values of every task, plus the time budget.
// Returns the NUMBERS (positions) of the tasks it chose.
vector<int> choose(const vector<int>& minutes, const vector<double>& values, int budget) {
    int n = minutes.size();
    vector<vector<double>> dp(n + 1, vector<double>(budget + 1, 0));

    for (int i = 1; i <= n; i++) {
        for (int t = 0; t <= budget; t++) {
            dp[i][t] = dp[i - 1][t];
            if (minutes[i - 1] <= t) {
                double take = dp[i - 1][t - minutes[i - 1]] + values[i - 1];
                if (take > dp[i][t]) dp[i][t] = take;
            }
        }
    }

    vector<int> chosen;
    int t = budget;
    for (int i = n; i >= 1; i--) {
        if (dp[i][t] != dp[i - 1][t]) {
            chosen.push_back(i - 1);
            t = t - minutes[i - 1];
        }
    }
    return chosen;
}

// ---------- Printing the result ----------

// Shows a plan, and how long it will REALLY take according to what we learned.
void show_plan(const string& title, const vector<Todo>& todos, const vector<int>& chosen,
               const vector<int>& real_minutes, int budget) {
    cout << title << endl;
    int guessed_total = 0;
    int real_total = 0;
    for (size_t k = 0; k < chosen.size(); k++) {
        int i = chosen[k];
        cout << "  " << todos[i].name << "  (guessed " << todos[i].guessed
             << " min, expected " << real_minutes[i] << " min)" << endl;
        guessed_total = guessed_total + todos[i].guessed;
        real_total = real_total + real_minutes[i];
    }
    cout << "  total guessed = " << guessed_total << " min, "
         << "total expected = " << real_total << " min, budget = " << budget << " min";
    if (real_total > budget) cout << "   <-- OVER BUDGET";
    cout << endl << endl;
}

int main() {
    // 0 = study, 1 = gym, 2 = coding
    vector<Past> history = {
        {0, 30, 45}, {0, 60, 80}, {0, 20, 25},
        {1, 60, 60}, {1, 45, 50},
        {2, 90, 150}, {2, 40, 60},
    };

    vector<Todo> todos = {
        {"Algo assignment", 0, 60, 4, 1},
        {"Gym",             1, 45, 2, 5},
        {"Build API",       2, 90, 5, 2},
        {"Revise notes",    0, 30, 3, 3},
        {"Fix bug",         2, 40, 3, 7},
    };

    int budget = 180;

    // Build the three lists the planner needs.
    vector<int> guessed_minutes;
    vector<int> learned_minutes;
    vector<double> values;
    for (size_t i = 0; i < todos.size(); i++) {
        double ratio = average_ratio_for(history, todos[i].category);
        guessed_minutes.push_back(todos[i].guessed);
        learned_minutes.push_back((int)(todos[i].guessed * ratio + 0.5));   // +0.5 rounds
        values.push_back(value_of(todos[i]));
    }

    // Plan A: trust my guesses.
    vector<int> plan_a = choose(guessed_minutes, values, budget);
    show_plan("Plan A: using my raw guesses", todos, plan_a, learned_minutes, budget);

    // Plan B: use the learned (corrected) minutes.
    vector<int> plan_b = choose(learned_minutes, values, budget);
    show_plan("Plan B: using learned minutes", todos, plan_b, learned_minutes, budget);

    return 0;
}
