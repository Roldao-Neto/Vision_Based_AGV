#include "wheel_pi.h"

namespace wheel_pi {
    
    static float sign(float x)
    {
        return x > 0.0f ? 1.0f : (x < 0.0f ? -1.0f : 0.0f);
    }
    
    void reset(State &s)
    {
        s.integ = 0.0f;
        s.v_ref_prev = 0.0f;
    }
    
    float update(State &s, const Config &c, float v_ref, float a_ref, float v_meas, float dt)
    {
        const float v_ref_prev = s.v_ref_prev;
        s.v_ref_prev = v_ref;
        if (v_ref > -c.v_min && v_ref < c.v_min) {
            s.integ = 0.0f;
            return 0.0f;
        }
        if (sign(v_ref) != sign(v_ref_prev)) {
            s.integ = 0.0f;
        }
        const Model &m = v_ref > 0.0f ? c.fwd : c.bwd;
        const float kp = m.tau / (m.k * c.t_cl);
        const float ki = 1.0f / (m.k * c.t_cl);
        const float e = 0.5f * (v_ref + v_ref_prev) - v_meas;
        const float ff = m.pwm0 * sign(v_ref) + (v_ref + m.tau * a_ref) / m.k;
        const float u_raw = ff + kp * e + s.integ;
        const float u = u_raw > c.u_max ? c.u_max : (u_raw < -c.u_max ? -c.u_max : u_raw);
        if (u == u_raw || sign(e) != sign(u_raw)) {
            s.integ += ki * e * dt;
        }
        return u;
    }
}
