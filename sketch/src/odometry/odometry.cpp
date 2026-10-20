#include "odometry.h"

#include <math.h>

namespace odometry
{
    void update(State &s, const Config &c, int32_t dcount_l, int32_t dcount_r)
    {
        const double dl = (double)dcount_l * c.m_per_count[0];
        const double dr = (double)dcount_r * c.m_per_count[1];
        const double d = 0.5 * (dl + dr);
        const double dtheta = (dr - dl) / c.track_m;
        const double heading = s.theta + 0.5 * dtheta;
        s.x += d * cos(heading);
        s.y += d * sin(heading);
        s.theta += dtheta;
    }
}
