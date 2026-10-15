/* Simulated embedded sensor node written in C.
 * Prints one JSON line per reading to stdout:  ./sensor [device] [steps] [seed]
 * Pipe it into the bridge to publish:           ./sensor | python3 -m iot_monitor bridge --mqtt-host localhost
 * Uses a xorshift generator so output is reproducible for a given seed. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static uint32_t state = 2463534242u;

static uint32_t xorshift32(void)
{
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

static double uniform(void) { return (xorshift32() >> 8) / 16777216.0; }

/* Irwin-Hall approximation of a standard normal: sum of 12 uniforms - 6. */
static double gauss(void)
{
    double s = 0.0;
    for (int i = 0; i < 12; i++) s += uniform();
    return s - 6.0;
}

static double clamp(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }

int main(int argc, char **argv)
{
    const char *device = argc > 1 ? argv[1] : "c-node-01";
    int steps = argc > 2 ? atoi(argv[2]) : 100;
    uint32_t seed = argc > 3 ? (uint32_t)strtoul(argv[3], NULL, 10) : 1u;
    if (steps < 0 || steps > 1000000) return 2;
    state ^= seed * 2654435761u;
    if (state == 0) state = 1;

    double t0 = (double)time(NULL);
    for (int i = 0; i < steps; i++) {
        double ts = t0 + i;
        double temp = clamp(70.0 + 3.0 * sin(2.0 * M_PI * i / 120.0) + 0.6 * gauss(), -50.0, 200.0);
        double vib = clamp(2.5 + 0.15 * gauss() + (i == 60 ? 4.0 : 0.0), 0.0, 50.0);   /* shock at step 60 */
        double volt = clamp(230.0 + 1.2 * gauss(), 0.0, 500.0);
        printf("{\"device\":\"%s\",\"metric\":\"temperature\",\"value\":%.3f,\"unit\":\"C\",\"ts\":%.3f,\"seq\":%d}\n", device, temp, ts, i);
        printf("{\"device\":\"%s\",\"metric\":\"vibration\",\"value\":%.3f,\"unit\":\"mm/s\",\"ts\":%.3f,\"seq\":%d}\n", device, vib, ts, i);
        printf("{\"device\":\"%s\",\"metric\":\"voltage\",\"value\":%.3f,\"unit\":\"V\",\"ts\":%.3f,\"seq\":%d}\n", device, volt, ts, i);
    }
    return 0;
}
