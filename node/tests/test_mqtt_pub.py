"""NodePublisher with a fake paho client: Will before connect, online retained on connect."""

import json
from types import SimpleNamespace

from node.mqtt_pub import NodePublisher
from node.settings import Settings


class FakeInfo:
    def wait_for_publish(self, timeout=None):
        return True


class FakeClient:
    def __init__(self, client_id):
        self.client_id = client_id
        self.calls = []
        self.published = []

    def username_pw_set(self, user, password):
        self.calls.append(("username_pw_set", user))

    def will_set(self, topic, payload, qos, retain):
        self.calls.append(("will_set", topic, payload, qos, retain))

    def reconnect_delay_set(self, min_delay, max_delay):
        self.calls.append(("reconnect_delay_set", min_delay, max_delay))

    def connect_async(self, host, port, keepalive):
        self.calls.append(("connect_async", host, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakeInfo()

    def subscribe(self, *a, **k):
        raise AssertionError("the node must never subscribe")


def make():
    s = Settings(broker_host="localhost", node_id="bed1", node_user="bed1", node_pass="x", keepalive=5)
    holder = {}

    def factory(cid):
        holder["c"] = FakeClient(cid)
        return holder["c"]
    return NodePublisher(s, client_factory=factory), holder


def test_will_set_before_connect_and_online_on_connect():
    pub, h = make()
    c = h["c"]
    assert c.client_id == "node-bed1"
    pub.start()
    names = [x[0] for x in c.calls]
    assert names.index("will_set") < names.index("connect_async")
    assert ("will_set", "icu/bed1/online", "offline", 1, True) in c.calls
    assert ("connect_async", "localhost", 1883, 5) in c.calls
    pub._on_connect(c, None, None, SimpleNamespace(is_failure=False), None)
    assert pub.connected
    assert c.published[-1] == ("icu/bed1/online", "online", 1, True)


def test_refused_connect_publishes_nothing():
    pub, h = make()
    pub._on_connect(h["c"], None, None, SimpleNamespace(is_failure=True), None)
    assert not pub.connected and h["c"].published == []


def test_topics_qos_retain():
    pub, h = make()
    payload = {"node": "bed1", "level": "urgent"}
    pub.publish_status(payload)
    pub.publish_alert("urgent", payload)
    pub.publish_heartbeat()
    (t1, p1, q1, r1), (t2, _, q2, r2), (t3, p3, q3, r3) = h["c"].published
    assert (t1, q1, r1) == ("icu/bed1/status/routine", 0, False) and json.loads(p1) == payload
    assert (t2, q2, r2) == ("icu/bed1/status/urgent", 1, True)
    assert (t3, q3, r3) == ("icu/bed1/heartbeat", 0, False) and set(json.loads(p3)) == {"node", "ts", "uptime_s"}


def test_clean_quit_publishes_offline_retained():
    pub, h = make()
    pub.clean_quit()
    assert h["c"].published[-1] == ("icu/bed1/online", "offline", 1, True)
    assert ("disconnect",) in h["c"].calls and ("loop_stop",) in h["c"].calls


def test_publish_error_does_not_raise():
    pub, h = make()

    def boom(*a, **k):
        raise RuntimeError("socket closed")
    h["c"].publish = boom
    assert pub.publish_status({"x": 1}) is None
