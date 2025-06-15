# 3D Bending & IK G-code Utility

A comprehensive PyQt6-based GUI application for processing G-code files through three stages:
1. **Bending**: Applies spline-based bending transformations to G-code
2. **IK Translation**: Performs inverse kinematics calculations
3. **Klipper Conversion**: Converts to Klipper-compatible format

## Features

- **Intuitive GUI**: User-friendly interface with organized sections
- **File Management**: Easy file selection and automatic output naming
- **Spline Preview**: Real-time visualization of bending splines using matplotlib
- **Parameter Control**: Adjustable spline parameters and layer settings
- **Process Logging**: Detailed log output for monitoring and debugging
- **Sequential Processing**: Step-by-step workflow with dependency checking
- **Error Handling**: Comprehensive error checking and user feedback

## Installation

### Prerequisites
- Python 3.8 or higher
- Windows PowerShell (for Windows users)

### Install Dependencies

1. **Clone or download the project files**
2. **Install required packages**:
   ```bash
   pip install -r requirements.txt
   ```

   Or install manually:
   ```bash
   pip install PyQt6 matplotlib scipy numpy
   ```

## Usage

### Running the Application

```bash
python gcode_processor_gui.py
```

### Step-by-Step Process

1. **File Selection**
   - Click "Browse G-code File" to select your input `.gcode` file
   - The selected file path will be displayed

2. **Configure Spline Parameters**
   - **SPLINE_X**: Start and end X coordinates for the bending spline (default: 115.5, 205.5)
   - **SPLINE_Z**: Start and end Z coordinates for the bending spline (default: 0, 100)
   - **Layer Height**: Print layer height in mm (default: 0.28)
   - **Warning Angle**: Maximum printable angle in degrees (default: 100)

3. **Preview Spline**
   - Click "Preview Spline" to visualize the bending curve
   - Adjust parameters and preview again if needed

4. **Process G-code**
   - **Step 1**: Click "Run Bending" to apply spline transformations
   - **Step 2**: Click "Run IK Translation" to perform inverse kinematics
   - **Step 3**: Click "Run Klipper Conversion" to convert to Klipper format

### Output Files

The application automatically generates output files in the same directory as your input file:

- `BENT_<filename>.gcode` - After bending process
- `IK_<filename>.gcode` - After IK translation
- `KLIPPER_<filename>.gcode` - Final Klipper-compatible output

### Process Log

Monitor the "Process Log" section for:
- Status updates during processing
- Warning messages about potential issues
- Error notifications
- Success confirmations

## Technical Details

### Bending Process
- Applies cubic spline transformations based on user-defined control points
- Calculates B-axis rotations for each layer
- Adjusts extrusion amounts based on layer height changes
- Validates movements for printability

### IK Translation
- Performs inverse kinematics calculations using arm lengths:
  - La = 28.4 mm
  - Lb = 47.7 mm
- Transforms X, Y, Z coordinates based on A and B axis values
- Ensures all coordinates remain positive

### Klipper Conversion
- Converts B-axis movements to `MANUAL_STEPPER` commands
- Removes redundant A and B axis commands from G1 lines
- Optimizes by only sending stepper commands when B value changes

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Verify Python version compatibility (3.8+)

2. **File Processing Errors**
   - Check that input G-code file is valid and accessible
   - Ensure sufficient disk space for output files
   - Verify spline parameters are reasonable for your print geometry

3. **Spline Warnings**
   - "Movement below build platform": Adjust SPLINE_X values
   - "Spline angle too high": Modify spline curve or warning angle threshold
   - "Self intersection": Reduce bending curvature

### Parameter Guidelines

- **SPLINE_X**: Should span the width of your print area
- **SPLINE_Z**: Should match or exceed your print height
- **Layer Height**: Must match your slicer settings exactly
- **Warning Angle**: Set based on your printer's mechanical limits

## License

This project integrates and extends existing G-code processing scripts for 3D printing applications.

## Support

For issues or questions:
1. Check the process log for specific error messages
2. Verify input parameters are within reasonable ranges
3. Ensure all prerequisite files exist before running subsequent steps 