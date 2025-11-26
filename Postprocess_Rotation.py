#!/usr/bin/env python3
"""
rotation_compensate_one_axis.py

Single-axis rotation compensation:
- uses timestamps like [1758212275572762046] (nanoseconds in brackets)
- user selects an analysis time window
- computes dominant rotation frequency (FFT) -> RPM
- fits sinusoid at that frequency (A*sin(omega t + phi) + offset)
- subtracts fitted rotation component -> compensated signal
- plots original, fitted rotation, compensated, FFT (peak labeled)
- saves selected section CSV and JSON summary
"""
import os
import json
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector
from scipy.signal import find_peaks
from scipy.optimize import curve_fit
import tkinter as tk
from tkinter import filedialog

# -------------------------
# Helpers
# -------------------------
def parse_timestamp_field(col_values):
    """Parse bracketed nanosecond timestamps -> seconds since epoch (float)."""
    secs = []
    for v in col_values:
        s = str(v).strip()
        if s.startswith('[') and s.endswith(']'):
            s = s[1:-1]
        try:
            iv = int(s)
        except Exception:
            try:
                iv = float(s)
            except Exception:
                raise ValueError(f"Can't parse timestamp value: {v!r}")
        # assume nanoseconds -> seconds
        secs.append(iv / 1e9)
    return np.array(secs, dtype=float)

def compute_fft_for_plot(t_rel, sig):
    """
    Resample onto uniform grid using mean dt, compute rfft and return freqs, mag, fs.
    t_rel: time vector in seconds (relative)
    sig: signal
    """
    if len(t_rel) < 2:
        return np.array([0.0]), np.array([0.0]), 1.0
    dt_mean = np.mean(np.diff(t_rel))
    fs = 1.0 / dt_mean
    # uniform grid from first to last inclusive
    t_uniform = np.arange(t_rel[0], t_rel[-1] + dt_mean/2, dt_mean)
    sig_uniform = np.interp(t_uniform, t_rel, sig)
    N = len(sig_uniform)
    fft_vals = np.fft.rfft(sig_uniform - np.mean(sig_uniform))  # remove mean for clarity
    fft_freqs = np.fft.rfftfreq(N, dt_mean)
    fft_mag = np.abs(fft_vals) * 2.0 / N
    return fft_freqs, fft_mag, fs

def fit_sinusoid_least_squares(t, y, freq_hz):
    """
    Fit y(t) = B*sin(omega t) + C*cos(omega t) + D  (linear in B,C,D)
    Return amplitude A, phase phi (radians), offset D, and reconstructed fitted signal.
    """
    omega = 2.0 * np.pi * freq_hz
    # design matrix columns: sin(omega t), cos(omega t), 1
    S = np.column_stack([np.sin(omega * t), np.cos(omega * t), np.ones_like(t)])
    # solve least squares
    coeffs, *_ = np.linalg.lstsq(S, y, rcond=None)
    B, C, D = coeffs
    A = np.hypot(B, C)
    phi = np.arctan2(C, B)  # as derived: y = B*sin + C*cos = A*sin(omega t + phi)
    y_fit = (B * np.sin(omega * t) + C * np.cos(omega * t) + D)
    return float(A), float(phi), float(D), y_fit

# -------------------------
# User picks CSV file
# -------------------------
root = tk.Tk()
root.withdraw()
file_path = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "*.csv")])
if not file_path:
    print("No file selected. Exiting.")
    raise SystemExit

df = pd.read_csv(file_path)
print("Columns detected:", df.columns.tolist())

# -------------------------
# Identify timestamp + axis column (ask user if ambiguous)
# -------------------------
cols = df.columns.tolist()
# timestamp detection
if 'timestamp' in [c.lower() for c in cols]:
    t_col = next(c for c in cols if c.lower() == 'timestamp')
else:
    t_col = cols[0]

# ask user to choose axis column if more than 2 columns
axis_col = None
# prefer common names z1, x1, etc.
for pref in ['z1', 'x1', 'y1', 'accel', 'acc']:
    for c in cols:
        if c.lower() == pref:
            axis_col = c
            break
    if axis_col:
        break
if axis_col is None:
    # fallback: if there are at least 2 columns use second column (as in your files)
    if len(cols) >= 2:
        axis_col = cols[1]
    else:
        raise SystemExit("Couldn't find axis column automatically. Make sure CSV has at least one data column.")

print(f"Using timestamp column: '{t_col}' and axis column: '{axis_col}'")

# -------------------------
# Parse time and signal
# -------------------------
t_seconds = parse_timestamp_field(df[t_col].values)
t0 = t_seconds[0]
t_rel = t_seconds - t0  # seconds since start
sig_raw = pd.to_numeric(df[axis_col], errors='coerce').values.astype(float)

