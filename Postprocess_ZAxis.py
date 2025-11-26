#!/usr/bin/env python3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector
from scipy.signal import find_peaks
import tkinter as tk
from tkinter import filedialog
from statistics import mean
import os

# ===============================
# Ask user for CSV file
# ===============================
root = tk.Tk()
root.withdraw()

# Get the script directory and construct path to Messdaten folder
script_dir = os.path.dirname(os.path.abspath(__file__))
messdaten_dir = os.path.join(script_dir, "Messdaten")

# Set initial directory to Messdaten if it exists, otherwise use script directory
initial_dir = messdaten_dir if os.path.exists(messdaten_dir) else script_dir

file_path = filedialog.askopenfilename(
    title="Select CSV file",
    filetypes=[("CSV files", "*.csv")],
    initialdir=initial_dir
)

# Keep just the CSV file name for plot titles
file_name = os.path.basename(file_path)

if not file_path:
    print("No file selected. Exiting.")
    exit()

# ===============================
# Load CSV with header
# ===============================
df = pd.read_csv(file_path)

# ==========================================================
# Load corresponding frequency file
# ==========================================================
freq_file_path = file_path.replace('.csv', '_freq.csv')
try:
    df_freq = pd.read_csv(freq_file_path)
    print(f"[INFO] Loaded frequency file: {freq_file_path}")
except FileNotFoundError:
    df_freq = None
    print(f"[WARNING] Frequency file not found: {freq_file_path}")
except Exception as e:
    df_freq = None
    print(f"[WARNING] Error reading frequency file: {e}")

# -----------------------------------------
# Auto-select correct column (z1 or z2)
# -----------------------------------------
if "z1" in df.columns and df["z1"].abs().mean() > 0:
    col = "z1"
else:
    col = "z2" if "z2" in df.columns else None

if col is None:
    print("ERROR: Neither z1 nor z2 found in CSV.")
    exit()

print(f"[INFO] Using column: {col}")

z_raw = df[col].values

# ==========================================================
# FIRST: USER SELECTS SECTION FOR GRAVITY CALIBRATION
# ==========================================================

fig_g, ax_g = plt.subplots(figsize=(12, 5))
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

# Compute gravity from selected section
if gravity_selection is not None:
    g_start, g_end = gravity_selection
    g_measured = df[col].iloc[g_start:g_end].mean()
    print(f"\nEstimated gravity from selection: {g_measured:.5f} g-units\n")

    # gravity-compensated signal
    df[f"{col}_corr"] = df[col] - g_measured
    z_corr = df[f"{col}_corr"].values
else:
    z_corr = z_raw

# ==========================================================
# SECOND: USER SELECTS SECTION FOR ANALYSIS
# ==========================================================

fig_s, ax_s = plt.subplots(figsize=(12, 5))
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

# Extract selected section
start, end = analysis_selection
df_section = df.iloc[start:end+1]
z_section = df_section[f"{col}_corr"].values
time_section = np.arange(len(z_section))

# ==========================================================
# Process frequency data for selected section
# ==========================================================
if df_freq is not None:
    # Extract frequency values for the selected section
    freq_section = df_freq['frequency_hz'].iloc[start:end+1].values
    
    # Filter out abnormally high values (threshold: e.g., > 100 Hz)
    threshold = 100.0  # Adjust this threshold as needed
    freq_filtered = freq_section[freq_section < threshold]
    freq_filtered = freq_filtered[freq_filtered > 0]  # Also remove zeros   
    
    if len(freq_filtered) > 0:
        avg_frequency = np.mean(freq_filtered)
        print(f"\n[INFO] Measured frequency statistics:")
        print(f"       Valid samples: {len(freq_filtered)} / {len(freq_section)}")
        print(f"       Average frequency: {avg_frequency:.2f} Hz\n")
    else:
        print(f"\n[WARNING] No valid frequency data found in selected section\n")

# Calculate sampling rate from timestamps
if 'timestamp' in df_section.columns:
    # Remove brackets and convert to numeric (timestamps are in format [1758212275572762046])
    timestamps_str = df_section['timestamp'].astype(str).str.strip('[]').values
    timestamps = pd.to_numeric(timestamps_str, errors='coerce')
    
    # Convert from nanoseconds to seconds (assuming timestamps are in nanoseconds)
    timestamps_sec = timestamps / 1e9
    
    time_diffs = np.diff(timestamps_sec)
    avg_dt = np.mean(time_diffs)
    sampling_rate = 1.0 / avg_dt
    print(f"\n[INFO] Calculated sampling rate: {sampling_rate:.2f} Hz (avg dt: {avg_dt:.6f} s)\n")
else:
    sampling_rate = 1.0
    avg_dt = 1.0
    print(f"\n[WARNING] No 'timestamp' column found, assuming sampling rate = {sampling_rate} Hz\n")

# ==========================================================
# FFT of selected vibration section
# ==========================================================
# Compute FFT
N = len(z_section)
fft_vals = np.fft.fft(z_section)
fft_freq = np.fft.fftfreq(N, d=avg_dt)

# Take only positive frequencies
pos_mask = fft_freq > 0
fft_freq_pos = fft_freq[pos_mask]
fft_mag_pos = np.abs(fft_vals[pos_mask])

# Find peak frequency
peak_idx = np.argmax(fft_mag_pos)
peak_freq = fft_freq_pos[peak_idx]
peak_mag = fft_mag_pos[peak_idx]

# Plot FFT
fig_fft, ax_fft = plt.subplots(figsize=(12, 5))
ax_fft.plot(fft_freq_pos, fft_mag_pos, 'b')
ax_fft.plot(peak_freq, peak_mag, 'ro', markersize=8, label=f'Peak: {peak_freq:.2f} Hz')
ax_fft.annotate(f'{peak_freq:.2f} Hz', 
                xy=(peak_freq, peak_mag), 
                xytext=(10, 10), 
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
# THIRD: USER CLICKS PEAKS FOR DAMPING CALCULATION
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
        ax_p.plot(peaks[selected_peaks],
                  peak_values[selected_peaks],
                  'go', markersize=10, label='Selected')

    ax_p.legend()
    ax_p.set_title(f"{file_name} — Click peaks to select/deselect")
    ax_p.set_xlabel("Sample index")
    ax_p.set_ylabel(f"{col} corrected")
    fig_p.canvas.draw()

fig_p, ax_p = plt.subplots(figsize=(12, 5))
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
