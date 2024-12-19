'''
Updates Pre-Github:
    
'''

import subprocess, sys, re, time, threading, json, csv, os, webbrowser
import tkinter as tk
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from tkinter import filedialog, ttk, messagebox, Toplevel, Scale

# iDRAC connection details
MEM_DIR = r"\\path\\" 
CUSTOM_COOLING_MAP = r"CoolingMap-Logarithmic.json"
SENSOR_LOGS = r"Sensor Logs.csv"
IDRAC_IP = "192.168.1.1"  # iDRAC
USERNAME = "username"           # iDRAC
PASSWORD = "password"         # iDRAC
TIMEOUT = 20                # Seconds
DEFAULT_MODE = 'Auto'       # iDRAC/Manual/Auto
DEFAULT_FAN_SPEED = 50      # %
MINIMUM_FAN_SPEED = 10      # %
MAXIMUM_FAN_SPEED = 100     # %
SENSOR_UPDATE_INTERVAL = 60 # Seconds
PREFIX = f"ipmitool -I lanplus -H {IDRAC_IP} -U {USERNAME} -P {PASSWORD}"

debug = True  # Debug mode (set to True for additional outputs)
sensor_command_debug = False
fan_speeds = {}
temps = {}
custom_graph = {}  # Temp-to-Fan-Speed mapping
data_history = []  # Global variable to store historical sensor data


