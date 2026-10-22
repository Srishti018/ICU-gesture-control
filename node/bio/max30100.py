"""MAX30100 pulse-oximeter driver over I2C (smbus2). Register map from the datasheet."""

import time

INT_STATUS = 0x00
FIFO_WR_PTR = 0x02
OVF_COUNTER = 0x03
FIFO_RD_PTR = 0x04
FIFO_DATA = 0x05
MODE_CONFIG = 0x06
SPO2_CONFIG = 0x07
LED_CONFIG = 0x09
REV_ID = 0xFE
PART_ID = 0xFF

EXPECTED_PART_ID = 0x11
FIFO_DEPTH = 16
BYTES_PER_SAMPLE = 4
MAX_BLOCK = 32  # bytes per I2C block read (8 samples)

MODE_RESET = 0x40
MODE_SHUTDOWN = 0x80
MODE_SPO2 = 0x03
SPO2_HIRES_100HZ_1600US = 0x47

# LED current code -> mA
LED_CURRENT_MA = {0: 0, 1: 4.4, 2: 7.6, 3: 11.0, 4: 14.2, 5: 17.4, 6: 20.8, 7: 24.0, 8: 27.1, 9: 30.6,
                  10: 33.8, 11: 37.0, 12: 40.2, 13: 43.6, 14: 46.8, 15: 50.0}


class SensorError(Exception):
    pass


def fifo_count(wr: int, rd: int, ovf: int) -> int:
    """Samples waiting in the 16-deep FIFO from the write/read pointers and overflow counter."""
    n = (wr - rd) & 0x0F
    if n == 0 and ovf > 0:
        return FIFO_DEPTH
    return n


def parse_fifo(data) -> list[tuple[int, int]]:
    """4 bytes per sample, big-endian: IR high, IR low, RED high, RED low."""
    data = bytes(data)
    if len(data) % BYTES_PER_SAMPLE:
        raise ValueError(f"FIFO data length {len(data)} is not a multiple of {BYTES_PER_SAMPLE}")
    return [((data[i] << 8) | data[i + 1], (data[i + 2] << 8) | data[i + 3])
            for i in range(0, len(data), BYTES_PER_SAMPLE)]


def led_config_byte(red_code: int, ir_code: int) -> int:
    for name, code in (("red_code", red_code), ("ir_code", ir_code)):
        if not 0 <= code <= 15:
            raise ValueError(f"{name} must be 0..15, got {code}")
    return (red_code << 4) | ir_code


class MAX30100:
    def __init__(self, bus: int = 1, address: int = 0x57, red_code: int = 8, ir_code: int = 15):
        self.bus_number = bus
        self.address = address
        self.red_code = red_code
        self.ir_code = ir_code
        self.bus = None
        self.dropped = 0

    def _read(self, reg: int) -> int:
        return self.bus.read_byte_data(self.address, reg)

    def _write(self, reg: int, value: int) -> None:
        self.bus.write_byte_data(self.address, reg, value)

    def open(self) -> "MAX30100":
        try:
            from smbus2 import SMBus
        except ImportError as e:
            raise SensorError("smbus2 is not installed (pip install smbus2)") from e
        try:
            self.bus = SMBus(self.bus_number)
        except (FileNotFoundError, PermissionError, OSError) as e:
            raise SensorError(f"cannot open I2C bus {self.bus_number}: {e}") from e
        try:
            part = self._read(PART_ID)
        except OSError as e:
            self.close()
            raise SensorError(f"MAX30100 not found at 0x{self.address:02x}: {e}") from e
        if part != EXPECTED_PART_ID:
            self.close()
            raise SensorError(f"MAX30100 not found or wrong part ID: 0x{part:02x}")
        return self

    def revision(self) -> int:
        return self._read(REV_ID)

    def configure(self) -> None:
        self._write(MODE_CONFIG, MODE_RESET)
        deadline = time.monotonic() + 0.1
        while self._read(MODE_CONFIG) & MODE_RESET:
            if time.monotonic() > deadline:
                raise SensorError("MAX30100 reset did not complete within 100 ms")
            time.sleep(0.005)
        self._write(SPO2_CONFIG, SPO2_HIRES_100HZ_1600US)
        self._write(LED_CONFIG, led_config_byte(self.red_code, self.ir_code))
        for reg in (FIFO_WR_PTR, OVF_COUNTER, FIFO_RD_PTR):
            self._write(reg, 0)
        self._read(INT_STATUS)  # read to clear
        self._write(MODE_CONFIG, MODE_SPO2)

    def read_samples(self) -> list[tuple[int, int]]:
        wr = self._read(FIFO_WR_PTR) & 0x0F
        rd = self._read(FIFO_RD_PTR) & 0x0F
        ovf = self._read(OVF_COUNTER)
        if ovf:
            self.dropped += ovf
        n = fifo_count(wr, rd, ovf)
        raw = bytearray()
        remaining = n * BYTES_PER_SAMPLE
        while remaining:
            k = min(MAX_BLOCK, remaining)
            # FIFO_DATA does not auto-increment: consecutive bytes are consecutive samples.
            raw += bytes(self.bus.read_i2c_block_data(self.address, FIFO_DATA, k))
            remaining -= k
        return parse_fifo(raw)

    def set_led(self, red_code: int, ir_code: int) -> None:
        self._write(LED_CONFIG, led_config_byte(red_code, ir_code))
        self.red_code, self.ir_code = red_code, ir_code

    def shutdown(self) -> None:
        if self.bus is not None:
            self._write(MODE_CONFIG, self._read(MODE_CONFIG) | MODE_SHUTDOWN)

    def close(self) -> None:
        if self.bus is not None:
            try:
                self.bus.close()
            finally:
                self.bus = None
