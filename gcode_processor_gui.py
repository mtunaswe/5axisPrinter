import sys
import os
import re
import math
import subprocess
import numpy as np

# Set matplotlib backend before importing pyplot
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to avoid Qt conflicts
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from scipy.interpolate import CubicSpline
from collections import namedtuple
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QGridLayout, QWidget, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QFileDialog, QGroupBox, QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap, QShortcut, QKeySequence
from PyQt6.QtWidgets import QLabel as QImageLabel

# Try to import PyQt6 matplotlib backend, fallback to image display
try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    MATPLOTLIB_QT_AVAILABLE = True
except ImportError:
    MATPLOTLIB_QT_AVAILABLE = False

# Import our Klipper controller
try:
    from klipper_remote_control import KlipperRemoteController
    KLIPPER_AVAILABLE = True
except ImportError:
    KLIPPER_AVAILABLE = False

# Define namedtuples
Point2D = namedtuple('Point2D', 'x y')
GCodeLine = namedtuple('GCodeLine', 'x y z e f')

class SplineCanvas(QImageLabel if not MATPLOTLIB_QT_AVAILABLE else FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        if MATPLOTLIB_QT_AVAILABLE:
            self.fig = Figure(figsize=(width, height), dpi=dpi)
            super().__init__(self.fig)
            self.setParent(parent)
            self.axes = self.fig.add_subplot(111)
        else:
            super().__init__(parent)
            self.setMinimumSize(400, 300)
            self.setStyleSheet("border: 1px solid gray;")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setText("Spline preview will appear here")

    def plot_spline(self, spline_x, spline_z):
        if MATPLOTLIB_QT_AVAILABLE:
            self._plot_with_canvas(spline_x, spline_z)
        else:
            self._plot_with_image(spline_x, spline_z)
    
    def _plot_with_canvas(self, spline_x, spline_z):
        self.axes.clear()
        
        # Create spline
        spline = CubicSpline(spline_z, spline_x, bc_type=((1, 0), (1, 2.5)))
        
        # Plot data points and spline
        xs = np.arange(spline_z[0], spline_z[-1], 1)
        self.axes.plot(spline_x, spline_z, 'o', label='Control Points', markersize=8)
        self.axes.plot(spline(xs), xs, label="Spline Curve", linewidth=2)
        
        self.axes.set_xlim(0, max(spline_x) + 20)
        self.axes.set_ylim(0, max(spline_z) + 20)
        self.axes.set_xlabel('X Position')
        self.axes.set_ylabel('Z Position')
        self.axes.set_title('Bending Spline Preview')
        self.axes.legend(fontsize='small', loc='upper left')
        self.axes.grid(True, alpha=0.3)
        self.axes.set_aspect('equal', adjustable='box')
        
        self.draw()
    
    def _plot_with_image(self, spline_x, spline_z):
        # Create plot using matplotlib with Agg backend and display as image
        fig, ax = plt.subplots(figsize=(5, 4), dpi=100)
        
        # Create spline
        spline = CubicSpline(spline_z, spline_x, bc_type=((1, 0), (1, 2.5)))
        
        # Plot data points and spline
        xs = np.arange(spline_z[0], spline_z[-1], 1)
        ax.plot(spline_x, spline_z, 'o', label='Control Points', markersize=8)
        ax.plot(spline(xs), xs, label="Spline Curve", linewidth=2)
        
        ax.set_xlim(0, max(spline_x) + 20)
        ax.set_ylim(0, max(spline_z) + 20)
        ax.set_xlabel('X Position')
        ax.set_ylabel('Z Position')
        ax.set_title('Bending Spline Preview')
        ax.legend(fontsize='small', loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal', adjustable='box')
        
        # Save to temporary file and load as pixmap
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            fig.savefig(tmp.name, bbox_inches='tight', dpi=100)
            tmp_path = tmp.name
        
        plt.close(fig)
        
        # Load and display the image
        pixmap = QPixmap(tmp_path)
        self.setPixmap(pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass

class ProcessWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, process_type, input_file, output_file, params=None):
        super().__init__()
        self.process_type = process_type
        self.input_file = input_file
        self.output_file = output_file
        self.params = params

    def run(self):
        try:
            if self.process_type == "bending":
                self.run_bending()
            elif self.process_type == "ik":
                self.run_ik_translation()
            elif self.process_type == "klipper":
                self.run_klipper_conversion()
        except Exception as e:
            self.error_signal.emit(str(e))

    def run_bending(self):
        # Extract bending logic from bend_gcode_Baxis_exhaust3.py
        self.log_signal.emit("Starting G-code bending process...")
        
        spline_x = self.params['spline_x']
        spline_z = self.params['spline_z']
        layer_height = self.params['layer_height']
        warning_angle = self.params['warning_angle']
        
        # Create spline
        spline = CubicSpline(spline_z, spline_x, bc_type=((1, 0), (1, 2.5)))
        
        # Create spline lookup table
        discretization_length = self.params['discretization_length']
        spline_lookup_table = [0.0]
        height_steps = np.arange(discretization_length, spline_z[-1], discretization_length)
        for i in range(len(height_steps)):
            height = height_steps[i]
            spline_lookup_table.append(spline_lookup_table[i] + 
                np.sqrt((spline(height) - spline(height - discretization_length))**2 + discretization_length**2))
        
        def on_spline_length(z_height):
            for i in range(len(spline_lookup_table)):
                height = spline_lookup_table[i]
                if height >= z_height:
                    return i * discretization_length
            self.log_signal.emit(f"Warning! Spline not defined high enough for Z={z_height}")
            return z_height
        
        def get_normal_point(current_point, derivative, distance):
            angle = np.arctan(derivative) + math.pi / 2
            return Point2D(current_point.x + distance * np.cos(angle), 
                          current_point.y + distance * np.sin(angle))
        
        def parse_gcode(current_line):
            pattern = re.compile(r'(?i)^[gG][0-3](?:\s+x(?P<x>-?[0-9.]{1,15})|\s+y(?P<y>-?[0-9.]{1,15})|\s+z(?P<z>-?[0-9.]{1,15})|\s+e(?P<e>-?[0-9.]{1,15})|\s+f(?P<f>-?[0-9.]{1,15}))*')
            line_entries = pattern.match(current_line)
            if line_entries:
                return GCodeLine(line_entries.group('x'), line_entries.group('y'), 
                               line_entries.group('z'), line_entries.group('e'), line_entries.group('f'))
            return None
        
        def write_line(output_file, g, x, y, z, a, f=None, e=None):
            output_string = f"G{int(g)} X{round(x,5)} Y{round(y,5)} Z{round(z,3)} A0 B{round(a,3)}"
            if e is not None:
                output_string += f" E{round(float(e),5)}"
            if f is not None:
                output_string += f" F{int(float(f))}"
            output_file.write(output_string + "\n")
        
        # Process the G-code file
        last_position = Point2D(0, 0)
        current_z = 0.0
        last_z = 0.0
        relative_mode = False
        
        with open(self.input_file, "r") as gcode_file, open(self.output_file, "w+") as output_file:
            for current_line in gcode_file:
                if current_line[0] == ";":
                    output_file.write(current_line)
                    continue
                
                if current_line.find("G91 ") != -1:
                    relative_mode = True
                    output_file.write(current_line)
                    continue
                
                if current_line.find("G90 ") != -1:
                    relative_mode = False
                    output_file.write(current_line)
                    continue
                
                if relative_mode:
                    output_file.write(current_line)
                    continue
                
                current_line_commands = parse_gcode(current_line)
                if current_line_commands is not None:
                    if current_line_commands.z is not None:
                        current_z = float(current_line_commands.z)
                    
                    if current_line_commands.x is None or current_line_commands.y is None:
                        if current_line_commands.z is not None:
                            output_file.write(f"G91\nG1 Z{current_z-last_z}")
                            if current_line_commands.f is not None:
                                output_file.write(f" F{current_line_commands.f}")
                            output_file.write("\nG90\nM83\n")
                            last_z = current_z
                            continue
                        output_file.write(current_line)
                        continue
                    
                    current_position = Point2D(float(current_line_commands.x), float(current_line_commands.y))
                    midpoint_x = last_position.x + (current_position.x - last_position.x) / 2
                    
                    dist_to_spline = midpoint_x - spline_x[0]
                    corrected_z_height = on_spline_length(current_z)
                    
                    angle_spline_this_layer = np.arctan(spline(corrected_z_height, 1))
                    angle_last_layer = np.arctan(spline(corrected_z_height - layer_height, 1))
                    
                    height_difference = np.sin(angle_spline_this_layer - angle_last_layer) * dist_to_spline * -1
                    
                    transformed_gcode = get_normal_point(
                        Point2D(corrected_z_height, spline(corrected_z_height)), 
                        spline(corrected_z_height, 1), 
                        current_position.x - spline_x[0]
                    )
                    
                    if float(transformed_gcode.x) <= 0.0:
                        self.log_signal.emit("Warning! Movement below build platform. Check your spline!")
                    
                    if transformed_gcode.x < 0 or np.abs(transformed_gcode.x - current_z) > 50:
                        self.log_signal.emit(f"Warning! Possibly unplausible move detected on height {current_z} mm!")
                        output_file.write(current_line)
                        continue
                    
                    if (layer_height + height_difference) < 0:
                        self.log_signal.emit(f"ERROR! Self intersection on height {current_z} mm! Check your spline!")
                    
                    if angle_spline_this_layer > (warning_angle * np.pi / 180.):
                        self.log_signal.emit(f"Warning! Spline angle is {angle_spline_this_layer * 180. / np.pi:.2f}° at height {current_z} mm!")
                    
                    if current_line_commands.e is not None:
                        extrusion_amount = float(current_line_commands.e) * ((layer_height + height_difference) / layer_height)
                    else:
                        extrusion_amount = None
                    
                    b_axis = angle_spline_this_layer * 57.2958  # radians to degrees
                    write_line(output_file, 1, transformed_gcode.y, current_position.y, 
                             transformed_gcode.x, b_axis, None, extrusion_amount)
                    
                    last_position = current_position
                    last_z = current_z
                else:
                    output_file.write(current_line)
        
        self.log_signal.emit("G-code bending finished!")
        self.finished_signal.emit("bending")

    def run_ik_translation(self):
        self.log_signal.emit("Starting IK translation process...")
        
        La = 28.4
        Lb = 47.7
        
        def func_x(x_val, y_val, z_val, a_val, b_val):
            return max(x_val + math.sin(math.radians(a_val)) * La + 
                      math.cos(math.radians(a_val)) * math.sin(math.radians(b_val)) * Lb, 0)

        def func_y(x_val, y_val, z_val, a_val, b_val):
            return max(y_val - La + math.cos(math.radians(a_val)) * La - 
                      math.sin(math.radians(a_val)) * math.sin(math.radians(b_val)) * Lb, 0)

        def func_z(x_val, y_val, z_val, a_val, b_val):
            return max(z_val + math.cos(math.radians(b_val)) * Lb - Lb, 0)

        def recalculate(line):
            if not line.startswith("G") and not line.startswith("M"):
                return line

            parts = line.split()
            x_val = y_val = z_val = a_val = b_val = 0

            x_indices = []
            y_indices = []
            z_indices = []

            for i in range(1, len(parts)):
                if parts[i].startswith("X"):
                    x_val = float(parts[i][1:])
                    x_indices.append(i)
                elif parts[i].startswith("Y"):
                    y_val = float(parts[i][1:])
                    y_indices.append(i)
                elif parts[i].startswith("Z"):
                    z_val = float(parts[i][1:])
                    z_indices.append(i)
                elif parts[i].startswith("A"):
                    a_val = float(parts[i][1:])
                elif parts[i].startswith("B"):
                    b_val = float(parts[i][1:])

            for i in x_indices:
                parts[i] = "X" + str(func_x(x_val, y_val, z_val, a_val, b_val))

            for i in y_indices:
                parts[i] = "Y" + str(func_y(x_val, y_val, z_val, a_val, b_val))
            
            for i in z_indices:
                parts[i] = "Z" + str(func_z(x_val, y_val, z_val, a_val, b_val))

            return " ".join(parts)

        with open(self.input_file) as f:
            lines = f.readlines()

        with open(self.output_file, "w") as f:
            for line in lines:
                new_line = recalculate(line.strip())
                f.write(new_line + "\n")

        self.log_signal.emit("IK translation finished!")
        self.finished_signal.emit("ik")

    def run_klipper_conversion(self):
        self.log_signal.emit("Starting Klipper conversion process...")
        
        with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as infile:
            lines = infile.readlines()

        converted_lines = []
        last_b_value = None

        for line in lines:
            original_line = line.strip()

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

        with open(self.output_file, 'w', encoding='utf-8') as outfile:
            outfile.write("\n".join(converted_lines))

        self.log_signal.emit("Klipper conversion finished!")
        self.finished_signal.emit("klipper")

class GCodeProcessorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.input_file = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("3D Bending & IK G-code Utility")
        
        # Set minimum window size (will be maximized in main())
        self.setMinimumSize(1000, 800)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # File Selection Group
        file_group = QGroupBox("File Selection")
        file_layout = QHBoxLayout()
        
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 5px; }")
        self.browse_button = QPushButton("Browse G-code File")
        self.browse_button.clicked.connect(self.browse_file)
        
        file_layout.addWidget(self.file_label, 1)
        file_layout.addWidget(self.browse_button)
        file_group.setLayout(file_layout)

        # Printer Connection Group
        printer_group = QGroupBox("Printer Connection")
        printer_layout = QGridLayout()
        
        printer_layout.addWidget(QLabel("Printer IP Address:"), 0, 0)
        self.printer_ip = QLineEdit("172.20.10.4")
        self.printer_ip.setToolTip("IP address of your Raspberry Pi running Klipper")
        printer_layout.addWidget(self.printer_ip, 0, 1)
        
        self.test_connection_button = QPushButton("🔗 Test Connection")
        self.test_connection_button.clicked.connect(self.test_printer_connection)
        printer_layout.addWidget(self.test_connection_button, 0, 2)
        
        self.connection_status = QLabel("⚪ Not Connected")
        self.connection_status.setStyleSheet("QLabel { color: gray; }")
        printer_layout.addWidget(self.connection_status, 1, 0, 1, 3)
        
        printer_group.setLayout(printer_layout)
        
        # Printer Setup Commands Group
        setup_group = QGroupBox("Printer Setup Commands")
        setup_layout = QGridLayout()
        
        setup_layout.addWidget(QLabel("Quick Setup Sequences:"), 0, 0, 1, 2)
        
        self.mass_production_button = QPushButton("🏭 Mass Production Setup")
        self.mass_production_button.clicked.connect(self.setup_mass_production)
        self.mass_production_button.setEnabled(False)
        self.mass_production_button.setToolTip("Z+15mm → A+90° → B-45°")
        setup_layout.addWidget(self.mass_production_button, 1, 0)
        
        self.five_axis_button = QPushButton("🔧 5-Axis Printing Setup")
        self.five_axis_button.clicked.connect(self.setup_five_axis)
        self.five_axis_button.setEnabled(False)
        self.five_axis_button.setToolTip("Z+25mm → B-90°")
        setup_layout.addWidget(self.five_axis_button, 1, 1)
        
        self.home_all_button = QPushButton("🏠 Home All Axes")
        self.home_all_button.clicked.connect(self.home_all_axes)
        self.home_all_button.setEnabled(False)
        self.home_all_button.setToolTip("G28 - Home all axes")
        setup_layout.addWidget(self.home_all_button, 2, 0)
        
        self.emergency_stop_button = QPushButton("🛑 Emergency Stop")
        self.emergency_stop_button.clicked.connect(self.emergency_stop)
        self.emergency_stop_button.setEnabled(False)
        self.emergency_stop_button.setToolTip("M112 - Emergency stop")
        self.emergency_stop_button.setStyleSheet("QPushButton { background-color: #ff6b6b; color: white; font-weight: bold; }")
        setup_layout.addWidget(self.emergency_stop_button, 2, 1)
        
        setup_group.setLayout(setup_layout)

        # Spline Section (Parameters + Preview in 2 columns)
        spline_main_group = QGroupBox("Spline Configuration")
        spline_main_layout = QHBoxLayout()
        
        # Parameters Group (Left Column)
        params_group = QGroupBox("Spline Parameters")
        params_layout = QGridLayout()
        
        # Spline X parameters
        params_layout.addWidget(QLabel("SPLINE_X [start, end]:"), 0, 0)
        self.spline_x_start = QLineEdit("115.5")
        self.spline_x_end = QLineEdit("205.5")
        params_layout.addWidget(self.spline_x_start, 0, 1)
        params_layout.addWidget(self.spline_x_end, 0, 2)
        
        # Spline Z parameters
        params_layout.addWidget(QLabel("SPLINE_Z [start, end]:"), 1, 0)
        self.spline_z_start = QLineEdit("0")
        self.spline_z_end = QLineEdit("100")
        params_layout.addWidget(self.spline_z_start, 1, 1)
        params_layout.addWidget(self.spline_z_end, 1, 2)
        
        # Other parameters
        params_layout.addWidget(QLabel("Layer Height:"), 2, 0)
        self.layer_height = QLineEdit("0.28")
        params_layout.addWidget(self.layer_height, 2, 1)
        
        params_layout.addWidget(QLabel("Warning Angle (°):"), 3, 0)
        self.warning_angle = QLineEdit("100")
        params_layout.addWidget(self.warning_angle, 3, 1)
        
        params_layout.addWidget(QLabel("Discretization Length:"), 4, 0)
        self.discretization_length = QLineEdit("0.01")
        self.discretization_length.setToolTip("Step size for spline length calculations (smaller = more precise but slower)")
        params_layout.addWidget(self.discretization_length, 4, 1)
        
        # Preview button
        self.preview_button = QPushButton("Preview Spline")
        self.preview_button.clicked.connect(self.preview_spline)
        params_layout.addWidget(self.preview_button, 5, 0, 1, 3)
        
        # Add tooltips to other parameters
        self.spline_x_start.setToolTip("Starting X coordinate for the bending spline")
        self.spline_x_end.setToolTip("Ending X coordinate for the bending spline")
        self.spline_z_start.setToolTip("Starting Z coordinate (usually 0)")
        self.spline_z_end.setToolTip("Ending Z coordinate (should match your print height)")
        self.layer_height.setToolTip("Layer height from your slicer settings (must match exactly)")
        self.warning_angle.setToolTip("Maximum bending angle before warnings (degrees)")
        
        params_group.setLayout(params_layout)

        # Spline Preview Group (Right Column)
        preview_group = QGroupBox("Spline Preview")
        preview_layout = QVBoxLayout()
        
        self.spline_canvas = SplineCanvas()
        preview_layout.addWidget(self.spline_canvas)
        preview_group.setLayout(preview_layout)
        
        # Add both groups to horizontal layout
        spline_main_layout.addWidget(params_group)
        spline_main_layout.addWidget(preview_group)
        spline_main_group.setLayout(spline_main_layout)

        # Process Buttons Group
        process_group = QGroupBox("Processing Steps")
        process_layout = QHBoxLayout()
        
        self.bend_button = QPushButton("1. Run Bending")
        self.bend_button.clicked.connect(self.run_bending)
        self.bend_button.setEnabled(False)
        
        self.ik_button = QPushButton("2. Run IK Translation")
        self.ik_button.clicked.connect(self.run_ik_translation)
        self.ik_button.setEnabled(False)
        
        self.klipper_button = QPushButton("3. Run Klipper Conversion")
        self.klipper_button.clicked.connect(self.run_klipper_conversion)
        #self.klipper_button.setEnabled(False)
        
        process_layout.addWidget(self.bend_button)
        process_layout.addWidget(self.ik_button)
        process_layout.addWidget(self.klipper_button)
        process_group.setLayout(process_layout)

        # Output Files Group
        output_group = QGroupBox("Output Files")
        output_layout = QVBoxLayout()
        
        # File paths display
        files_layout = QGridLayout()
        files_layout.addWidget(QLabel("Bent G-code:"), 0, 0)
        self.bent_file_label = QLabel("Not generated yet")
        self.bent_file_label.setStyleSheet("QLabel { background-color: #f8f8f8; padding: 3px; border: 1px solid #ddd; color: #333; }")
        files_layout.addWidget(self.bent_file_label, 0, 1)
        
        files_layout.addWidget(QLabel("IK G-code:"), 1, 0)
        self.ik_file_label = QLabel("Not generated yet")
        self.ik_file_label.setStyleSheet("QLabel { background-color: #f8f8f8; padding: 3px; border: 1px solid #ddd; color: #333; }")
        files_layout.addWidget(self.ik_file_label, 1, 1)
        
        files_layout.addWidget(QLabel("Klipper G-code:"), 2, 0)
        self.klipper_file_label = QLabel("Not generated yet")
        self.klipper_file_label.setStyleSheet("QLabel { background-color: #f8f8f8; padding: 3px; border: 1px solid #ddd; color: #333; }")
        files_layout.addWidget(self.klipper_file_label, 2, 1)
        
        output_layout.addLayout(files_layout)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        self.open_folder_button = QPushButton("📁 Open Output Folder")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.open_folder_button.setEnabled(False)
        
        self.copy_path_button = QPushButton("📋 Copy Final Path")
        self.copy_path_button.clicked.connect(self.copy_final_path)
        self.copy_path_button.setEnabled(False)
        
        self.send_to_printer_button = QPushButton("🚀 Send to Printer")
        self.send_to_printer_button.clicked.connect(self.send_to_printer)
        self.send_to_printer_button.setEnabled(False)
        self.send_to_printer_button.setToolTip("Upload and start printing the final Klipper G-code")
        
        self.upload_only_button = QPushButton("📤 Upload Only")
        self.upload_only_button.clicked.connect(self.upload_only)
        self.upload_only_button.setEnabled(False)
        self.upload_only_button.setToolTip("Upload file to printer without starting print")
        
        buttons_layout.addWidget(self.open_folder_button)
        buttons_layout.addWidget(self.copy_path_button)
        buttons_layout.addWidget(self.upload_only_button)
        buttons_layout.addWidget(self.send_to_printer_button)
        output_layout.addLayout(buttons_layout)
        
        output_group.setLayout(output_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        # Log Output Group
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        
        self.log_output = QTextEdit()
        self.log_output.setFont(QFont("Consolas", 9))
        self.log_output.setMaximumHeight(200)
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)

        # Add all groups to main layout
        main_layout.addWidget(file_group)
        main_layout.addWidget(printer_group)
        main_layout.addWidget(setup_group)
        main_layout.addWidget(spline_main_group)
        main_layout.addWidget(process_group)
        main_layout.addWidget(output_group)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(log_group)

        # Initial spline preview
        self.preview_spline()
        
        # Initialize printer controller
        self.printer_controller = None
        
        # Add keyboard shortcuts for full screen control
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self.exit_fullscreen)
        
        # Store fullscreen state
        self.is_fullscreen = False

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select G-code File", "", "G-code Files (*.gcode);;All Files (*)")
        
        if file_path:
            self.input_file = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.bend_button.setEnabled(True)
            self.log_output.append(f"Selected file: {file_path}")

    def preview_spline(self):
        try:
            spline_x = [float(self.spline_x_start.text()), float(self.spline_x_end.text())]
            spline_z = [float(self.spline_z_start.text()), float(self.spline_z_end.text())]
            self.spline_canvas.plot_spline(spline_x, spline_z)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numeric values for spline parameters.")

    def get_output_filename(self, prefix, input_file):
        directory = os.path.dirname(input_file)
        filename = os.path.basename(input_file)
        name, ext = os.path.splitext(filename)
        return os.path.join(directory, f"{prefix}_{name}{ext}")

    def run_bending(self):
        if not self.input_file:
            QMessageBox.warning(self, "No File", "Please select a G-code file first.")
            return

        try:
            params = {
                'spline_x': [float(self.spline_x_start.text()), float(self.spline_x_end.text())],
                'spline_z': [float(self.spline_z_start.text()), float(self.spline_z_end.text())],
                'layer_height': float(self.layer_height.text()),
                'warning_angle': float(self.warning_angle.text()),
                'discretization_length': float(self.discretization_length.text())
            }
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numeric values for all parameters.")
            return

        output_file = self.get_output_filename("BENT", self.input_file)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        self.worker = ProcessWorker("bending", self.input_file, output_file, params)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.finished_signal.connect(self.on_process_finished)
        self.worker.error_signal.connect(self.on_process_error)
        self.worker.start()

    def run_ik_translation(self):
        bent_file = self.get_output_filename("BENT", self.input_file)
        if not os.path.exists(bent_file):
            QMessageBox.warning(self, "File Not Found", "Please run bending first.")
            return

        output_file = self.get_output_filename("IK", self.input_file)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.worker = ProcessWorker("ik", bent_file, output_file)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.finished_signal.connect(self.on_process_finished)
        self.worker.error_signal.connect(self.on_process_error)
        self.worker.start()

    def run_klipper_conversion(self):
        ik_file = self.get_output_filename("IK", self.input_file)
        if not os.path.exists(ik_file):
            QMessageBox.warning(self, "File Not Found", "Please run IK translation first.")
            return

        output_file = self.get_output_filename("KLIPPER", self.input_file)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.worker = ProcessWorker("klipper", ik_file, output_file)
        self.worker.log_signal.connect(self.log_output.append)
        self.worker.finished_signal.connect(self.on_process_finished)
        self.worker.error_signal.connect(self.on_process_error)
        self.worker.start()

    def on_process_finished(self, process_type):
        self.progress_bar.setVisible(False)
        
        if process_type == "bending":
            bent_file = self.get_output_filename("BENT", self.input_file)
            self.bent_file_label.setText(os.path.basename(bent_file))
            self.bent_file_label.setToolTip(bent_file)
            self.ik_button.setEnabled(True)
            self.open_folder_button.setEnabled(True)
            QMessageBox.information(self, "Success", f"Bending process completed successfully!\nOutput: {os.path.basename(bent_file)}")
        elif process_type == "ik":
            ik_file = self.get_output_filename("IK", self.input_file)
            self.ik_file_label.setText(os.path.basename(ik_file))
            self.ik_file_label.setToolTip(ik_file)
            self.klipper_button.setEnabled(True)
            QMessageBox.information(self, "Success", f"IK translation completed successfully!\nOutput: {os.path.basename(ik_file)}")
        elif process_type == "klipper":
            klipper_file = self.get_output_filename("KLIPPER", self.input_file)
            self.klipper_file_label.setText(os.path.basename(klipper_file))
            self.klipper_file_label.setToolTip(klipper_file)
            self.copy_path_button.setEnabled(True)
            
            # Enable printer buttons if connected
            if self.printer_controller:
                self.upload_only_button.setEnabled(True)
                self.send_to_printer_button.setEnabled(True)
            
            QMessageBox.information(self, "Success", f"Klipper conversion completed successfully!\nOutput: {os.path.basename(klipper_file)}")

    def on_process_error(self, error_message):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Process Error", f"An error occurred: {error_message}")
        self.log_output.append(f"ERROR: {error_message}")

    def open_output_folder(self):
        if self.input_file:
            folder_path = os.path.dirname(self.input_file)
            try:
                subprocess.Popen(f'explorer "{folder_path}"', shell=True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open folder: {e}")

    def copy_final_path(self):
        klipper_file = self.get_output_filename("KLIPPER", self.input_file)
        if os.path.exists(klipper_file):
            try:
                # Copy to clipboard using Qt
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(klipper_file)
                QMessageBox.information(self, "Copied", f"Final output path copied to clipboard:\n{os.path.basename(klipper_file)}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not copy to clipboard: {e}")

    def send_to_printer(self):
        if not KLIPPER_AVAILABLE:
            QMessageBox.warning(self, "Feature Unavailable", "Klipper remote control is not available. Please check installation.")
            return
            
        klipper_file = self.get_output_filename("KLIPPER", self.input_file)
        if not os.path.exists(klipper_file):
            QMessageBox.warning(self, "File Not Found", "Please complete Klipper conversion first.")
            return
            
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        # Confirm before starting print
        reply = QMessageBox.question(self, "Confirm Print", 
                                   f"Upload and start printing:\n{os.path.basename(klipper_file)}?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.log_output.append("Uploading file and starting print...")
            
            try:
                result = self.printer_controller.upload_and_print(klipper_file)
                self.progress_bar.setVisible(False)
                
                if result["success"]:
                    QMessageBox.information(self, "Print Started", 
                                          f"Successfully uploaded and started printing:\n{os.path.basename(klipper_file)}")
                    self.log_output.append("✅ Print started successfully!")
                else:
                    QMessageBox.critical(self, "Print Failed", f"Failed to start print:\n{result['error']}")
                    self.log_output.append(f"❌ Print failed: {result['error']}")
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
                self.log_output.append(f"❌ Error: {str(e)}")

    def upload_only(self):
        if not KLIPPER_AVAILABLE:
            QMessageBox.warning(self, "Feature Unavailable", "Klipper remote control is not available. Please check installation.")
            return
            
        klipper_file = self.get_output_filename("KLIPPER", self.input_file)
        if not os.path.exists(klipper_file):
            QMessageBox.warning(self, "File Not Found", "Please complete Klipper conversion first.")
            return
            
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.log_output.append("Uploading file...")
        
        try:
            result = self.printer_controller.upload_file(klipper_file)
            self.progress_bar.setVisible(False)
            
            if result["success"]:
                QMessageBox.information(self, "Upload Complete", 
                                      f"Successfully uploaded:\n{os.path.basename(klipper_file)}")
                self.log_output.append("✅ File uploaded successfully!")
            else:
                QMessageBox.critical(self, "Upload Failed", f"Failed to upload file:\n{result['error']}")
                self.log_output.append(f"❌ Upload failed: {result['error']}")
        except Exception as e:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.log_output.append(f"❌ Error: {str(e)}")

    def test_printer_connection(self):
        if not KLIPPER_AVAILABLE:
            QMessageBox.warning(self, "Feature Unavailable", 
                              "Klipper remote control is not available.\nPlease install the 'requests' library.")
            return
            
        ip_address = self.printer_ip.text().strip()
        if not ip_address:
            QMessageBox.warning(self, "Invalid IP", "Please enter a valid IP address.")
            return
            
        self.log_output.append(f"Testing connection to {ip_address}...")
        self.test_connection_button.setEnabled(False)
        self.connection_status.setText("🟡 Testing...")
        self.connection_status.setStyleSheet("QLabel { color: orange; }")
        
        try:
            self.printer_controller = KlipperRemoteController(ip_address)
            
            if self.printer_controller.test_connection():
                self.connection_status.setText("🟢 Connected")
                self.connection_status.setStyleSheet("QLabel { color: green; }")
                self.log_output.append("✅ Successfully connected to printer!")
                
                # Enable all printer control buttons
                self.mass_production_button.setEnabled(True)
                self.five_axis_button.setEnabled(True)
                self.home_all_button.setEnabled(True)
                self.emergency_stop_button.setEnabled(True)
                
                # Get and display printer status
                status_result = self.printer_controller.get_printer_status()
                if status_result["success"]:
                    self.log_output.append("📊 Printer status retrieved successfully")
                
                QMessageBox.information(self, "Connection Successful", 
                                      f"Successfully connected to printer at {ip_address}")
            else:
                self.connection_status.setText("🔴 Connection Failed")
                self.connection_status.setStyleSheet("QLabel { color: red; }")
                self.log_output.append("❌ Failed to connect to printer")
                self.printer_controller = None
                
                # Disable printer control buttons
                self.mass_production_button.setEnabled(False)
                self.five_axis_button.setEnabled(False)
                self.home_all_button.setEnabled(False)
                self.emergency_stop_button.setEnabled(False)
                
                QMessageBox.warning(self, "Connection Failed", 
                                  f"Could not connect to printer at {ip_address}\n"
                                  "Please check:\n"
                                  "• IP address is correct\n"
                                  "• Printer is powered on\n"
                                  "• Moonraker service is running\n"
                                  "• Network connection is working")
        except Exception as e:
            self.connection_status.setText("🔴 Error")
            self.connection_status.setStyleSheet("QLabel { color: red; }")
            self.log_output.append(f"❌ Connection error: {str(e)}")
            self.printer_controller = None
            
            # Disable printer control buttons
            self.mass_production_button.setEnabled(False)
            self.five_axis_button.setEnabled(False)
            self.home_all_button.setEnabled(False)
            self.emergency_stop_button.setEnabled(False)
            
            QMessageBox.critical(self, "Connection Error", f"An error occurred: {str(e)}")
        finally:
            self.test_connection_button.setEnabled(True)

    def toggle_fullscreen(self):
        """Toggle between fullscreen and maximized window"""
        if self.is_fullscreen:
            self.showMaximized()
            self.is_fullscreen = False
            self.log_output.append("📺 Switched to maximized window mode (F11 to toggle)")
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.log_output.append("📺 Switched to full screen mode (ESC or F11 to exit)")
    
    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        if self.is_fullscreen:
            self.showMaximized()
            self.is_fullscreen = False
            self.log_output.append("📺 Exited full screen mode")

    def setup_mass_production(self):
        """Setup printer for mass production: Z+15, A+90, B-45"""
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        # Confirm before executing
        reply = QMessageBox.question(self, "Confirm Mass Production Setup", 
                                   "Execute mass production setup sequence:\n"
                                   "• Move Z axis +15mm\n"
                                   "• Rotate A axis +90°\n"
                                   "• Rotate B axis -45°\n\n"
                                   "Continue?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.log_output.append("🏭 Executing mass production setup sequence...")
            
            try:
                # Execute sequence step by step
                commands = [
                    "G91",  # Relative positioning
                    "G1 Z15 F1000",  # Move Z up 15mm
                    "G90",  # Absolute positioning
                    "MANUAL_STEPPER STEPPER=a_stepper MOVE=90",  # A axis to 90°
                    "MANUAL_STEPPER STEPPER=b_stepper MOVE=-45"  # B axis to -45°
                ]
                
                success_count = 0
                for i, command in enumerate(commands):
                    result = self.printer_controller.send_gcode(command)
                    if result["success"]:
                        success_count += 1
                        self.log_output.append(f"✅ Step {i+1}/5: {command}")
                    else:
                        self.log_output.append(f"❌ Step {i+1}/5 failed: {command} - {result['error']}")
                        break
                
                self.progress_bar.setVisible(False)
                
                if success_count == len(commands):
                    QMessageBox.information(self, "Setup Complete", 
                                          "Mass production setup completed successfully!\n"
                                          "Printer is ready for mass production mode.")
                    self.log_output.append("🏭 ✅ Mass production setup completed successfully!")
                else:
                    QMessageBox.warning(self, "Setup Incomplete", 
                                      f"Setup partially completed ({success_count}/{len(commands)} steps).\n"
                                      "Check process log for details.")
                    
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "Setup Error", f"An error occurred: {str(e)}")
                self.log_output.append(f"❌ Mass production setup error: {str(e)}")

    def setup_five_axis(self):
        """Setup printer for 5-axis printing: Z+25, B-90"""
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        # Confirm before executing
        reply = QMessageBox.question(self, "Confirm 5-Axis Setup", 
                                   "Execute 5-axis printing setup sequence:\n"
                                   "• Move Z axis +25mm\n"
                                   "• Rotate B axis -90°\n\n"
                                   "Continue?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.log_output.append("🔧 Executing 5-axis printing setup sequence...")
            
            try:
                # Execute sequence step by step
                commands = [
                    "G91",  # Relative positioning
                    "G1 Z25 F1000",  # Move Z up 25mm
                    "G90",  # Absolute positioning
                    "MANUAL_STEPPER STEPPER=b_stepper MOVE=-90"  # B axis to -90°
                ]
                
                success_count = 0
                for i, command in enumerate(commands):
                    result = self.printer_controller.send_gcode(command)
                    if result["success"]:
                        success_count += 1
                        self.log_output.append(f"✅ Step {i+1}/4: {command}")
                    else:
                        self.log_output.append(f"❌ Step {i+1}/4 failed: {command} - {result['error']}")
                        break
                
                self.progress_bar.setVisible(False)
                
                if success_count == len(commands):
                    QMessageBox.information(self, "Setup Complete", 
                                          "5-axis printing setup completed successfully!\n"
                                          "Printer is ready for 5-axis printing mode.")
                    self.log_output.append("🔧 ✅ 5-axis printing setup completed successfully!")
                else:
                    QMessageBox.warning(self, "Setup Incomplete", 
                                      f"Setup partially completed ({success_count}/{len(commands)} steps).\n"
                                      "Check process log for details.")
                    
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "Setup Error", f"An error occurred: {str(e)}")
                self.log_output.append(f"❌ 5-axis setup error: {str(e)}")

    def home_all_axes(self):
        """Home all printer axes"""
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        # Confirm before executing
        reply = QMessageBox.question(self, "Confirm Homing", 
                                   "Home all axes (G28)?\n\n"
                                   "This will move all axes to their home positions.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.log_output.append("🏠 Homing all axes...")
            
            try:
                result = self.printer_controller.home_all_axes()
                if result["success"]:
                    QMessageBox.information(self, "Homing Complete", "All axes homed successfully!")
                    self.log_output.append("🏠 ✅ All axes homed successfully!")
                else:
                    QMessageBox.critical(self, "Homing Failed", f"Homing failed: {result['error']}")
                    self.log_output.append(f"❌ Homing failed: {result['error']}")
            except Exception as e:
                QMessageBox.critical(self, "Homing Error", f"An error occurred: {str(e)}")
                self.log_output.append(f"❌ Homing error: {str(e)}")

    def emergency_stop(self):
        """Emergency stop the printer"""
        if not self.printer_controller:
            QMessageBox.warning(self, "Not Connected", "Please test printer connection first.")
            return
            
        # No confirmation for emergency stop - it should be immediate
        self.log_output.append("🛑 EMERGENCY STOP ACTIVATED!")
        
        try:
            result = self.printer_controller.emergency_stop()
            if result["success"]:
                QMessageBox.critical(self, "Emergency Stop", "Emergency stop executed!\nPrinter has been stopped.")
                self.log_output.append("🛑 ✅ Emergency stop executed successfully!")
            else:
                QMessageBox.critical(self, "Emergency Stop Failed", f"Emergency stop failed: {result['error']}")
                self.log_output.append(f"❌ Emergency stop failed: {result['error']}")
        except Exception as e:
            QMessageBox.critical(self, "Emergency Stop Error", f"An error occurred: {str(e)}")
            self.log_output.append(f"❌ Emergency stop error: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # Set application properties for better full screen experience
    app.setApplicationName("3D Bending & IK G-code Utility")
    app.setOrganizationName("GCode Processor")
    
    window = GCodeProcessorGUI()
    
    # Show window first
    window.show()
    
    # Use timer to maximize after window is fully shown (prevents resizing issues)
    def maximize_window():
        window.showMaximized()
        window.raise_()  # Bring to front
        window.activateWindow()  # Set focus
        window.log_output.append("🖥️ Application started in maximized mode (F11 for full screen)")
    
    # Set timer to maximize window after 100ms to ensure proper initialization
    QTimer.singleShot(100, maximize_window)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 