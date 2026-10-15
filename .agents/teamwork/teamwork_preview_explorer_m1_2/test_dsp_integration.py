import math
import ctypes

def c_int32(val):
    return ctypes.c_int32(val).value

def i2s_mic_convert_sample(raw_32):
    return c_int32(raw_32) >> 8

def audio_dsp_process_window(samples):
    N = len(samples)
    if N == 0:
        return 0, 0, 0
    sum_sq = 0.0
    peak_int = 0
    for s in samples:
        # Exact integer peak tracking with saturation at 8388607
        abs_s = 8388607 if s <= -8388608 else abs(s)
        if abs_s > peak_int:
            peak_int = abs_s
        
        # Power-of-2 division preserves exact IEEE 754 mantissa
        sf = s / 8388608.0
        sum_sq += sf * sf
        
    mean_sq = sum_sq / N
    rms_f = math.sqrt(mean_sq)
    decimated_sample = samples[-1]
    # Scale to full-scale 24-bit integer
    rms_level = int(round(rms_f * 8388607.0))
    if rms_level > 8388607:
        rms_level = 8388607
    return decimated_sample, rms_level, peak_int

def test_dsp_integration():
    print("=== Testing M1 Converted Samples into M2 DSP Pipeline ===")
    
    # 1. DC Full Scale Positive (+8388607)
    raw_dc_pos = [0x7FFFFF00] * 128
    conv_dc_pos = [i2s_mic_convert_sample(r) for r in raw_dc_pos]
    dec, rms, peak = audio_dsp_process_window(conv_dc_pos)
    print(f"DC Max Positive: Dec={dec}, RMS={rms}, Peak={peak}")
    assert dec == 8388607
    assert abs(rms - 8388607) <= 1
    assert peak == 8388607
    
    # 2. DC Full Scale Negative (-8388608)
    raw_dc_neg = [0x80000000] * 128
    conv_dc_neg = [i2s_mic_convert_sample(r) for r in raw_dc_neg]
    dec, rms, peak = audio_dsp_process_window(conv_dc_neg)
    print(f"DC Max Negative: Dec={dec}, RMS={rms}, Peak={peak}")
    assert dec == -8388608
    assert rms == 8388607
    assert peak == 8388607

    # 3. Pure Zero / Silence
    raw_zero = [0x00000000] * 128
    conv_zero = [i2s_mic_convert_sample(r) for r in raw_zero]
    dec, rms, peak = audio_dsp_process_window(conv_zero)
    print(f"Pure Silence: Dec={dec}, RMS={rms}, Peak={peak}")
    assert dec == 0 and rms == 0 and peak == 0

    # 4. Trailing Bus Noise Only (Silence with Floating Pulldown Delay)
    raw_noise = [0x000000FF] * 128
    conv_noise = [i2s_mic_convert_sample(r) for r in raw_noise]
    dec, rms, peak = audio_dsp_process_window(conv_noise)
    print(f"Trailing Bus Noise: Dec={dec}, RMS={rms}, Peak={peak}")
    assert dec == 0 and rms == 0 and peak == 0, "Trailing noise was not rejected!"

    # 5. Full Scale Sine Wave
    sine_samples = []
    for i in range(128):
        angle = 2.0 * math.pi * i / 128.0
        val = int(8388607 * math.sin(angle))
        raw = (val << 8) & 0xFFFFFFFF
        sine_samples.append(raw)
    
    conv_sine = [i2s_mic_convert_sample(r) for r in sine_samples]
    dec, rms, peak = audio_dsp_process_window(conv_sine)
    expected_rms = int(round(8388607 / math.sqrt(2)))
    print(f"Full-Scale Sine: RMS={rms} (Exp={expected_rms}), Peak={peak}")
    assert abs(rms - expected_rms) / expected_rms < 0.01
    assert peak > 8300000

    # 6. Impulse Clap (1 peak sample among zeroes)
    impulse_samples = [0] * 128
    impulse_samples[64] = 0x40000000 # 50% scale clap (+4194304)
    conv_impulse = [i2s_mic_convert_sample(r) for r in impulse_samples]
    dec, rms, peak = audio_dsp_process_window(conv_impulse)
    print(f"Impulse Clap: RMS={rms}, Peak={peak}")
    assert peak == 4194304, f"Peak expected 4194304, got {peak}"
    expected_impulse_rms = int(round(4194304 / math.sqrt(128)))
    assert abs(rms - expected_impulse_rms) <= 1

    print("ALL INTEGRATION TESTS PASSED!")

if __name__ == "__main__":
    test_dsp_integration()