# Max Fan RPM is ~ 12,500 RPM
def run_command(command):
    if debug == True:
        command_meaning = '(command_meaning)'
        print(f'Running Command:  {command} {command_meaning}')
    try:
        result = subprocess.run(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=TIMEOUT
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("Error: Command timed out.")
        return ""
    except Exception as e:
        print(f"Error: {e}")
        return ""
def fetch_sensor_data():
    global fan_speeds, temps, data_history
    fan_speeds.clear()
    temps.clear()
    temp_values = []

    try:
        # Run the ipmitool command and wait for it to complete
        output = run_command(f"{PREFIX} sensor")

        # Ensure the output is fully received before parsing
        if sensor_command_debug:
            print("Raw Sensor Output Received:")
            print(output)  # Log full output for verification

        if not output:
            print("No data received from the server. Check the connection.")
            return  # Exit early if output is empty

        output_lines = output.split("\n")

        # Regex patterns for fans, temperatures, voltage, and power
        fan_pattern = re.compile(r"^(Fan[1-6])\s+\|\s+([\d.]+)\s+\| RPM")
        temp_pattern = re.compile(r"^(Inlet Temp|Exhaust Temp|Temp)\s+\|\s+([\d.]+)")
        voltage_pattern = re.compile(r"^(Voltage 1|Voltage 2)\s+\|\s+([\d.]+)")
        power_pattern = re.compile(r"^(Pwr Consumption)\s+\|\s+([\d.]+)")

        # Parse the fully received output
        for line in output_lines:
            line = line.strip()

            # Match and store fan speeds
            fan_match = fan_pattern.search(line)
            if fan_match:
                fan_name, fan_value = fan_match.groups()
                fan_speeds[fan_name] = float(fan_value)

            # Match and store temperatures
            temp_match = temp_pattern.search(line)
            if temp_match:
                label, value = temp_match.groups()
                value = float(value)
                temp_values.append(value)
                temps[label] = value

            # Match and store voltages
            voltage_match = voltage_pattern.search(line)
            if voltage_match:
                label, value = voltage_match.groups()
                temps[label] = float(value)

            # Match and store power consumption
            power_match = power_pattern.search(line)
            if power_match:
                label, value = power_match.groups()
                temps[label] = float(value)

        # Use the maximum temperature for fan control
        if temp_values:
            temps["Max Temp"] = max(temp_values)

        # Calculate averages for fan speeds and voltages
        avg_fan_speed = sum(fan_speeds.values()) / len(fan_speeds) if fan_speeds else 0
        avg_voltage = (temps.get("Voltage 1", 0) + temps.get("Voltage 2", 0)) / 2

        # Append to data history
        timestamp = datetime.now().strftime("%m-%d-%y | %I:%M%p").lower()
        data_entry = {
            "timestamp": timestamp,
            "Avg Temp": sum(temp_values) / len(temp_values) if temp_values else 0,
            "Max Temp": temps.get("Max Temp", 0),
            "Avg Fan Speed": avg_fan_speed,
            "Avg Voltage": avg_voltage,
            "Pwr Consumption": temps.get("Pwr Consumption", 0),
        }
        data_history.append(data_entry)

        if debug:
            print("Parsed Sensor Data:")
            print(data_entry)  # Display the fully parsed data

        # Save the updated sensor history
        FanControlGUI.save_sensor_history()

    except Exception as e:
        print(f"Error fetching data: {e}")

class FanControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.geometry("600x400")

        self.mode = tk.StringVar(value=DEFAULT_MODE)  # Default mode to Auto
        self.fan_speed = tk.IntVar(value=DEFAULT_FAN_SPEED)

        # Disable iDRAC control at startup
        run_command(f"{PREFIX} raw 0x30 0x30 0x01 0x00")

        # Load fan configuration from the static file
        self.load_cooling_map()

        ttk.Label(root, text="Dell R720 Fan Sensor Monitor", font=("Arial", 16, "bold")).pack(pady=10)

        # Mode Selection
        mode_frame = ttk.LabelFrame(root, text="Fan Control Mode")
        mode_frame.pack(fill="x", padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text="iDRAC Control", variable=self.mode, value="iDRAC", command=self.switch_mode).pack(side="left")
        ttk.Radiobutton(mode_frame, text="Manual", variable=self.mode, value="Manual", command=self.switch_mode).pack(side="left")
        ttk.Radiobutton(mode_frame, text="Auto (Custom)", variable=self.mode, value="Auto", command=self.switch_mode).pack(side="left")

        # Manual Control
        self.manual_frame = ttk.LabelFrame(root, text="Manual Fan Control")
        self.manual_frame.pack(fill="x", padx=10, pady=5)
        self.manual_entry = ttk.Entry(self.manual_frame, textvariable=self.fan_speed, width=5, state="disabled")
        self.manual_entry.pack(side="left", padx=5)
        ttk.Label(self.manual_frame, text="% Fan Speed").pack(side="left")
        self.apply_button = ttk.Button(self.manual_frame, text="Apply", command=self.apply_manual_speed, state="disabled")
        self.apply_button.pack(side="left", padx=5)
        self.manual_entry.bind("<Return>", lambda event: self.apply_manual_speed())

        # Sensor Display
        self.sensor_frame = ttk.Frame(root)
        self.sensor_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.temp_frame = ttk.LabelFrame(self.sensor_frame, text="Temperatures")
        self.temp_frame.pack(side="left", fill="both", expand=True, padx=5)
        self.fan_frame = ttk.LabelFrame(self.sensor_frame, text="Fan Speeds")
        self.fan_frame.pack(side="right", fill="both", expand=True, padx=5)

        self.fan_labels = {}
        self.temp_labels = {}
        self.populate_sensor_labels()

        # Add button to show the historical graph window
        ttk.Button(root, text="Show Historic Graph", command=self.window_historic_graph).pack(pady=10)

        # Start background updates
        self.start_background_sensor_updates()
    def populate_sensor_labels(self):
        # Temperature Labels
        for key in ["Inlet Temp", "Exhaust Temp", "CPU Pkg"]:  # Replace Temp with CPU Pkg
            self.temp_labels[key] = ttk.Label(self.temp_frame, text=f"{key}: --- °C / --- °F")
            self.temp_labels[key].pack(anchor="w")

        # Add Power Stats Header
        power_frame = ttk.LabelFrame(self.temp_frame, text="Power Stats")
        power_frame.pack(fill="x", padx=0, pady=15, anchor="s")  # Place at the bottom of the temp frame

        # Power Stats Labels inside the Power Frame
        self.temp_labels["Voltage 1"] = ttk.Label(power_frame, text="Voltage 1: --- v")
        self.temp_labels["Voltage 1"].pack(anchor="w")

        self.temp_labels["Voltage 2"] = ttk.Label(power_frame, text="Voltage 2: --- v")
        self.temp_labels["Voltage 2"].pack(anchor="w")

        self.temp_labels["Pwr Consumption"] = ttk.Label(power_frame, text="Power: --- w")
        self.temp_labels["Pwr Consumption"].pack(anchor="w")

        # Fan Speed Labels
        for i in range(1, 7):
            self.fan_labels[f"Fan{i}"] = ttk.Label(self.fan_frame, text=f"Fan{i}: --- RPM")
            self.fan_labels[f"Fan{i}"].pack(anchor="w")
    def update_sensor_labels(self):
        # Update displayed fan speeds
        for fan, value in fan_speeds.items():
            if fan in self.fan_labels:
                self.fan_labels[fan].config(text=f"{fan}: {int(value)} RPM")

        # Update displayed temperatures
        for temp, value in temps.items():
            fahrenheit = (value * 9 / 5) + 32  # Celsius to Fahrenheit
            if temp == "Max Temp":  # CPU Pkg
                self.temp_labels["CPU Pkg"].config(text=f"CPU Pkg: {round(value, 2)}°C / {round(fahrenheit, 2)}°F")
            elif temp in self.temp_labels:
                self.temp_labels[temp].config(text=f"{temp}: {round(value, 2)}°C / {round(fahrenheit, 2)}°F")

        # Update power stats
        for key in ["Voltage 1", "Voltage 2", "Pwr Consumption"]:
            if key in self.temp_labels and key in temps:
                self.temp_labels[key].config(text=f"{key}: {temps[key]}v" if "Voltage" in key else f"Power: {temps[key]}w")

        # Automatically calculate and apply fan speed in Auto mode
        if self.mode.get() == "Auto":
            current_temp = temps.get("Max Temp", 0)  # Use Max Temp for CPU Pkg
            calculated_fan_speed = self.calculate_auto_speed(current_temp)

            # Update manual fan speed display box for visibility
            self.fan_speed.set(calculated_fan_speed)

            # Send the calculated fan speed to the system
            self.apply_auto_fan_speed(calculated_fan_speed)

            if debug:
                print(f"Auto Mode: Current Temp: {current_temp}°C -> Calculated Fan Speed: {calculated_fan_speed}%")

    def load_cooling_map(self):
        global custom_graph
        try:
            search_path = os.path.join(MEM_DIR, CUSTOM_COOLING_MAP)
            with open(search_path, "r") as file:
                custom_graph = json.load(file)
                # Ensure keys are integers
                custom_graph = {int(k): int(v) for k, v in custom_graph.items()}
                print(f"Loaded fan configuration from {search_path}: {custom_graph}")
        except FileNotFoundError:
            print(f"Configuration file {search_path} not found. Using default settings.")
            custom_graph = {}
        except Exception as e:
            print(f"Error loading configuration file: {e}")
            custom_graph = {}
    def switch_mode(self):
        if debug == True:
            print(f'Switching mode to: {self.mode.get()}')
        if self.mode.get() == "iDRAC":
            run_command(f"{PREFIX} raw 0x30 0x30 0x01 0x01")
            self.manual_entry.config(state="disabled")
            self.apply_button.config(state="disabled")
        elif self.mode.get() == "Manual":
            run_command(f"{PREFIX} raw 0x30 0x30 0x01 0x00")
            self.manual_entry.config(state="normal")
            self.apply_button.config(state="normal")
        elif self.mode.get() == "Auto":
            self.window_auto_mode_setup()
    
    def start_background_sensor_updates(self):
        def update():
            while True:
                fetch_sensor_data()
                self.root.after(0, self.update_sensor_labels)
                time.sleep(SENSOR_UPDATE_INTERVAL)

        threading.Thread(target=update, daemon=True).start()
    def calculate_auto_speed(self, temp):
        if temp < 50:  # Below minimum temperature
            fan_speed = MINIMUM_FAN_SPEED
        elif temp > 90:  # Above maximum temperature
            fan_speed = MAXIMUM_FAN_SPEED
        else:
            # Use the custom graph for intermediate temperatures
            fan_speed = MAXIMUM_FAN_SPEED  # Default to max if no match
            for threshold in sorted(custom_graph.keys()):
                if temp <= threshold:
                    fan_speed = custom_graph[threshold]
                    break

        # Ensure fan speed is within the valid range
        fan_speed = max(MINIMUM_FAN_SPEED, min(fan_speed, MAXIMUM_FAN_SPEED))
        return fan_speed
    
    def apply_manual_speed(self):
        speed = self.fan_speed.get()

        # Ensure speed is a numeric value
        if isinstance(speed, str):
            speed = float(speed)

        if MINIMUM_FAN_SPEED <= speed <= MAXIMUM_FAN_SPEED:
            # Scale speed to 0–64 range
            scaled_value = int((64 / 100) * speed)  # Scale to 0-64 range
            hex_value = f"{scaled_value:02}"  # Format as two-digit value
            if debug:
                print(f"Applying Manual Fan Speed: {speed}% -> Hex Value: {hex_value}")
            run_command(f"{PREFIX} raw 0x30 0x30 0x02 0xff 0x{hex_value}")
        else:
            messagebox.showerror("Error", "Fan speed must be between 25 and 100.")
    def apply_auto_fan_speed(self, speed):
        # Ensure speed is a numeric value
        if isinstance(speed, str):
            speed = float(speed)

        if MINIMUM_FAN_SPEED <= speed <= MAXIMUM_FAN_SPEED:
            # Scale speed to 0–64 range
            scaled_value = int((64 / 100) * speed)  # Scale to 0-64 range
            hex_value = f"{scaled_value:02}"  # Format as two-digit value
            if debug:
                print(f"Applying Auto Fan Speed: {speed}% -> Hex Value: {hex_value}")
            run_command(f"{PREFIX} raw 0x30 0x30 0x02 0xff 0x{hex_value}")
        else:
            print(f"Invalid Auto Fan Speed: {speed}. It must be between {MINIMUM_FAN_SPEED}% and {MAXIMUM_FAN_SPEED}%.")

    def window_auto_mode_setup(self):
        if debug:
            print(f'Opening Cooling Map Setup...')
        graph_window = Toplevel(self.root)
        graph_window.title("Custom Auto Mode Setup")
        graph_window.geometry("600x400")
        unsaved_changes = False  # Track if there are unsaved changes

        ttk.Label(graph_window, text="Set Fan Speed for Each Temperature Range").pack(pady=5)

        # Dictionary to store input fields
        inputs = {}

        # Load existing values
        def load_existing_values():
            for temp in range(50, 95, 5):
                frame = ttk.Frame(graph_window)
                frame.pack(fill="x", pady=2)

                ttk.Label(frame, text=f"{temp}°C", width=10).pack(side="left")
                value = custom_graph.get(temp, 50)  # Default to 50% fan speed
                entry = ttk.Entry(frame, width=10)
                entry.insert(0, value)
                entry.pack(side="left")
                inputs[temp] = entry

                # Detect changes
                entry.bind("<KeyRelease>", lambda event: set_unsaved())
        def set_unsaved(flag=True):
            nonlocal unsaved_changes
            unsaved_changes = flag
        def save_and_apply():
            nonlocal unsaved_changes
            custom_graph.clear()
            for temp, entry in inputs.items():
                try:
                    value = int(entry.get())
                    if MINIMUM_FAN_SPEED <= value <= MAXIMUM_FAN_SPEED:
                        custom_graph[temp] = value
                    else:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Error", f"Invalid input for {temp}°C. Enter a value between {MINIMUM_FAN_SPEED} and {MINIMUM_FAN_SPEED}.")
                    return
            print("Custom Graph Saved:", custom_graph)
            unsaved_changes = False
            graph_window.destroy()
        def reset_values():
            custom_graph.clear()
            for entry in inputs.values():
                entry.delete(0, tk.END)
                entry.insert(0, 50)
            set_unsaved()
            print("Custom Graph Reset")
        def save_to_file():
            # Ensure custom_graph is updated before saving
            custom_graph.clear()
            for temp, entry in inputs.items():
                try:
                    value = int(entry.get())
                    if MINIMUM_FAN_SPEED <= value <= MAXIMUM_FAN_SPEED:
                        custom_graph[temp] = value
                    else:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Error", f"Invalid input for {temp}°C. Enter a value between 25 and 100.")
                    return

            # Use file dialog to save JSON
            file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
            if file_path:
                try:
                    with open(file_path, "w") as file:
                        json.dump(custom_graph, file, indent=4)
                    print(f"Custom Graph Saved to: {file_path}")
                    set_unsaved(False)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save file: {e}")
        def load_from_file():
            file_path = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
            if file_path:
                try:
                    with open(file_path, "r") as file:
                        loaded_data = json.load(file)
                        custom_graph.clear()
                        # Ensure all keys are integers and override the graph
                        custom_graph.update({int(k): int(v) for k, v in loaded_data.items()})

                    print(f"Custom Graph Loaded from: {file_path}")

                    # Update the inputs with loaded values
                    for temp, entry in inputs.items():
                        entry.delete(0, tk.END)  # Clear existing value
                        entry.insert(0, custom_graph.get(temp, 50))  # Insert loaded or default value

                    set_unsaved()  # Mark changes as unsaved
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load file: {e}")
        def on_close():
            if unsaved_changes:
                if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Close without saving?"):
                    graph_window.destroy()
            else:
                graph_window.destroy()

        # Load inputs and add buttons
        load_existing_values()
        button_frame = ttk.Frame(graph_window)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Save & Apply", command=save_and_apply).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Reset", command=reset_values).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Save to File", command=save_to_file).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Load from File", command=load_from_file).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_close).pack(side="left", padx=5)

        graph_window.protocol("WM_DELETE_WINDOW", on_close)
    def window_historic_graph(self, event=None):
        try:
            # Load data from the CSV file
            filepath = os.path.join(MEM_DIR, SENSOR_LOGS)
            if not os.path.exists(filepath):
                print("No historical data file found.")
                messagebox.showerror("Error", "No historical data available.")
                return

            # Prepare data
            timestamps = []
            temps = {"Inlet Temp": [], "Exhaust Temp": [], "CPU Min": [], "CPU Max": []}
            power_stats = {"Voltage 1": [], "Voltage 2": [], "Power": []}
            fan_rpm = {"Min RPM": [], "Max RPM": []}

            # Read data from the CSV file
            with open(filepath, "r") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    timestamps.append(row["timestamp"])

                    # Temperatures
                    temps["Inlet Temp"].append(float(row.get("Inlet Temp", 0)))
                    temps["Exhaust Temp"].append(float(row.get("Exhaust Temp", 0)))
                    temps["CPU Min"].append(float(row.get("Avg Temp", 0)))  # Treat as Min CPU Temp
                    temps["CPU Max"].append(float(row.get("Max Temp", 0)))  # Max CPU Temp

                    # Power Stats
                    power_stats["Voltage 1"].append(float(row.get("Avg Voltage", 0)))
                    power_stats["Voltage 2"].append(float(row.get("Avg Voltage", 0)))  # Assume similar for now
                    power_stats["Power"].append(float(row.get("Pwr Consumption", 0)))

                    # Fan RPM
                    fan_rpm["Min RPM"].append(min(float(row.get("Avg Fan Speed", 0)), 5000))  # Simulated Min
                    fan_rpm["Max RPM"].append(max(float(row.get("Avg Fan Speed", 0)), 5000))  # Simulated Max

            # Create subplots with 3 rows
            fig = make_subplots(
                rows=3, cols=1,
                subplot_titles=("Temperatures", "Power Stats", "Fan Speeds"),
                shared_xaxes=True,
                vertical_spacing=0.1
            )

            # 1. Temperatures (Top Graph)
            for label, values in temps.items():
                fig.add_trace(
                    go.Scatter(x=timestamps, y=values, mode="lines+markers", name=label),
                    row=1, col=1
                )

            # 2. Power Stats (Middle Graph)
            for label, values in power_stats.items():
                fig.add_trace(
                    go.Scatter(x=timestamps, y=values, mode="lines+markers", name=label),
                    row=2, col=1
                )

            # 3. Fan Speeds (Bottom Graph)
            for label, values in fan_rpm.items():
                fig.add_trace(
                    go.Scatter(x=timestamps, y=values, mode="lines+markers", name=label),
                    row=3, col=1
                )

            # Update layout
            fig.update_layout(
                title="Historical Sensor Metrics",
                height=900,  # Adjust for shorter graphs
                width=1200,
                showlegend=True,
                template="plotly_white"
            )

            # Update axis labels
            fig.update_xaxes(title_text="Timestamp", row=3, col=1)
            fig.update_yaxes(title_text="°C / °F", row=1, col=1)
            fig.update_yaxes(title_text="Volts / Watts", row=2, col=1)
            fig.update_yaxes(title_text="RPM", row=3, col=1)

            # Save the graph as an HTML file
            html_filepath = os.path.join(MEM_DIR, "historical_metrics.html")
            fig.write_html(html_filepath)

            # Open the HTML file in the default browser
            webbrowser.open(f"file://{html_filepath}", new=2)

            if debug:
                print(f"Graph saved to: {html_filepath}")

        except Exception as e:
            print(f"Error generating HTML graph: {e}")
            messagebox.showerror("Error", f"Failed to generate graph:\n{e}")

    @staticmethod
    def save_sensor_history():
        global data_history
        try:
            filepath = os.path.join(MEM_DIR, SENSOR_LOGS)

            # Check if the file exists; if not, write headers
            file_exists = os.path.isfile(filepath)
            with open(filepath, "a", newline="") as csvfile:
                fieldnames = ["timestamp", "Avg Temp", "Max Temp", "Avg Fan Speed", "Avg Voltage", "Pwr Consumption"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()  # Write headers if file is new

                # Append the latest entry
                for entry in data_history[-1:]:
                    writer.writerow(entry)
        except Exception as e:
            print(f"Error saving data history: {e}")
    @staticmethod
    def load_sensor_history():
        global data_history
        try:
            filepath = os.path.join(MEM_DIR, SENSOR_LOGS)
            data_history = []  # Clear existing data

            if os.path.exists(filepath):
                with open(filepath, "r", newline="") as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        # Convert numeric values back to float and preserve timestamps
                        row["Avg Temp"] = float(row["Avg Temp"])
                        row["Max Temp"] = float(row["Max Temp"])
                        row["Avg Fan Speed"] = float(row["Avg Fan Speed"])
                        row["Avg Voltage"] = float(row["Avg Voltage"])
                        row["Pwr Consumption"] = float(row["Pwr Consumption"])
                        data_history.append(row)
            else:
                print("No sensor history found. Starting with an empty history.")
                data_history = []

        except Exception as e:
            print(f"Error loading sensor history: {e}")
            data_history = []

if __name__ == "__main__":
    root = tk.Tk()
    app = FanControlGUI(root)
    root.mainloop()
