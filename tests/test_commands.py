from command_file import take_commands
from mode_commands import IDLE, SPEED, parse


def test_commands_come_oldest_first_and_are_deleted(tmp_path):
    (tmp_path / "1791741000000000002.cmd").write_text("idle\n")
    (tmp_path / "1791741000000000001.cmd").write_text("speed 250 500 1500 450\n")
    assert take_commands(tmp_path) == ["speed 250 500 1500 450", "idle"]
    assert list(tmp_path.iterdir()) == []


def test_files_still_being_written_are_left_alone(tmp_path):
    (tmp_path / ".1791741000000000001.tmp").write_text("idle\n")
    assert take_commands(tmp_path) == []
    assert (tmp_path / ".1791741000000000001.tmp").exists()


def test_commands_left_from_before_start_are_discarded(tmp_path):
    # mission() drains cmd/ once at start and only logs what it finds; later reads run commands.
    (tmp_path / "1791741000000000001.cmd").write_text("speed 250 500 4500 937\n")
    (tmp_path / "1791741000000000002.cmd").write_text("")
    assert take_commands(tmp_path) == ["speed 250 500 4500 937"]
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


def test_parse_speed():
    assert parse("speed 250 500 1500 450") == (SPEED, 250, 500, 1500, 450)
    assert parse("speed -100 0 1500 250") == (SPEED, -100, 0, 1500, 250)
    assert parse("speed 250 500 1500") is None
    assert parse("speed 0.25 500 1500 450") is None
    assert parse("speed 250 x 1500 450") is None
    # Out-of-cap values still parse: the MCU is the one that refuses them.
    assert parse("speed 900 500 9000 450") == (SPEED, 900, 500, 9000, 450)
