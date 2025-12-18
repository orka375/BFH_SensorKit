#!/usr/bin/env python3
"""
analyze_time_based.py

Uses real timestamps (nanoseconds in brackets) as time base.
Interactive steps:
 1) choose CSV
 2) select gravity section (time axis) -> avg per axis -> subtract
 3) select vibration section (time axis)
 4) for each axis x1,y1,z1: auto-detect peaks, interactive click-to-select peaks
 5) compute damping metrics (using actual times in seconds) and fit envelope
 6) save results
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
from matplotlib.widgets import Button

# -------------------------
# Helpers
# -------------------------
def parse_timestamp_field(col_values):
    """
    Parse timestamps like "[1758212275572762046]" -> float seconds since epoch
    Assumes values are integers in nanoseconds inside brackets.
    """
    secs = []
    for v in col_values:
        s = str(v).strip()
        # remove brackets if present
        if s.startswith('[') and s.endswith(']'):
            s = s[1:-1]
        # sometimes there may be stray characters, try int conversion
        try:
            iv = int(s)
        except Exception:
            # fallback: try float
            iv = float(s)
        # assume input is nanoseconds -> convert to seconds
        secs.append(iv / 1e9)
    return np.array(secs, dtype=float)

def exp_envelope(t, A, lamb):
    return A * np.exp(-lamb * t)

def fit_envelope(peak_times, peak_vals):
    if len(peak_times) < 2:
        return None
    try:
        p0 = (np.abs(peak_vals[0]), 0.1)  # initial guess
        popt, _ = curve_fit(exp_envelope, peak_times, np.abs(peak_vals), p0=p0, maxfev=10000)
        return popt[0], popt[1]
    except Exception:
        return None

def compute_damping_from_peaks_times(peak_times, peak_amps):
    """
    peak_times: array of times in seconds (monotonic)
    peak_amps: array of amplitudes (signed or abs). Use abs for log decrement.
    Returns dict of metrics.
    """
    if len(peak_times) < 2:
        return None

    times = np.asarray(peak_times, dtype=float)
    amps = np.abs(np.asarray(peak_amps, dtype=float))

    # logarithmic decrements between consecutive peaks
    deltas = np.log(amps[:-1] / amps[1:])
    delta_mean = np.mean(deltas)

    # damped period: mean difference between consecutive peak times
    periods = np.diff(times)
    T_d = np.mean(periods)
    if T_d <= 0:
        return None
    omega_d = 2.0 * np.pi / T_d

    # damping ratio
    zeta = delta_mean / np.sqrt(4.0 * np.pi**2 + delta_mean**2)

    # undamped natural frequency
    omega_n = omega_d / np.sqrt(1.0 - zeta**2) if zeta < 1.0 else float('nan')

    # Q-factor and time constant tau
    Q = 1.0 / (2.0 * zeta) if zeta > 0 else float('inf')
    tau = 1.0 / (zeta * omega_n) if (zeta > 0 and not np.isnan(omega_n) and omega_n != 0) else float('nan')

    return {
        'delta_mean': float(delta_mean),
        'zeta': float(zeta),
        'omega_d': float(omega_d),
        'omega_n': float(omega_n),
        'period_d': float(T_d),
        'Q': float(Q),
        'tau': float(tau),
        'peak_times': times.tolist(),
        'peak_amps': amps.tolist()
    }

# -------------------------
# Pick CSV file
# -------------------------
root = tk.Tk()
root.withdraw()
# Open file dialog starting in Messdaten if present
script_dir = os.path.dirname(os.path.abspath(__file__))
messdaten_dir = os.path.join(script_dir, "Messdaten")
initial_dir = messdaten_dir if os.path.exists(messdaten_dir) else script_dir
file_path = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "*.csv")], initialdir=initial_dir)
if not file_path:
    print("No file selected. Exiting.")
    raise SystemExit

df = pd.read_csv(file_path)
print("Columns detected:", df.columns.tolist())
file_name = os.path.basename(file_path)

# -------------------------
# Identify timestamp column and x1,y1,z1 columns
# -------------------------
cols = [c.strip() for c in df.columns.tolist()]

# timestamp column detection (common name 'timestamp' expected)
if 'timestamp' in [c.lower() for c in cols]:
    t_col = next(c for c in df.columns if c.lower() == 'timestamp')
else:
    # fallback to first column
    t_col = df.columns[0]

# axis columns: auto choose set x1/y1/z1 or x2/y2/z2 based on availability and signal
def exists(colname):
    return any(c.lower() == colname for c in df.columns)

def pick_axis_set():
    # Prefer explicit sets if present
    has_set1 = all(exists(n) for n in ['x1','y1','z1'])
    has_set2 = all(exists(n) for n in ['x2','y2','z2'])
    if has_set1 and has_set2:
        # choose the set with higher absolute mean across axes
        x1 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'x1')], errors='coerce').abs().mean()
        y1 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'y1')], errors='coerce').abs().mean()
        z1 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'z1')], errors='coerce').abs().mean()
        x2 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'x2')], errors='coerce').abs().mean()
        y2 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'y2')], errors='coerce').abs().mean()
        z2 = pd.to_numeric(df[next(c for c in df.columns if c.lower()== 'z2')], errors='coerce').abs().mean()
        mean1 = np.nanmean([x1,y1,z1])
        mean2 = np.nanmean([x2,y2,z2])
        use2 = mean2 > 0 and mean2 >= mean1
        if use2:
            return ('x2','y2','z2')
        else:
            return ('x1','y1','z1')
    if has_set1:
        return ('x1','y1','z1')
    if has_set2:
        return ('x2','y2','z2')
    # fallback: try generic x,y,z
    def find_col(pref):
        for c in df.columns:
            if c.lower() == pref:
                return c
        for c in df.columns:
            if c.lower().startswith(pref):
                return c
        return None
    cx = find_col('x') or (df.columns[1] if df.shape[1] > 1 else None)
    cy = find_col('y') or (df.columns[2] if df.shape[1] > 2 else None)
    cz = find_col('z') or (df.columns[3] if df.shape[1] > 3 else None)
    if all([cx,cy,cz]):
        return (cx,cy,cz)
    return (None,None,None)

sel_x, sel_y, sel_z = pick_axis_set()
if not all([t_col, sel_x, sel_y, sel_z]):
    raise SystemExit("Couldn't identify required columns (timestamp, x*, y*, z*). Check CSV headers.")

# Map selected lower-case names to actual column names in df
def actual_name(lower_name):
    for c in df.columns:
        if c.lower() == lower_name:
            return c
    return lower_name

col_x = actual_name(sel_x)
col_y = actual_name(sel_y)
col_z = actual_name(sel_z)

print(f"Using timestamp column: '{t_col}'")
print(f"Using axes columns: x='{col_x}', y='{col_y}', z='{col_z}'")

# Parse timestamps -> seconds
t_seconds = parse_timestamp_field(df[t_col].values)
# create a time0 relative axis (seconds since start)
t0 = t_seconds[0]
t_rel = t_seconds - t0

# convert signals to float
x_raw = pd.to_numeric(df[col_x], errors='coerce').values.astype(float)
y_raw = pd.to_numeric(df[col_y], errors='coerce').values.astype(float)
z_raw = pd.to_numeric(df[col_z], errors='coerce').values.astype(float)

n = len(df)

# -------------------------
# Gravity selection (time-based)
# -------------------------
print("\nSelect a flat (non-moving) time range to estimate gravity offsets for each axis.")
fig_g, ax_g = plt.subplots(figsize=(12, 4))
ax_g.plot(t_rel, x_raw, label='x raw', alpha=0.7)
ax_g.plot(t_rel, y_raw, label='y raw', alpha=0.7)
ax_g.plot(t_rel, z_raw, label='z raw', alpha=0.9)
ax_g.set_title(f"{file_name} — Drag to select gravity calibration section (time in seconds since start)")
ax_g.set_xlabel("Time (s) since start")
ax_g.legend()

grav_sel = [t_rel[0], t_rel[-1]]
def onselect_grav(xmin, xmax):
    # ensure xmin<xmax
    grav_sel[0] = max(t_rel[0], float(xmin))
    grav_sel[1] = min(t_rel[-1], float(xmax))
    print(f"[gravity time select] {grav_sel}")

span_g = SpanSelector(ax_g, onselect_grav, 'horizontal', useblit=True,
                      props=dict(alpha=0.3, facecolor='orange'),
                      interactive=True, drag_from_anywhere=True)
plt.show()

g_start_t, g_end_t = grav_sel
if g_end_t <= g_start_t:
    raise SystemExit("Invalid gravity selection. Please select a valid time range.")

# convert to indices for averaging
g_idx0 = np.searchsorted(t_rel, g_start_t, side='left')
g_idx1 = np.searchsorted(t_rel, g_end_t, side='right') - 1
g_idx1 = min(g_idx1, n-1)
if g_idx1 <= g_idx0:
    raise SystemExit("Gravity selection too small. Select a larger flat region.")

g_x = np.nanmean(x_raw[g_idx0:g_idx1+1])
g_y = np.nanmean(y_raw[g_idx0:g_idx1+1])
g_z = np.nanmean(z_raw[g_idx0:g_idx1+1])
print(f"Measured gravity offsets -> gx: {g_x:.6f}, gy: {g_y:.6f}, gz: {g_z:.6f}")

# subtract gravity offsets
x_corr = x_raw - g_x
y_corr = y_raw - g_y
z_corr = z_raw - g_z

# append corrected columns to df for saving later
df['x_corr'] = x_corr
df['y_corr'] = y_corr
df['z_corr'] = z_corr
df['time_s'] = t_seconds  # absolute epoch seconds
df['time_rel_s'] = t_rel  # relative to start

# -------------------------
# Select vibration section (time-based)
# -------------------------
print("\nSelect vibration section (time-based).")
fig_s, ax_s = plt.subplots(figsize=(12, 4))
ax_s.plot(t_rel, x_corr, label='x corrected', alpha=0.6)
ax_s.plot(t_rel, y_corr, label='y corrected', alpha=0.6)
ax_s.plot(t_rel, z_corr, label='z corrected', alpha=0.9)
ax_s.set_title(f"{file_name} — Drag to select vibration section (time in seconds since start)")
ax_s.set_xlabel("Time (s) since start")
ax_s.legend()

sec_sel = [t_rel[0], t_rel[-1]]
def onselect_sec(xmin, xmax):
    sec_sel[0] = max(t_rel[0], float(xmin))
    sec_sel[1] = min(t_rel[-1], float(xmax))
    print(f"[section time select] {sec_sel}")

span_s = SpanSelector(ax_s, onselect_sec, 'horizontal', useblit=True,
                      props=dict(alpha=0.3, facecolor='cyan'),
                      interactive=True, drag_from_anywhere=True)
plt.show()

s_start_t, s_end_t = sec_sel
if s_end_t <= s_start_t:
    raise SystemExit("Invalid vibration section selection. Please select a valid time range.")

s_idx0 = np.searchsorted(t_rel, s_start_t, side='left')
s_idx1 = np.searchsorted(t_rel, s_end_t, side='right') - 1
s_idx1 = min(s_idx1, n-1)
if s_idx1 <= s_idx0:
    raise SystemExit("Analysis selection too small. Select a larger region.")

df_section = df.iloc[s_idx0:s_idx1+1].reset_index(drop=True)
t_section_abs = df_section['time_s'].values            # absolute epoch seconds
t_section = df_section['time_rel_s'].values - df_section['time_rel_s'].values[0]  # seconds relative to section start
x_sec = df_section['x_corr'].values
y_sec = df_section['y_corr'].values
z_sec = df_section['z_corr'].values

# Optional: load corresponding frequency file and report average frequency within selection
freq_file_path = file_path.replace('.csv', '_freq.csv')
avg_frequency_info = None
if os.path.exists(freq_file_path):
    try:
        df_freq = pd.read_csv(freq_file_path)
        if 'frequency_hz' in df_freq.columns:
            freq_section = pd.to_numeric(df_freq['frequency_hz'], errors='coerce').iloc[s_idx0:s_idx1+1].values
            threshold = 3000.0
            freq_filtered = freq_section[(freq_section > 0) & (freq_section < threshold)]
            if freq_filtered.size > 0:
                avg_frequency = float(np.nanmean(freq_filtered))
                avg_frequency_info = {
                    'file': os.path.basename(freq_file_path),
                    'valid_samples': int(freq_filtered.size),
                    'total_samples': int(len(freq_section)),
                    'avg_hz': avg_frequency,
                }
                print(f"\n[INFO] Measured frequency statistics from {os.path.basename(freq_file_path)}")
                print(f"       Valid samples: {avg_frequency_info['valid_samples']} / {avg_frequency_info['total_samples']}")
                print(f"       Average frequency: {avg_frequency_info['avg_hz']:.2f} Hz\n")
            else:
                print("\n[WARNING] No valid frequency data found in selected section\n")
        else:
            print("\n[WARNING] 'frequency_hz' column not found in freq file\n")
    except Exception as e:
        print(f"\n[WARNING] Error reading frequency file: {e}\n")

# save selected section
base, ext = os.path.splitext(file_path)
timestr = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
# selected_csv = f"{base}_selected_{timestr}.csv"
# df_section.to_csv(selected_csv, index=False)
# print(f"Selected section saved to: {selected_csv}")

# -------------------------
# Per-axis analysis (Option A: separate peak selection windows)
# -------------------------
axes = [('x', x_sec), ('y', y_sec), ('z', z_sec)]
results = {}
for name, signal in axes:
    print(f"\n--- Axis {name.upper()} ---")

    # detect peaks on absolute signal (capture both positive & negative peaks)
    abs_sig = np.abs(signal)
    # use prominence relative to signal std to avoid many tiny peaks
    prom = max(np.std(abs_sig) * 0.1, 1e-6)
    peaks_idx, props = find_peaks(abs_sig, distance=3, prominence=prom)
    if peaks_idx.size == 0:
        print(f"No peaks detected for axis {name}. Skipping.")
        results[name] = None
        continue

    peak_times = t_section[peaks_idx]                          # times relative to section start (s)
    peak_times_abs = t_section_abs[peaks_idx]                 # absolute epoch seconds (useful for saving)
    peak_vals = signal[peaks_idx]

    # interactive peak selection window
    selected = []  # indices into peaks_idx array
    fig_p, ax_p = plt.subplots(figsize=(12,4))
    ax_p.plot(t_section, signal, label=f'{name} corrected')
    ax_p.plot(peak_times, peak_vals, 'ro', label='Detected peaks')
    ax_p.set_title(f"{file_name} — Axis {name.upper()} — Click near a red marker to toggle selection. Close window when done.")
    ax_p.set_xlabel("Time (s) relative to section start")
    ax_p.set_ylabel(f"{name} corrected")
    ax_p.legend()
    fig_p.canvas.draw()

    def on_click_axis(event, name=name):
        if event.inaxes != ax_p:
            return
        xclick = event.xdata
        # find nearest detected peak by time
        idx_rel = int(np.argmin(np.abs(peak_times - xclick)))
        if idx_rel in selected:
            selected.remove(idx_rel)
        else:
            selected.append(idx_rel)
        # refresh
        ax_p.clear()
        ax_p.plot(t_section, signal, label=f'{name} corrected')
        ax_p.plot(peak_times, peak_vals, 'ro', label='Detected peaks')
        if selected:
            sel_times = peak_times[selected]
            sel_vals = peak_vals[selected]
            ax_p.plot(sel_times, sel_vals, 'go', markersize=9, label='Selected peaks')
        ax_p.set_title(f"{file_name} — Axis {name.upper()} — Click near a red marker to toggle selection. Close window when done.")
        ax_p.set_xlabel("Time (s) relative to section start")
        ax_p.set_ylabel(f"{name} corrected")
        ax_p.legend()
        fig_p.canvas.draw()

    fig_p.canvas.mpl_connect('button_press_event', on_click_axis)
    plt.show()  # wait for user to close window

    if len(selected) < 2:
        print(f"Axis {name}: less than 2 peaks selected -> skipping damping calculation.")
        results[name] = None
        # save detected peaks file (none selected)
        peaks_out_df = pd.DataFrame({
            'time_abs_s': peak_times_abs,
            'time_rel_s': peak_times,
            'amp': peak_vals
        })
        # peaks_out_df.to_csv(f"{base}_{name}_peaks_{timestr}.csv", index=False)
        # print(f"Detected peaks for axis {name} saved to {base}_{name}_peaks_{timestr}.csv")
        continue

    # build arrays of selected peaks (ordered by time)
    selected_sorted = sorted(selected)
    sel_peak_times = peak_times[selected_sorted]           # relative seconds
    sel_peak_times_abs = peak_times_abs[selected_sorted]   # absolute epoch seconds
    sel_peak_vals = peak_vals[selected_sorted]

    # compute metrics using real times
    metrics = compute_damping_from_peaks_times(sel_peak_times, sel_peak_vals)
    env_fit = fit_envelope(sel_peak_times, sel_peak_vals)
    if env_fit is not None:
        A_fit, lamb_fit = env_fit
    else:
        A_fit, lamb_fit = (None, None)

    metrics.update({'envelope_A': float(A_fit) if A_fit is not None else None,
                    'envelope_lambda': float(lamb_fit) if lamb_fit is not None else None})
    results[name] = metrics

    # save selected peaks csv
    peaks_sel_df = pd.DataFrame({
        'time_abs_s': sel_peak_times_abs,
        'time_rel_s': sel_peak_times,
        'amp': sel_peak_vals
    })
    # peaks_sel_csv = f"{base}_{name}_selected_peaks_{timestr}.csv"
    # peaks_sel_df.to_csv(peaks_sel_csv, index=False)
    # print(f"Selected peaks for axis {name} saved to {peaks_sel_csv}")

    # Plot final figure with envelope + selected peaks
    figf, axf = plt.subplots(figsize=(12,4))
    axf.plot(t_section, signal, label=f'{name} corrected', alpha=0.6)
    axf.plot(peak_times, peak_vals, 'ro', label='Detected peaks', alpha=0.6)
    axf.plot(sel_peak_times, sel_peak_vals, 'go', markersize=8, label='Selected peaks')
    if A_fit is not None and lamb_fit is not None:
        tt = np.linspace(0, t_section[-1], 1000)
        env = A_fit * np.exp(-lamb_fit * tt)
        # use sign of first selected peak to provide signed envelope
        sign0 = np.sign(sel_peak_vals[0]) if len(sel_peak_vals) > 0 else 1.0
        axf.plot(tt, sign0 * env, 'k--', linewidth=2, label='Fitted envelope')
    axf.set_title(f"{file_name} — Axis {name.upper()} — Section with peaks & fitted envelope")
    axf.set_xlabel("Time (s) relative to section start")
    axf.set_ylabel(f"{name} corrected")
    axf.legend()
    plt.show()

# -------------------------
# FFT PLOTS FOR EACH AXIS
# -------------------------
print("\nGenerating FFT plots for each axis...")

def compute_fft(t, sig):
    """
    Compute FFT using irregular-sampling aware resampling.
    - t: time vector in seconds (relative)
    - sig: signal
    Returns freq (Hz), magnitude, fs
    """
    # resample to uniform grid
    dt_mean = np.mean(np.diff(t))
    fs = 1.0 / dt_mean

    # interpolation onto uniform time grid
    t_uniform = np.arange(t[0], t[-1], dt_mean)
    sig_uniform = np.interp(t_uniform, t, sig)

    N = len(sig_uniform)
    fft_vals = np.fft.rfft(sig_uniform)
    fft_freqs = np.fft.rfftfreq(N, dt_mean)
    fft_mag = np.abs(fft_vals) * 2.0 / N

    return fft_freqs, fft_mag, fs


axes_fft = [('x', x_sec), ('y', y_sec), ('z', z_sec)]

for name, sig in axes_fft:
    print(f"FFT axis {name.upper()}...")

    freqs, mag, fs = compute_fft(t_section, sig)

    # find the largest peak (skip 0 Hz)
    peak_index = np.argmax(mag[1:]) + 1
    peak_freq = freqs[peak_index]
    peak_mag = mag[peak_index]

    # plot
    fig_fft, ax_fft = plt.subplots(figsize=(12,4))
    ax_fft.plot(freqs, mag, label="FFT")

    # mark peak
    ax_fft.plot(peak_freq, peak_mag, 'ro', markersize=8, label="Peak")
    ax_fft.annotate(
        f"{peak_freq:.2f} Hz",
        xy=(peak_freq, peak_mag),
        xytext=(peak_freq, peak_mag * 1.05),
        ha='center',
        arrowprops=dict(arrowstyle="->", lw=1)
    )

    ax_fft.set_title(f"{file_name} — FFT of axis {name.upper()} (fs ≈ {fs:.2f} Hz)")
    ax_fft.set_xlabel("Frequency (Hz)")
    ax_fft.set_ylabel("Amplitude")
    ax_fft.set_xlim(0, freqs[-1])
    ax_fft.grid(True)
    ax_fft.legend()

    # Save button with suggested filename: FFT_<numbers>_<axis>.png
    numbers_in_name = ''.join(ch for ch in file_name if ch.isdigit())
    suggested_fft_name = f"FFT_{numbers_in_name}_{name}.png" if numbers_in_name else f"FFT_{os.path.splitext(file_name)[0]}_{name}.png"
    def on_save_fft(event, fig=fig_fft):
        initial_dir = os.path.dirname(file_path)
        save_path = filedialog.asksaveasfilename(
            title="Save FFT plot",
            defaultextension=".png",
            initialdir=initial_dir,
            initialfile=suggested_fft_name,
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf"), ("All Files", "*.*")],
        )
        if save_path:
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"[INFO] Saved FFT plot to: {save_path}")
    btn_ax = fig_fft.add_axes([0.85, 0.02, 0.12, 0.05])
    btn_save = Button(btn_ax, 'Save FFT')
    btn_save.on_clicked(on_save_fft)

    plt.show()


# -------------------------
# Save results summary
# -------------------------
summary = {
    'input_file': os.path.basename(file_path),
    # 'selected_section_csv': os.path.basename(selected_csv),
    'selected_section_indices': {'start_idx': int(s_idx0), 'end_idx': int(s_idx1)},
    'selected_section_times_abs': {'start_s': float(t_section_abs[0]), 'end_s': float(t_section_abs[-1])},
    'gravity_offsets': {'gx': float(g_x), 'gy': float(g_y), 'gz': float(g_z)},
    'timestamp': datetime.datetime.now().isoformat(),
    'per_axis': results
}
if avg_frequency_info is not None:
    summary['freq_stats'] = avg_frequency_info

summary_file = f"{base}_results_{timestr}.json"
with open(summary_file, 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\nAnalysis complete. Summary saved to: {summary_file}")
print("Per-axis summary:")
print(json.dumps(summary['per_axis'], indent=2))
