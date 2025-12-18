#!/usr/bin/env python3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector
from scipy.signal import find_peaks
import tkinter as tk
from tkinter import filedialog
import os

# ===============================
# Ask user for CSV file
# ===============================
root = tk.Tk()
root.withdraw()

script_dir = os.path.dirname(os.path.abspath(__file__))
messdaten_dir = os.path.join(script_dir, "Messdaten")
initial_dir = messdaten_dir if os.path.exists(messdaten_dir) else script_dir

file_path = filedialog.askopenfilename(
    title="Select accelerometer CSV file",
    filetypes=[("CSV files", "*.csv")],
    initialdir=initial_dir
)
file_name = os.path.basename(file_path)

if not file_path:
    print("No file selected. Exiting.")
    exit()

# ===============================
# Load accelerometer CSV
# ===============================
df = pd.read_csv(file_path)

# ==========================================================
# Load corresponding edge timestamp file (_edges.csv)
# ==========================================================
edges_file_path = file_path.replace(".csv", "_edges.csv")
try:
    df_edges = pd.read_csv(edges_file_path)
    print(f"[INFO] Loaded edge timestamp file: {edges_file_path}")
    edge_times = df_edges['edge_timestamp'].values.astype(float)
except FileNotFoundError:
    df_edges = None
    edge_times = np.array([])
    print(f"[WARNING] Edge timestamp file not found: {edges_file_path}")

# -----------------------------------------
# Auto-select column (z1 or z2)
# -----------------------------------------
if "z1" in df.columns and df["z1"].abs().mean() > 0:
    col = "z1"
elif "z2" in df.columns:
    col = "z2"
else:
    raise ValueError("Neither z1 nor z2 found in CSV.")

print(f"[INFO] Using column: {col}")

z_raw = df[col].values

# ==========================================================
# FIRST: USER SELECTS SECTION FOR GRAVITY CALIBRATION
# ==========================================================
fig_g, ax_g = plt.subplots(figsize=(12,5))
ax_g.plot(df.index, z_raw, 'b')
ax_g.set_title(f"{file_name} — Select a flat section to estimate gravity (Column: {col})")
ax_g.set_xlabel("Sample index")
ax_g.set_ylabel(f"{col} raw")

gravity_selection = [0, len(df)]

def onselect_gravity(xmin, xmax):
    gravity_selection[0] = int(xmin)
    gravity_selection[1] = int(xmax)
    print(f"[Gravity] Selected section: {gravity_selection}")

span_g = SpanSelector(
    ax_g,
    onselect_gravity,
    'horizontal',
    useblit=True,
    props=dict(alpha=0.3, facecolor='red'),
    interactive=True,
    drag_from_anywhere=True
)

plt.show()

g_start, g_end = gravity_selection
g_measured = df[col].iloc[g_start:g_end].mean()
print(f"\nEstimated gravity from selection: {g_measured:.5f} g-units\n")

df[f"{col}_corr"] = df[col] - g_measured
z_corr = df[f"{col}_corr"].values

# ==========================================================
# SECOND: USER SELECTS SECTION FOR ANALYSIS
# ==========================================================
fig_s, ax_s = plt.subplots(figsize=(12,5))
ax_s.plot(df.index, z_corr, 'k')
ax_s.set_title(f"{file_name} — Select vibration section (gravity compensated, column: {col})")
ax_s.set_xlabel("Sample index")
ax_s.set_ylabel(f"{col} corrected")

analysis_selection = [0, len(df)]

def onselect_section(xmin, xmax):
    analysis_selection[0] = int(xmin)
    analysis_selection[1] = int(xmax)
    print(f"[Analysis] Selected section: {analysis_selection}")

span_s = SpanSelector(
    ax_s,
    onselect_section,
    'horizontal',
    useblit=True,
    props=dict(alpha=0.3, facecolor='blue'),
    interactive=True,
    drag_from_anywhere=True
)

plt.show()

start, end = analysis_selection
df_section = df.iloc[start:end+1]
z_section = df_section[f"{col}_corr"].values
time_section = np.arange(len(z_section))

# ==========================================================
# Process edge timestamps
# ==========================================================
if len(edge_times) > 0:
    # Select edges within analysis section
    if 'timestamp' in df_section.columns:
        ts_start = df_section['timestamp'].iloc[0]
        ts_end = df_section['timestamp'].iloc[-1]
        edges_in_section = edge_times[(edge_times >= ts_start) & (edge_times <= ts_end)]
        # convert nanoseconds to seconds if needed
        edges_in_section_sec = edges_in_section
        if edges_in_section.max() > 1e6:  # assume nanoseconds
            edges_in_section_sec = edges_in_section / 1e9
    else:
        # Use all edges
        edges_in_section_sec = edge_times / 1e9 if edge_times.max() > 1e6 else edge_times

    # Compute inter-edge intervals and mean frequency
    if len(edges_in_section_sec) > 1:
        dt_edges = np.diff(edges_in_section_sec)
        mean_freq = 1.0 / np.mean(dt_edges)
        print(f"\n[INFO] Edge-based average frequency: {mean_freq:.2f} Hz\n")
    else:
        print("\n[INFO] Not enough edge events to compute frequency.\n")
