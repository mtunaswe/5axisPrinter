import re

def convert_b_axis_to_manual_stepper(input_path, output_path):
    """
    Convert B-axis values in G-code to Klipper-compatible MANUAL_STEPPER commands.
    Removes A values and redundant B-moves.
    """
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile:
        lines = infile.readlines()

    converted_lines = []
    last_b_value = None

    for line in lines:
        original_line = line.strip()

        # Only modify G1 movement lines
        if original_line.startswith("G1"):
            # Extract B-axis value if it exists
            b_match = re.search(r"\bB(-?\d+\.?\d*)", original_line)
            if b_match:
                current_b = float(b_match.group(1))
                if last_b_value is None or current_b != last_b_value:
                    converted_lines.append(f"MANUAL_STEPPER STEPPER=b_stepper MOVE={current_b}")
                    last_b_value = current_b
                # Remove B from the G1 line
                original_line = re.sub(r"\s*B-?\d+\.?\d*", "", original_line)

            # Remove A (e.g., A0)
            original_line = re.sub(r"\s*A-?\d+\.?\d*", "", original_line)

        converted_lines.append(original_line)

    # Write cleaned output to a file
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.write("\n".join(converted_lines))

    print(f"✅ Done! Converted file saved to: {output_path}")


# ----------------------
# Example Usage
# ----------------------
if __name__ == "__main__":
    input_file = "BENTsilindir6_IK.gcode"               # Your bent G-code input
    output_file = "BENTsilindir6_IKandconverted.gcode"    # Cleaned output for Klipper

    convert_b_axis_to_manual_stepper(input_file, output_file)
