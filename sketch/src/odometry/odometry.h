#pragma once

#include <stdint.h>

namespace odometry
{
    // double, not float: a float θ that is never wrapped drifts ~4e-4 rad over two turns from
    // repeated rounding, which would blur the cross-check with the Python reference.
    struct Config
    {
        double m_per_count[2]; // per wheel, [left, right]
        double track_m;        // b, distance between the wheel contact points
    };

    struct State
    {
        double x = 0.0;     // m, axle midpoint
        double y = 0.0;     // m
        double theta = 0.0; // rad, counter-clockwise, not wrapped (an umbmark ends at θ0 ± 2π)
    };

    // One tick of midpoint integration from the count deltas of both wheels:
    // d = (dL + dR)/2, dθ = (dR − dL)/b, x += d·cos(θ + dθ/2), y += d·sin(θ + dθ/2), θ += dθ.
    void update(State &s, const Config &c, int32_t dcount_l, int32_t dcount_r);
}
