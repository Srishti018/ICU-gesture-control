from ml.rule import gesture_only_level, rule_level


def f(g, d):
    return {"gesture_conf": g, "tremor": 0.01, "hr_delta": d, "spo2": 98}


def test_rule_gesture_boundary():
    assert rule_level(f(0.79, 0)) == "routine"
    assert rule_level(f(0.80, 0)) == "urgent"


def test_rule_hr_delta_boundary():
    assert rule_level(f(0.80, 14)) == "urgent"
    assert rule_level(f(0.80, 15)) == "critical"
    assert rule_level(f(0.79, 30)) == "routine"


def test_rule_missing_hr_delta_is_not_critical():
    assert rule_level(f(0.9, None)) == "urgent"


def test_gesture_only_never_critical():
    assert gesture_only_level(f(0.79, 30)) == "routine"
    assert gesture_only_level(f(0.80, 30)) == "urgent"
    assert gesture_only_level(f(1.0, 100)) == "urgent"
