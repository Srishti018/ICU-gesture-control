from node.payload import should_publish_alert


def alerts_for(levels):
    prev, out = "routine", []
    for i, lv in enumerate(levels):
        if should_publish_alert(prev, lv):
            out.append((i, lv))
        prev = lv
    return out


def test_alerts_only_on_rise():
    seq = ["routine", "urgent", "urgent", "critical", "critical", "routine", "critical"]
    assert alerts_for(seq) == [(1, "urgent"), (3, "critical"), (6, "critical")]


def test_first_window_critical_alerts():
    assert alerts_for(["critical", "critical"]) == [(0, "critical")]


def test_falling_or_flat_never_alerts():
    assert alerts_for(["routine", "routine"]) == []
    assert alerts_for(["urgent", "routine", "urgent"]) == [(0, "urgent"), (2, "urgent")]
    assert alerts_for(["critical", "urgent"]) == [(0, "critical")]
