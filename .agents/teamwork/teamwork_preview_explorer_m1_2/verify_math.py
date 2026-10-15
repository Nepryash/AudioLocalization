import ctypes

def c_int32(val):
    return ctypes.c_int32(val).value

def test_arithmetic_shift():
    # Test cases: (hex_input, expected_signed_int, description)
    test_cases = [
        (0x7FFFFF00, 8388607, "Max positive 24-bit (+8388607)"),
        (0x80000000, -8388608, "Max negative 24-bit (-8388608)"),
        (0x00000000, 0, "Zero level"),
        (0xFFFFFF00, -1, "Negative 1 (-1)"),
        (0x00000100, 1, "Positive 1 (+1)"),
        (0x000000FF, 0, "Low-byte bus noise only (0x000000FF)"),
        (0x00000001, 0, "Low-byte bus noise LSB (0x00000001)"),
        (0xFFFFFF80, -1, "Negative with low-byte noise (0xFFFFFF80)"),
        (0x40000000, 4194304, "Half-scale positive (+4194304)"),
        (0xC0000000, -4194304, "Half-scale negative (-4194304)"),
    ]

    print("=== Verification of Arithmetic Right Shift (raw_32 >> 8) ===")
    all_passed = True
    for raw_u32, expected, desc in test_cases:
        # Cast to signed 32-bit integer in C
        s32 = c_int32(raw_u32)
        # Arithmetic shift right by 8
        shifted = s32 >> 8
        passed = (shifted == expected)
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {desc:45} | Raw: 0x{raw_u32:08X} ({s32:11}) -> Shifted: {shifted:9} (Hex: 0x{(shifted & 0xFFFFFFFF):08X}) | Exp: {expected:9}")
    
    print("\n=== Verification of Pitfalls ===")
    # Pitfall 1: Unsigned right shift
    for raw_u32 in [0x80000000, 0xFFFFFF00, 0xC0000000]:
        s32 = c_int32(raw_u32)
        u32_shift = raw_u32 >> 8
        correct = s32 >> 8
        print(f"[PITFALL 1 - Unsigned Shift] Raw: 0x{raw_u32:08X} (True: {correct}) -> Unsigned >> 8: {u32_shift} (Error: {u32_shift - correct:+d})")

    # Pitfall 2: Masking after shift with 0x00FFFFFF
    for raw_u32 in [0x80000000, 0xFFFFFF00, 0xC0000000]:
        s32 = c_int32(raw_u32)
        correct = s32 >> 8
        masked = (s32 >> 8) & 0x00FFFFFF
        print(f"[PITFALL 2 - Mask 0xFFFFFF] Raw: 0x{raw_u32:08X} (True: {correct}) -> Masked: {masked} (Error: {masked - correct:+d})")

    return all_passed

if __name__ == "__main__":
    success = test_arithmetic_shift()
    print(f"\nOverall Result: {'ALL TESTS PASSED' if success else 'FAILURES DETECTED'}")
