"""arcadesynth - programmatically synthesize retro arcade sound effects
"""

import array
import math
import random
import numpy as np
from scipy.signal import butter, filtfilt, medfilt

DEFAULT_FREQUENCY = 44100
DEFAULT_CHANNELS = 1
MAX_LEN = 3600000
SAMPLE_RATE = DEFAULT_FREQUENCY * DEFAULT_CHANNELS

# ---------------------------------------------------------------------------
# Internal functions
# ---------------------------------------------------------------------------


def _limit(d, limit = 1.0, llimit = None):
    """Force value to a limit"""
    return min(max(d, (-limit if llimit is None else llimit)), limit)


def _butterworth_filter(buf, cutoff, type='lowpass', order=2):
    """A butterworth filter to reduce unwanted frequencies, order 1 is lowest effect, 6 is more dramatic"""
    nyq = 0.5 * SAMPLE_RATE
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype=type)
    buf = array.array("d", filtfilt(b, a, buf))
    return buf


def _samplept(func, i, f, harmonics=0, p=[]):
    """Calculate amplitude of a sample for a buffer position

    Given a function to calculate amplitude of a wave (func) for a buffer position (i)
    and frequency (f) calculate and return the amplitude.
    If harmonics is not zero also add in the amplitude of the given order of harmonics.
    If frequency is not constant throughout the buffer, track the current phase during the
    building process and pass the current phase of the primary and any harmonics through 
    the list (p), otherwise phase can be calculated on the fly.
    """
    amp = 0.0
    scaling = math.pow(2, harmonics) / (math.pow(2, harmonics + 1) - 1)
    for h in range(harmonics + 1):
        freq = f * (h + 1)
        vol = (1.0 / (h + 1)) * scaling
        dp = 2 * math.pi * freq / SAMPLE_RATE
        if len(p) == 0:
            phase = dp * i
        else:
            phase = p[h] = p[h] + dp
        a = func(phase)
        amp += a * vol
    return amp if len(p) == 0 else (amp, p)


def _sawtooth(phase):
    """Calculate amplitude for a sawtooth wave at the given phase"""
    return (2.0 / math.pi) * ((phase / 2.0) % math.pi) - 1.0


def _triangle(phase):
    """Calculate amplitude for a triangle wave at the given phase"""
    return ((2.0 / math.pi) * (math.pi - abs(phase % (2.0 * math.pi) - math.pi)) - 1.0)


def _square(phase):
    """Calculate amplitude for a square wave at the given phase"""
    return 1.0 if math.sin(phase) > 0.0 else -1.0


def _sin(phase):
    """Calculate amplitude for a sine wave at the given phase"""
    return math.sin(phase)


# ---------------------------------------------------------------------------
# User functions that manipulate internal buffers to build sounds
# ---------------------------------------------------------------------------


def init(frequency=DEFAULT_FREQUENCY, channels=DEFAULT_CHANNELS):
    """Set up sample rate, do this first to avoid using defaults

    E.g. get these values from pygame with 'frequency, _, channels = pygame.mixer.get_init()'
    """
    global SAMPLE_RATE
    SAMPLE_RATE = frequency * channels
    return


def tobytes(buf):
    """Convert buffer with range -1.0 to 1.0 to short signed integers then output as a byte stream

    Use this to convert a sound held in internal format to a byte list for external processing, e.g. by
    pygame.
    """
    a = array.array("h")
    for i in range(len(buf)):
        a.append(int(_limit(buf[i]) * 32767))
    return a.tobytes()


def boost(buf, gain):
    """Apply gain to buffer"""
    nparray1 = np.array(buf)
    npnew = nparray1 * gain
    buf = array.array("d", npnew)
    return buf


def combine(buf1, buf2):
    """Combine 2 buffers giving average amplitude for each sample"""
    nparray1 = np.array(buf1)
    nparray2 = np.array(buf2)
    npsummed = nparray1 + nparray2 / 2
    buf = array.array("d", npsummed)
    return buf


def constrain(buf, lower, upper):
    """Clip a buffer to an upper and lower constraint"""
    nparray = np.array(buf)
    np.clip(nparray, lower, upper, nparray)
    buf = array.array("d", nparray)
    return buf


def vmove(buf, amount):
    """Shift samples in the Y axis"""
    nparray = np.array(buf)
    nparray += amount
    buf = array.array("d", nparray)
    return buf


def noisalise(buf, vol = 1.0, gain = 1.0):
    """Apply gain to buffer proportional to mean amplitude, useful for restoring a constant RMS after processing noise"""
    data = np.array(buf)
    av = (data[data > 0].mean() + -data[data < 0].mean()) / 2.0
    r = gain / (av / 2.0)
    for i in range(len(buf)):
        buf[i] = _limit(buf[i], limit=vol / gain) * r * vol
    return


def slice(buf, start, end):
    """Extract a section of a buffer with start and end times in ms"""
    s = int(SAMPLE_RATE * start / 1000.0)
    e = min(len(buf), int(SAMPLE_RATE * end / 1000.0))
    return buf[s:e]


