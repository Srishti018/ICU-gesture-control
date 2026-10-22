import pytest

from node.bio import max30100
from node.bio.max30100 import MAX30100, SensorError, fifo_count, led_config_byte, parse_fifo


def test_parse_fifo_big_endian_pairs():
    data = bytes([0x12, 0x34, 0x56, 0x78, 0xFF, 0xFF, 0x00, 0x01])
    assert parse_fifo(data) == [(0x1234, 0x5678), (0xFFFF, 0x0001)]


def test_parse_fifo_empty_and_bad_length():
    assert parse_fifo(b"") == []
    with pytest.raises(ValueError):
        parse_fifo(b"\x00\x01\x02")


def test_fifo_count():
    assert fifo_count(5, 2, 0) == 3
    assert fifo_count(2, 14, 0) == 4        # wrap-around
    assert fifo_count(7, 7, 3) == 16        # full FIFO with overflow
    assert fifo_count(7, 7, 0) == 0         # empty


def test_led_config_byte():
    assert led_config_byte(8, 15) == 0x8F
    with pytest.raises(ValueError):
        led_config_byte(16, 0)


class FakeBus:
    """Minimal stand-in for smbus2.SMBus with a 16-deep FIFO."""

    def __init__(self, part_id=0x11, samples=()):
        self.regs = {max30100.PART_ID: part_id, max30100.MODE_CONFIG: 0}
        self.fifo = list(samples)
        self.writes = []
        self.block_sizes = []

    def read_byte_data(self, addr, reg):
        if reg == max30100.FIFO_WR_PTR:
            return len(self.fifo) & 0x0F
        if reg == max30100.FIFO_RD_PTR:
            return 0
        if reg == max30100.OVF_COUNTER:
            return 0
        return self.regs.get(reg, 0)

    def write_byte_data(self, addr, reg, value):
        self.writes.append((reg, value))
        self.regs[reg] = value & ~max30100.MODE_RESET if reg == max30100.MODE_CONFIG else value

    def read_i2c_block_data(self, addr, reg, k):
        assert reg == max30100.FIFO_DATA and k <= 32 and k % 4 == 0
        self.block_sizes.append(k)
        out = []
        for _ in range(k // 4):
            ir, red = self.fifo.pop(0)
            out += [ir >> 8, ir & 0xFF, red >> 8, red & 0xFF]
        return out

    def close(self):
        pass


def make_sensor(bus):
    s = MAX30100()
    s.bus = bus
    return s


def test_configure_writes_expected_registers():
    bus = FakeBus()
    make_sensor(bus).configure()
    assert bus.writes[0] == (max30100.MODE_CONFIG, 0x40)
    assert (max30100.SPO2_CONFIG, 0x47) in bus.writes
    assert (max30100.LED_CONFIG, 0x8F) in bus.writes
    assert bus.writes[-1] == (max30100.MODE_CONFIG, 0x03)


def test_read_samples_chunks_of_32_bytes():
    samples = [(1000 + i, 2000 + i) for i in range(15)]
    bus = FakeBus(samples=samples)
    got = make_sensor(bus).read_samples()
    assert got == samples
    assert bus.block_sizes == [32, 28]


def test_open_rejects_wrong_part_id(monkeypatch):
    import types
    fake_module = types.SimpleNamespace(SMBus=lambda n: FakeBus(part_id=0x15))
    monkeypatch.setitem(__import__("sys").modules, "smbus2", fake_module)
    with pytest.raises(SensorError, match="0x15"):
        MAX30100().open()