else:
    print("\n[INFO] No edge timestamps available.\n")

# ==========================================================
# Sampling rate from accelerometer timestamps
# ==========================================================
if 'timestamp' in df_section.columns:
    timestamps_sec = df_section['timestamp'].astype(float)
    if timestamps_sec.max() > 1e6:  # nanoseconds
        timestamps_sec /= 1e9
    dt = np.diff(timestamps_sec)
    sampling_rate = 1.0 / np.mean(dt)
    print(f"[INFO] Accelerometer sampling rate: {sampling_rate:.2f} Hz")
else:
    dt = 1.0
    sampling_rate = 1.0
    print(f"[WARNING] No timestamp column, assuming 1 Hz")

# ==========================================================
# FFT of vibration section
# ==========================================================
N = len(z_section)
z_section = z_section - np.mean(z_section)
window = np.hanning(N)
z_win = z_section * window
fft_vals = np.fft.fft(z_win)
fft_freq = np.fft.fftfreq(N, d=np.mean(dt))
fft_mag = np.abs(fft_vals) / N
fft_mag[1:-1] *= 2

pos_mask = fft_freq > 0
fft_freq_pos = fft_freq[pos_mask]
fft_mag_pos = fft_mag[pos_mask]

valid = (fft_freq_pos > 0.5) & (fft_freq_pos < 100.0)
peak_idx = np.argmax(fft_mag_pos[valid])
peak_freq = fft_freq_pos[valid][peak_idx]
peak_mag = fft_mag_pos[valid][peak_idx]

fig_fft, ax_fft = plt.subplots(figsize=(12,5))
ax_fft.plot(fft_freq_pos, fft_mag_pos, 'b')
ax_fft.plot(peak_freq, peak_mag, 'ro', markersize=8, label=f'Peak: {peak_freq:.2f} Hz')
ax_fft.annotate(f'{peak_freq:.2f} Hz',
                xy=(peak_freq, peak_mag),
                xytext=(10,10),
                textcoords='offset points',
                fontsize=10,
                bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
ax_fft.set_title(f"{file_name} — FFT of selected vibration section (Column: {col})")
ax_fft.set_xlabel("Frequency (Hz)")
ax_fft.set_ylabel("Magnitude")
ax_fft.legend()
ax_fft.grid(True)
plt.show()

# ==========================================================
# Automatic peak detection
# ==========================================================
peaks, _ = find_peaks(z_section, distance=5)
peak_values = z_section[peaks]

# ==========================================================
# User clicks peaks for damping calculation
# ==========================================================
selected_peaks = []

def on_click(event):
    if not event.inaxes:
        return
    idx = np.argmin(np.abs(peaks - int(event.xdata)))
    if idx not in selected_peaks:
        selected_peaks.append(idx)
    else:
        selected_peaks.remove(idx)
    update_peak_plot()

def update_peak_plot():
    ax_p.clear()
    ax_p.plot(time_section, z_section, 'k', label=f'{col} corrected')
    ax_p.plot(peaks, peak_values, 'ro', label='Detected peaks')
    if selected_peaks:
        ax_p.plot(peaks[selected_peaks], peak_values[selected_peaks],
                  'go', markersize=10, label='Selected')
    ax_p.legend()
    ax_p.set_title(f"{file_name} — Click peaks to select/deselect")
    ax_p.set_xlabel("Sample index")
    ax_p.set_ylabel(f"{col} corrected")
    fig_p.canvas.draw()

fig_p, ax_p = plt.subplots(figsize=(12,5))
fig_p.canvas.mpl_connect('button_press_event', on_click)
update_peak_plot()
plt.show()

# ==========================================================
# Compute damping ratio
# ==========================================================
if len(selected_peaks) < 2:
    print("\nERROR: Select at least 2 peaks.\n")
else:
    sel_vals = peak_values[selected_peaks]
    deltas = np.log(sel_vals[:-1] / sel_vals[1:])
    delta_mean = np.mean(deltas)
    zeta = delta_mean / np.sqrt(4 * np.pi**2 + delta_mean**2)
    print(f"\nEstimated damping ratio ζ = {zeta:.4f}\n")
