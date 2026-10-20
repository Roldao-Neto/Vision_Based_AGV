from command_file import take_commands
from mode_commands import IDLE, STRAIGHT, UMBMARK, parse


def test_commands_come_oldest_first_and_are_deleted(tmp_path):
    (tmp_path / "1791741000000000002.cmd").write_text("idle\n")
    (tmp_path / "1791741000000000001.cmd").write_text("straight 250 500 8000 1403\n")
    assert take_commands(tmp_path) == ["straight 250 500 8000 1403", "idle"]
    assert list(tmp_path.iterdir()) == []


def test_files_still_being_written_are_left_alone(tmp_path):
    (tmp_path / ".1791741000000000001.tmp").write_text("idle\n")
    assert take_commands(tmp_path) == []
    assert (tmp_path / ".1791741000000000001.tmp").exists()


def test_commands_left_from_before_start_are_discarded(tmp_path):
    # mission() drains cmd/ once at start and only logs what it finds; later reads run commands.
    (tmp_path / "1791741000000000001.cmd").write_text("umbmark 1 1000 250 30000\n")
    (tmp_path / "1791741000000000002.cmd").write_text("")
    assert take_commands(tmp_path) == ["umbmark 1 1000 250 30000"]
    assert list(tmp_path.iterdir()) == []
    (tmp_path / "1791741000000000003.cmd").write_text("idle\n")
    assert take_commands(tmp_path) == ["idle"]


def test_missing_dir_means_no_commands(tmp_path):
    assert take_commands(tmp_path / "cmd") == []


def test_parse():
    assert parse("idle") == (IDLE, 0, 0, 0, 0)
    assert parse("  idle ") == (IDLE, 0, 0, 0, 0)
    assert parse("idle 3") is None
    assert parse("count start") is None  # Day 1 modes are gone
    assert parse("step 200 0 1000 300") is None
    assert parse("speed 250 500 1500 450") is None  # retired on Day 2


def test_parse_straight():
    assert parse("straight 250 500 8000 1380") == (STRAIGHT, 250, 500, 8000, 1380)
    assert parse("straight -150 300 5000 500") == (STRAIGHT, -150, 300, 5000, 500)
    assert parse("straight 250 500 8000") is None
    assert parse("straight 0.25 500 8000 1380") is None
    # Out-of-cap values still parse: the MCU is the one that refuses them.
    assert parse("straight 900 500 90000 1380") == (STRAIGHT, 900, 500, 90000, 1380)


def test_parse_umbmark():
    assert parse("umbmark 1 1000 250 30000") == (UMBMARK, 1, 1000, 250, 30000)
    assert parse("umbmark -1 1000 250 30000") == (UMBMARK, -1, 1000, 250, 30000)
    assert parse("umbmark 1 1000 250") is None
    assert parse("umbmark ccw 1000 250 30000") is None
    assert parse("umbmark 2 1000 250 30000") == (UMBMARK, 2, 1000, 250, 30000)  # the MCU refuses it
