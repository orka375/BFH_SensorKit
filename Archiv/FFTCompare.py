import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector
import tkinter as tk
from tkinter import filedialog

# -------------------------
def parse_timestamp_field(col_values):
    secs = []
    for v in col_values:
        s = str(v).strip()
        if s.startswith('[') and s.endswith(']'):
            s = s[1:-1]
        iv = int(s)
        secs.append(iv / 1e9)
    return np.array(secs, dtype=float)

def compute_fft(t_rel, sig):
    dt_mean = np.mean(np.diff(t_rel))
    t_uniform = np.arange(t_rel[0], t_rel[-1]+dt_mean/2, dt_mean)
    sig_uniform = np.interp(t_uniform, t_rel, sig)
    N = len(sig_uniform)
    fft_vals = np.fft.rfft(sig_uniform - np.mean(sig_uniform))
    fft_freqs = np.fft.rfftfreq(N, dt_mean)
    fft_mag = np.abs(fft_vals)*2.0/N
    return fft_freqs, fft_mag

# -------------------------
root = tk.Tk()
root.withdraw()
file_paths = filedialog.askopenfilenames(title="Select CSV files", filetypes=[("CSV files","*.csv")])
if not file_paths:
    print("No files selected. Exiting.")
    exit()

fft_results = []

# -------------------------
for file_path in file_paths:
    df = pd.read_csv(file_path)
    t_col = next((c for c in df.columns if c.lower()=='timestamp'), df.columns[0])
    axis_col = next((c for c in ['z1','x1','y1','accel','acc'] if c in df.columns), df.columns[1])

    t_seconds = parse_timestamp_field(df[t_col].values)
    t_rel = t_seconds - t_seconds[0]
    sig_raw = pd.to_numeric(df[axis_col], errors='coerce').values.astype(float)

    fig, ax = plt.subplots(figsize=(12,4))
    ax.plot(t_rel, sig_raw, label='raw')
    ax.set_title(f"{os.path.basename(file_path)} - Select section")
    ax.set_xlabel("Time (s)")
    ax.legend()

    sel = [t_rel[0], t_rel[-1]]
    def onselect(xmin, xmax):
        sel[0] = max(t_rel[0], float(xmin))
        sel[1] = min(t_rel[-1], float(xmax))
        print(f"Selected time window: {sel}")

    span = SpanSelector(ax, onselect, 'horizontal', useblit=True,
                        props=dict(alpha=0.3, facecolor='cyan'), interactive=True)
    plt.show()

    start_t, end_t = sel
    i0 = np.searchsorted(t_rel, start_t)
    i1 = np.searchsorted(t_rel, end_t) - 1
    i1 = min(i1, len(t_rel)-1)
    t_window = t_rel[i0:i1+1]
    sig_window = sig_raw[i0:i1+1]

    freqs, mag = compute_fft(t_window, sig_window)
    fft_results.append({
        'file': os.path.basename(file_path),
        'freqs': freqs,
        'mag': mag
    })

#
CUTIT = True
# -------------------------
plt.figure(figsize=(12,5))
max_y_limit = 0
for res in fft_results:
    plt.plot(res['freqs'], res['mag'], label=res['file'])
    # find 95th percentile of amplitude (exclude extreme peak)
    y95 = np.percentile(res['mag'], 95)
    if not CUTIT:
        y95=0
    max_y_limit = max(max_y_limit, y95)

plt.xlabel("Frequency (Hz)")
plt.ylabel("Amplitude")
plt.title("FFT of selected sections (all files)")
plt.legend()
plt.grid(True)
plt.ylim(0, max_y_limit)  # scale y-axis to 95th percentile
plt.show()
