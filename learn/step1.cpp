#include <iostream>
using namespace std;

int main() {
    // Five past tasks: how many minutes I GUESSED, and how long they REALLY took.
    double guessed[5] = {30, 60, 20, 45, 90};
    double actual[5]  = {45, 80, 25, 70, 120};

    double total_ratio = 0;

    for (int i = 0; i < 5; i++) {
        double ratio = actual[i] / guessed[i];   // 45 / 30 = 1.5 means "took 50% longer"
        cout << "task " << i << ": ratio = " << ratio << endl;
        total_ratio = total_ratio + ratio;
    }

    double average = total_ratio / 5;
    cout << "average ratio = " << average << endl;

    // Predict a NEW task that I guess will take 40 minutes.
    double new_guess = 40;
    cout << "I guess " << new_guess << " min, so expect about "
         << new_guess * average << " min" << endl;

    return 0;
}