def median_filter(buf):
    """Perform a median filter"""
    return array.array("d", medfilt(buf, kernel_size=5))


def lowpass_filter(buf, cutoff, order=6):
    """Apply a filter that progressively removes frequencies above the cutoff"""
    return _butterworth_filter(buf, cutoff, type='lowpass', order=order)


def highpass_filter(buf, cutoff, order=6):
    """Apply a filter that progressively removes frequencies below the cutoff"""
    return _butterworth_filter(buf, cutoff, type='highpass', order=order)


def make_sawtooth(ms, vol=0.2, freq=140.0):
    """Make a sawtooth wave"""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("d")
    for i in range(n):
        buf.append(_samplept(_sawtooth, i, freq) * vol)
    return buf


def make_triangle(ms, vol=0.2, freq=140.0):
    """Make a triangle wave"""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("d")
    for i in range(n):
        buf.append(_samplept(_triangle, i, freq) * vol)
    return buf


def make_square(ms, vol=0.2, freq=140.0):
    """Make a square wave"""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("d")
    for i in range(n):
        buf.append(_samplept(_square, i, freq) * vol)
    return buf


def make_sin(ms=600, vol=0.4, freq=50.0, harmonics=0):
    """Make a sine wave"""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("d")
    for i in range(n):
        a = _samplept(_sin, i, freq, harmonics)
        buf.append(a * vol)
    return buf


def make_white(ms=600, vol=0.4, smooth=False):
    """Fill a buffer with random amplitudes to produce white noise

    If smooth is False use values of 1.0 or -1.0 randomly to produce white noise similar to the SN76477 Complex Sound Generator chip,
    otherwise generate purely random amplitudes which gives a more natural noise.
    """
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("d")
    random.seed(0)
    rng = random.Random()
    for _ in range(n):
        r = rng.uniform(-1.0, 1.0) * vol
        buf.append(r if smooth else 1.0 if r > 0.0 else -1.0)
    return buf


def make_brown(ms=600, vol=0.4, freq=150.0):
    """Apply a lowpass filter to white noise to produce brown noise"""
    buf = make_white(ms, vol)
    buf = lowpass_filter(buf, freq, order=1)
    return buf


def make_sweep(ms=80, startf=1500.0, endf=400.0, shape=_triangle, vol=1.0, repeat=0, harmonics=0):
    """Create a buffer that starts at frequency startf and ends at endf

    If repeat is not zero the cycle goes from startf to endf and back to startf in repeat milliseconds and
    continues to cycle until ms milliseconds have been filled.
    """
    n = int(SAMPLE_RATE * ms / 1000.0)
    loop = n * 2 if repeat == 0 else int(SAMPLE_RATE * repeat / 1000.0)
    period = loop // 2
    buf = array.array("d")
    phase = [0.0 for _ in range(harmonics + 1)]
    for i in range(n):
        x = i % loop
        if x > period:
            x = loop - x
        else:
            pass
        f = (startf - ((startf - endf) * (x / period) ))
        a, phase = _samplept(shape, i, f, harmonics, phase)
        buf.append(a * vol)
    return buf


def tremolo(buf, freq, intensity, shape=_sin):
    """Modify a buffer in place so that amplitude increases and decreases according to shape and intensity"""
    for i in range(len(buf)):
        phase = i * math.pi * freq / SAMPLE_RATE
        buf[i] *= (1.0 - intensity) + abs(((shape(phase) + 1.0) / 2.0) * intensity)
    return


def envelope(buf, attack, decay, sustain, release, start=0, end=MAX_LEN):
    """Modify a buffer in place with an ADSR envelope"""
    attack_start = int(SAMPLE_RATE * start / 1000.0)
    attack_end = min(len(buf), int(SAMPLE_RATE * (start + attack) / 1000.0))
    decay_end = min(len(buf), int(SAMPLE_RATE * decay / 1000.0) + attack_end)
    release_end = min(len(buf), int(SAMPLE_RATE * end / 1000.0))
    sustain_end = min(len(buf), release_end - int(SAMPLE_RATE * release / 1000.0))
    if attack != 0.0:
        for i in range(attack_start, attack_end):
            buf[i] *= (i - attack_start) / (attack_end - attack_start)
    for i in range(attack_end, decay_end):
        buf[i] *= ((decay_end - i) / (decay_end - attack_end)) * (1.0 - sustain) + sustain
    for i in range(decay_end, sustain_end):
        buf[i] *= sustain
    for i in range(sustain_end, release_end):
        buf[i] *= ((release_end - i) / (release_end - sustain_end)) * sustain
    return


def echo(buf, ms, vol):
    """Modify buffer in place to add a short delay to the sound"""
    delay = int(SAMPLE_RATE * ms / 1000.0)
    for _ in range(delay):
        buf.append(0.0)
    for i in range(len(buf)):
        buf[i] *= 1 - vol
        if i >= delay:
            buf[i] += buf[i - delay] * vol
    return


