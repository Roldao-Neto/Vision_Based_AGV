from mission import ARRIVED, Mission, Pose


class FakeBridge:
    def __init__(self, acks=None):
        self.calls = []
        self.acks = acks or {}

    def __call__(self, method, *args):
        self.calls.append((method, args))
        ack = self.acks.get(method, True)
        if isinstance(ack, Exception):
            raise ack
        return ack


def make(acks=None):
    bridge = FakeBridge(acks)
    events, paths = [], []
    now = [100.0]
    m = Mission(bridge, lambda name, detail: events.append((name, detail)),
                lambda pid, mm, ack: paths.append((pid, mm, ack)), clock=lambda: now[0])
    return m, bridge, events, paths, now


def pose(state, path_id, wp_idx=0, x=0.0):
    return Pose(rx=100.0, t_ms=0, t_linux=99.98, x=x, y=0.745, theta=0.0, state=state, path_id=path_id, wp_idx=wp_idx)


def names(events):
    return [e[0] for e in events]


def test_start_sends_reset_pose_then_the_path_to_b():
    m, bridge, events, paths, _ = make()
    m.post("start")
    m.step()
    assert bridge.calls == [("reset_pose", (178, 745, 0)), ("set_path", (1, [1581, 745]))]
    assert all(type(v) is int for v in bridge.calls[1][1][1])
    assert m.status == "running"
    assert paths == [(1, [1581, 745], True)]
    assert names(events) == ["mission_start"]


def test_arrived_only_on_the_current_path():
    m, _, events, _, now = make()
    m.on_pose(pose(ARRIVED, 4))  # ARRIVED of an earlier path, still in the last pose
    m.post("start")
    m.step()
    assert m.path_id == 5  # after the last one the STM32 reported
    m.step()
    assert m.status == "running"
    m.on_pose(pose(2, 5))
    m.step()
    assert m.status == "running"
    now[0] = 106.2
    m.on_pose(pose(ARRIVED, 5, x=1.5805))
    m.step()
    assert m.status == "arrived"
    assert names(events) == ["mission_start", "mission_arrived"]
    assert "after=6.20s" in events[-1][1]
    m.on_run_end(5, 6)  # the run_end that follows changes nothing
    m.step()
    assert names(events) == ["mission_start", "mission_arrived"]


def test_run_end_by_target_also_counts():
    m, _, events, _, _ = make()
    m.post("start")
    m.step()
    m.on_run_end(1, 6)
    m.step()
    assert m.status == "arrived"
    assert "seen_by=run_end" in events[-1][1]


def test_other_run_end_fails_and_old_ones_are_ignored():
    m, _, events, _, _ = make()
    m.post("start")
    m.step()
    m.on_run_end(0, 5)  # an earlier run
    m.step()
    assert m.status == "running"
    m.on_run_end(1, 5)
    m.step()
    assert m.status == "failed"
    assert "reason=encoder" in events[-1][1]


def test_abort_sends_idle_and_waits_for_the_run_end():
    m, bridge, events, _, _ = make()
    m.post("start")
    m.step()
    m.post("abort")
    m.step()
    assert bridge.calls[-1] == ("mode", (0, 0, 0, 0, 0))
    assert m.status == "aborting"
    m.on_run_end(1, 3)
    m.step()
    assert m.status == "aborted"
    assert names(events) == ["mission_start", "mission_abort", "mission_aborted"]


def test_refusals_and_bridge_errors_fail_without_moving():
    m, bridge, events, paths, _ = make({"reset_pose": False})
    m.post("start")
    m.step()
    assert m.status == "failed"
    assert [c[0] for c in bridge.calls] == ["reset_pose"]  # no set_path after a refused reset
    assert paths == []
    m, bridge, events, paths, _ = make({"set_path": TimeoutError("no answer")})
    m.post("start")
    m.step()
    assert m.status == "failed"
    assert paths[0][2].__class__ is TimeoutError


def test_start_while_running_and_abort_while_idle_are_rejected():
    m, bridge, events, _, _ = make()
    m.post("abort")
    m.step()
    m.post("start")
    m.post("start")
    m.step()
    assert names(events) == ["mission_rejected", "mission_start", "mission_rejected"]
    assert [c[0] for c in bridge.calls] == ["reset_pose", "set_path"]


def test_a_new_mission_after_the_last_one_ended():
    m, bridge, _, _, _ = make()
    m.post("start")
    m.step()
    m.on_pose(pose(ARRIVED, 1))
    m.step()
    m.post("start")
    m.step()
    assert m.status == "running"
    assert bridge.calls[-1] == ("set_path", (2, [1581, 745]))