# -------------------------
# Ask user to select analysis section (time-based)
# -------------------------
print("\nSelect the analysis time window (drag horizontally). Close the plot window when done.")
fig_sel, ax_sel = plt.subplots(figsize=(12,4))
ax_sel.plot(t_rel, sig_raw, label='raw')
ax_sel.set_title("Select analysis section (time axis in seconds since start)")
ax_sel.set_xlabel("Time (s) since start")
ax_sel.legend()

sel = [t_rel[0], t_rel[-1]]
def onselect(xmin, xmax):
    sel[0] = max(t_rel[0], float(xmin))
    sel[1] = min(t_rel[-1], float(xmax))
    print(f"Selected time window: {sel}")

span = SpanSelector(ax_sel, onselect, 'horizontal', useblit=True,
                    props=dict(alpha=0.3, facecolor='cyan'),
                    interactive=True, drag_from_anywhere=True)
plt.show()

start_t, end_t = sel
if end_t <= start_t:
    raise SystemExit("Invalid selection. Please select a non-zero width time window.")

# convert time window to indices (inclusive)
i0 = np.searchsorted(t_rel, start_t, side='left')
i1 = np.searchsorted(t_rel, end_t, side='right') - 1
i1 = min(i1, len(t_rel)-1)
if i1 <= i0:
    raise SystemExit("Selected window too small. Pick a larger region.")

t_window = t_rel[i0:i1+1]
sig_window = sig_raw[i0:i1+1]

# -------------------------
# FFT -> dominant frequency -> RPM
# -------------------------
freqs, mag, fs = compute_fft_for_plot(t_window, sig_window)
# ignore DC bin at index 0
if len(mag) <= 1:
    raise SystemExit("FFT failed: not enough samples.")

peak_idx = np.argmax(mag[1:]) + 1
dominant_freq = freqs[peak_idx]
dominant_mag = mag[peak_idx]
rpm = dominant_freq * 60.0

print(f"\nEstimated dominant frequency: {dominant_freq:.6f} Hz  -> RPM = {rpm:.3f}")

# -------------------------
# Fit sinusoid at dominant frequency
# -------------------------
A, phi, offset, fitted_rot = fit_sinusoid_least_squares(t_window, sig_window, dominant_freq)
omega = 2.0 * np.pi * dominant_freq
print(f"Fitted sinusoid: amplitude={A:.6f}, phase={phi:.4f} rad, offset={offset:.6f}")


import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

# -------------------------
# Interactive sinusoid adjustment (including time offset)
# -------------------------
fig_slider, ax_slider = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
plt.subplots_adjust(left=0.1, bottom=0.35, hspace=0.4)

# Original signal
l_orig, = ax_slider[0].plot(t_window, sig_window, label='Original')
ax_slider[0].set_ylabel('Signal')
ax_slider[0].legend()
ax_slider[0].set_title('Original and Fitted Sinusoid (Adjust with sliders)')

# Initial fitted rotation
l_fit, = ax_slider[0].plot(t_window, fitted_rot, '--', color='orange', label='Fitted rotation')
ax_slider[0].legend()

# Compensated signal plot
sig_comp_initial = sig_window - fitted_rot
l_comp, = ax_slider[1].plot(t_window, sig_comp_initial, label='Compensated (Original - Fitted)')
ax_slider[1].set_ylabel('Compensated signal')
ax_slider[1].legend()

# Slider axes
axcolor = 'lightgoldenrodyellow'
ax_amp = plt.axes([0.15, 0.25, 0.7, 0.03], facecolor=axcolor)
ax_freq = plt.axes([0.15, 0.2, 0.7, 0.03], facecolor=axcolor)
ax_off = plt.axes([0.15, 0.15, 0.7, 0.03], facecolor=axcolor)
ax_phase = plt.axes([0.15, 0.1, 0.7, 0.03], facecolor=axcolor)

# Sliders
s_amp = Slider(ax_amp, 'Amplitude', 0.0, 2*A, valinit=A, valstep=0.001)
s_freq = Slider(ax_freq, 'Frequency (Hz)', 0.0, 2*dominant_freq, valinit=dominant_freq, valstep=0.01)
s_off = Slider(ax_off, 'Vertical Offset', offset-2*A, offset+2*A, valinit=offset, valstep=0.001)
s_phase = Slider(ax_phase, 'Time Offset (s)', -0.5/dominant_freq, 0.5/dominant_freq, valinit=0.0, valstep=0.0001)

def update(val):
    amp = s_amp.val
    freq = s_freq.val
    off = s_off.val
    t_shift = s_phase.val
    omega_new = 2 * np.pi * freq
    # apply time shift as phase: phi = omega * t_shift
    fit_new = amp * np.sin(omega_new * (t_window - t_shift) + phi) + off
    sig_comp_new = sig_window - fit_new
    # update plots
    l_fit.set_ydata(fit_new)
    l_comp.set_ydata(sig_comp_new)
    fig_slider.canvas.draw_idle()