# ---------------------------------------------------------------------------
# Space Invaders sound effects returning bytes for external processing
# ---------------------------------------------------------------------------


def si_extralife():
    """Space Invaders extra life notification"""
    ms = 1360
    buf1 = make_triangle(ms, 1.0, 490)
    buf2 = make_sawtooth(ms, 1.0, 490)
    buf = combine(buf1, buf2)
    tremolo(buf, 120.0, 0.9, shape=_triangle)
    buf = boost(buf, 5.0)
    envelope(buf, 20, 0, 1.0, 20, end=200)
    for i in range(8):
        s = i * 145 + 200
        e = s + 135
        mute = e + 10
        envelope(buf, 30, 0, 0.9, 30, start=s, end=e)
        envelope(buf, 0, 0, 0.0, 0, start=e, end=mute)
    echo(buf, 30, 0.4)
    return tobytes(buf)


def si_ufodie():
    """Return bytes representing Space Invaders UFO exploding sound"""
    low = 150.0
    high = 1320.0
    buf = make_sweep(2210, low, high, _triangle, 0.5, 170)
    envelope(buf, 10, 0, 1.0, 350)
    echo(buf, 20, 0.3)
    return tobytes(buf)


def si_ufo():
    """Return bytes representing Space Invaders UFO on screen sound"""
    low = 400.0
    high = 1550.0
    buf = make_sweep(170, low, high, _square, 0.4, 170)
    return tobytes(buf)


def si_aliendie():
    """Return bytes representing Space Invaders enemy exploding sound"""
    buf = array.array("d")
    params = {
        "amplitude" : (0.7, 0.7, 0.4, 0.3, 0.25),
        "length" : (80, 80, 80, 100, 120)
    }
    for i in range(len(params["amplitude"])):
        s = 1500.0 if i < len(params["amplitude"]) - 1 else 1900.0
        f = 200.0 if 1 < len(params["amplitude"]) - 1 else 1100.0
        tempbuf = make_sweep(params["length"][i], s, f, _triangle, params["amplitude"][i], 0)
        envelope(tempbuf, 5, 0, 1.0, 5)
        buf += tempbuf
    envelope(buf, 5, 0, 1.0, 300)
    echo(buf, 20, 0.3)
    return tobytes(buf)


def si_explosion():
    """Return bytes representing Space Invaders player exploding sound"""
    ms = 1600
    buf = make_white(ms, 1.0)
    buf = lowpass_filter(buf, 350.0, order=1)
    noisalise(buf, gain=0.35)
    buf = lowpass_filter(buf, 2600.0)
    buf = median_filter(buf)
    buf = lowpass_filter(buf, 2600.0)
    envelope(buf, 20, 0, 1.0, 20, start=0, end=100)
    envelope(buf, 20, 0, 1.0, 20, start=100, end=180)
    envelope(buf, 5, 0, 0.1, 5, start=180, end=200)
    envelope(buf, 20, 0, 1.0, 20, start=200, end=250)
    envelope(buf, 20, 0, 1.0, 20, start=250, end=300)
    envelope(buf, 20, 0, 0.6, 20, start=300, end=400)
    envelope(buf, 20, 0, 1.0, 20, start=400, end=450)
    envelope(buf, 20, 0, 1.0, 20, start=450, end=500)
    envelope(buf, 20, 20, 0.6, 500, start=500)
    echo(buf, 80, 0.5)
    return tobytes(buf)


def si_playerfire():
    """Return bytes representing Space Invaders player firing sound"""
    ms = 400
    freq = 2490.0
    buf = make_white(ms, 1.0)
    start = slice(buf, 0, 300)
    for _ in range(5):
        start = lowpass_filter(start, freq, order=6)
        start = highpass_filter(start, freq, order=6)
    mid = slice(buf, 300, 350)
    for _ in range(5):
        mid = lowpass_filter(mid, freq - 75, order=6)
        mid = highpass_filter(mid, freq - 75, order=6)
    end = slice(buf, 350, 400)
    for _ in range(5):
        end = lowpass_filter(end, freq - 150, order=6)
        end = highpass_filter(end, freq - 150, order=6)
    buf = start + mid + end
    noisalise(buf, gain=0.15)
    envelope(buf, 10, 0, 1.0, 100)
    echo(buf, 40, 0.4)
    return tobytes(buf)


def si_march(freq=53.650):
    """Return bytes representing Space Invaders low-frequency marching sound

    Expected frequencies in Hz, 53.650, 50.114, 46.178, 62.465
    """
    ms = 80
    buf = make_sin(ms, 1.0, freq)
    buf = constrain(buf, 0.5, 1.0)
    buf = vmove(buf, -0.6)
    buf = median_filter(buf)
    envelope(buf, 5, 0, 1.0, 5)
    echo(buf, 20, 0.3)
    return tobytes(buf)
