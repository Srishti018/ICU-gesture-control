import logging

from node.local_io import buzzer as bz
from node.local_io.oled import MAX_CHARS, MockOled, format_lines, make_oled


def test_oled_lines_critical_inverted():
    lines, inv = format_lines("bed1", True, {"hr": 74, "spo2": 98, "finger": True}, "replay:rest", 0.912, 0.0123,
                              "critical")
    assert lines == ["bed1  MQTT OK", "Sensor HR 74 SpO2 98", "Bio: REPLAY rest", "Gesture 0.91 Tr 0.012",
                     "LEVEL: CRITICAL"]
    assert inv == 4
    assert format_lines("bed1", True, None, "replay:exertion", 0, 0, None)[0][2] == "Bio: REPLAY exertion"


def test_oled_lines_states():
    lines, inv = format_lines("bed1", False, None, "live", None, None, "routine", fusion_mode="rule")
    assert lines[0] == "bed1  MQTT --  RULE" and lines[1] == "Sensor: n/a" and lines[2] == "Bio: LIVE"
    assert lines[3] == "Gesture --  Tr --" and inv is None
    assert format_lines("bed1", True, {"finger": False}, "replay:exertion", 0, 0, "urgent")[0][1] == "Sensor: no finger"
    assert format_lines("bed1", True, {"finger": False}, "replay:exertion", 0, 0, "urgent")[1] == 4
    assert format_lines("bed1", True, None, "replay:exertion", 0, 0, None)[0][4] == "LEVEL: STARTING"
    assert all(len(x) <= MAX_CHARS for x in format_lines("a-very-long-node-name", True, None,
                                                          "replay:exertion", 0.5, 0.5, "critical")[0])


def test_mock_oled_logs_only_changes(caplog):
    oled = MockOled()
    with caplog.at_level(logging.INFO, logger="node.oled"):
        oled.show(["a", "b"], None)
        oled.show(["a", "b"], None)
        oled.show(["a", "c"], 1)
    lines = [r.getMessage() for r in caplog.records]
    assert lines == ["OLED  a | b", "OLED  a | [c]"]


def test_make_oled_never_raises():
    assert make_oled(False, False) is None
    assert make_oled(True, False) is None          # no luma / no I2C on the laptop -> disabled, logged
    assert isinstance(make_oled(False, True), MockOled)


def test_buzzer_patterns():
    assert bz.pattern_schedule("urgent") == [(0.150, 0.150), (0.150, 0.0)]
    assert bz.pattern_schedule("critical") == [(0.400, 0.150), (0.400, 0.150), (0.400, 0.0)]
    assert bz.pattern_schedule("routine") == []


def test_player_plays_once_in_order():
    events = []
    player = bz._Player(lambda: events.append("on"), lambda: events.append("off"),
                        sleep=lambda s: events.append(round(s, 3)))
    player.play("urgent")
    player.play("routine")      # ignored
    player.play("critical")
    player.close()
    assert events == ["on", 0.15, "off", 0.15, "on", 0.15, "off",
                      "on", 0.4, "off", 0.15, "on", 0.4, "off", 0.15, "on", 0.4, "off"]


def test_mock_and_disabled_buzzer(caplog):
    assert bz.make_buzzer(False, False) is None
    assert bz.make_buzzer(True, False) is None      # no gpiozero / GPIO on the laptop -> disabled, logged
    with caplog.at_level(logging.INFO, logger="node.buzzer"):
        bz.make_buzzer(False, True).play("critical")
    assert "BUZZER critical: 3 x 400 ms beep" in caplog.text