s_amp.on_changed(update)
s_freq.on_changed(update)
s_off.on_changed(update)
s_phase.on_changed(update)

plt.show()

# -------------------------
# Update fitted_rot with final slider values
# -------------------------
A = s_amp.val
dominant_freq = s_freq.val
offset = s_off.val
t_shift = s_phase.val
omega = 2 * np.pi * dominant_freq
fitted_rot = A * np.sin(omega * (t_window - t_shift) + phi) + offset
rpm = dominant_freq * 60.0
print(f"\nFinal adjusted parameters: amplitude={A:.6f}, frequency={dominant_freq:.6f} Hz ({rpm:.2f} RPM), offset={offset:.6f}, time_shift={t_shift:.6f} s")






# Also compute expected centrifugal amplitude from radius (user provided 0.19 m)
radius_m = 0.19  # 19 cm per your input
omega_phys = omega  # rad/s
expected_ac = radius_m * (omega_phys**2)
print(f"Expected centrifugal amplitude (r*omega^2): {expected_ac:.6f} (units of your accel data)")

# -------------------------
# Compensate: subtract fitted sinusoid
# -------------------------
sig_compensated = sig_window - fitted_rot

# -------------------------
# Plot original, fitted rotation, compensated
# -------------------------
fig1, ax1 = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
ax1[0].plot(t_window, sig_window, label='Original')
ax1[0].plot(t_window, fitted_rot, '--', label=f'Fitted rotation @ {dominant_freq:.3f} Hz')
ax1[0].legend()
ax1[0].set_ylabel('Signal')

ax1[1].plot(t_window, sig_window - offset, label='Original - offset')
ax1[1].plot(t_window, fitted_rot - offset, '--', label='Fitted rotation (zero-centered)')
ax1[1].legend()
ax1[1].set_ylabel('Zero-centered')

ax1[2].plot(t_window, sig_compensated, label='Compensated (original - fitted rotation)')
ax1[2].legend()
ax1[2].set_xlabel('Time (s) relative to section start')
ax1[2].set_ylabel('Compensated signal')

plt.suptitle(f"Rotation compensation (axis: {axis_col})\nDominant: {dominant_freq:.4f} Hz -> {rpm:.2f} RPM")
plt.tight_layout(rect=[0,0,1,0.97])
plt.show()

# -------------------------
# FFT plot with peak marked and labeled
# -------------------------
figf, axf = plt.subplots(figsize=(12,4))
axf.plot(freqs, mag, label='FFT magnitude')
# mark peak
axf.plot(dominant_freq, dominant_mag, 'ro', markersize=8, label='Dominant peak')
axf.annotate(f"{dominant_freq:.4f} Hz\n{rpm:.2f} RPM",
             xy=(dominant_freq, dominant_mag),
             xytext=(dominant_freq, dominant_mag*1.15),
             ha='center',
             arrowprops=dict(arrowstyle="->", lw=1))
axf.set_xlabel('Frequency (Hz)')
axf.set_ylabel('Amplitude')
axf.set_title('FFT (section)')
axf.set_xlim(0, freqs[-1])
axf.grid(True)
axf.legend()
plt.show()

# -------------------------
# Save results & selected section (with compensated column)
# -------------------------
base, ext = os.path.splitext(file_path)
timestr = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
selected_csv = f"{base}_selected_{timestr}.csv"

# build df_section (time absolute + relative + raw + fitted + compensated)
df_section = pd.DataFrame({
    'time_abs_s': t_seconds[i0:i1+1],
    'time_rel_s': t_window,
    axis_col + '_raw': sig_window,
    axis_col + '_rot_fit': fitted_rot,
    axis_col + '_compensated': sig_compensated
})
df_section.to_csv(selected_csv, index=False)
print(f"Selected section with compensated signal saved to: {selected_csv}")

summary = {
    'input_file': os.path.basename(file_path),
    'axis_column': axis_col,
    'selected_time_start_s_rel': float(t_window[0]),
    'selected_time_end_s_rel': float(t_window[-1]),
    'dominant_frequency_hz': float(dominant_freq),
    'rpm': float(rpm),
    'fit_amplitude': float(A),
    'fit_phase_rad': float(phi),
    'fit_offset': float(offset),
    'expected_centrifugal_r_omega2': float(expected_ac),
    'timestamp': datetime.datetime.now().isoformat(),
    'selected_csv': os.path.basename(selected_csv)
}
summary_file = f"{base}_rotation_summary_{timestr}.json"
with open(summary_file, 'w') as f:
    json.dump(summary, f, indent=2)
print(f"Summary saved to: {summary_file}")

print("\nDone.")
