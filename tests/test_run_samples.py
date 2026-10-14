from run_samples import RunSamples


def test_complete_in_order():
    s = RunSamples(record_id=1, width=3)
    s.add(0, 3, [0, 0, 0, 2000, 1, 2])
    assert not s.complete
    s.add(2, 3, [4000, 3, 5])
    assert s.complete
    assert s.samples == [(0, 0, 0), (2000, 1, 2), (4000, 3, 5)]


def test_ramp_width():
    s = RunSamples(record_id=2, width=4)
    s.add(0, 2, [0, 0, 0, 0, 20000, 1, 0, 0])
    assert s.complete
    assert s.samples == [(0, 0, 0, 0), (20000, 1, 0, 0)]


def test_lost_notification_is_detected():
    s = RunSamples(record_id=1, width=3)
    s.add(0, 4, [0, 0, 0])
    s.add(2, 4, [4000, 3, 5, 6000, 6, 9])  # sample 1 never arrived
    assert s.lost
    assert not s.complete


def test_missing_tail_is_not_complete():
    s = RunSamples(record_id=1, width=3)
    s.add(0, 5, [0, 0, 0, 2000, 1, 2])
    assert not s.lost
    assert not s.complete


def test_total_must_not_change():
    s = RunSamples(record_id=1, width=3)
    s.add(0, 2, [0, 0, 0])
    s.add(1, 3, [2000, 1, 2])
    assert s.lost


def test_values_must_fill_whole_samples():
    s = RunSamples(record_id=1, width=4)
    s.add(0, 1, [0, 0, 0])
    assert s.lost
