from command_file import take_commands
from mcu_commands import IDLE, parse


def test_commands_come_oldest_first_and_are_deleted(tmp_path):
    (tmp_path / "1791741000000000002.cmd").write_text("idle\n")
    (tmp_path / "1791741000000000001.cmd").write_text("path 1 1581 745\n")
    assert take_commands(tmp_path) == ["path 1 1581 745", "idle"]
    assert list(tmp_path.iterdir()) == []


def test_files_still_being_written_are_left_alone(tmp_path):
    (tmp_path / ".1791741000000000001.tmp").write_text("idle\n")
    assert take_commands(tmp_path) == []
    assert (tmp_path / ".1791741000000000001.tmp").exists()


def test_commands_left_from_before_start_are_discarded(tmp_path):
    # mission() drains cmd/ once at start and only logs what it finds; later reads run commands.
    (tmp_path / "1791741000000000001.cmd").write_text("reset_pose 178 745 0\n")
    (tmp_path / "1791741000000000002.cmd").write_text("")
    assert take_commands(tmp_path) == ["reset_pose 178 745 0"]
    assert list(tmp_path.iterdir()) == []
    (tmp_path / "1791741000000000003.cmd").write_text("idle\n")
    assert take_commands(tmp_path) == ["idle"]


def test_missing_dir_means_no_commands(tmp_path):
    assert take_commands(tmp_path / "cmd") == []


def test_parse():
    assert parse("idle") == ("mode", (IDLE, 0, 0, 0, 0))
    assert parse("  idle ") == ("mode", (IDLE, 0, 0, 0, 0))
    assert parse("idle 3") is None
    assert parse("stop") == ("stop", ())
    assert parse("stop 1") is None
    assert parse("") is None
    assert parse("count start") is None  # Day 1 modes are gone
    assert parse("speed 250 500 1500 450") is None  # retired on Day 2
    assert parse("straight 250 500 8000 1380") is None  # retired on Day 3
    assert parse("umbmark 1 1000 250 30000") is None


def test_parse_reset_pose():
    assert parse("reset_pose 178 745 0") == ("reset_pose", (178, 745, 0))
    assert parse("reset_pose 178 745 -1571") == ("reset_pose", (178, 745, -1571))
    assert parse("reset_pose 178 745") is None
    assert parse("reset_pose 0.178 0.745 0") is None


def test_parse_path():
    assert parse("path 1 1581 745") == ("set_path", (1, [1581, 745]))
    assert parse("path 2 1000 745 1000 1100 500 1100") == ("set_path", (2, [1000, 745, 1000, 1100, 500, 1100]))
    assert parse("path 1") is None
    assert parse("path 1 1581") is None  # odd number of values
    assert parse("path 1 1581.0 745") is None
    # Out-of-arena values still parse: the MCU is the one that refuses them.
    assert parse("path 1 5000 -10") == ("set_path", (1, [5000, -10]))
    # Native ints only: msgpack refuses numpy.int64.
    call = parse("path 1 1581 745")
    assert call is not None
    xy = call[1][1]
    assert isinstance(xy, list) and all(type(v) is int for v in xy)
