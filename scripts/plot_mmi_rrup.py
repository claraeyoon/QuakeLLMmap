"""
plot_mmi_vs_rrup.py

Creates a plot of Modified Mercalli Intensity (MMI, linear y-axis) vs.
rupture distance (Rrup, log x-axis) from multiple data sources for the
2025 Mw 7.7 Mandalay, Myanmar earthquake (us7000pn9s):

  1. Gemini AI LLM MMI estimates (records_test.txt)
       columns: longitude latitude intensity rrup_distance
       plotted as large circles

  2. USGS DYFI (Did You Feel It?) macroseismic data points, extracted from
     stationlist.json where station_type == "macroseismic"
       plotted as small diamonds

  3. Instrumental seismic stations, extracted from stationlist.json where
     station_type == "seismic"
       plotted as triangles

  4. ShakeMap GMPE attenuation curve (soil conditions), from
     attenuation_curves.json -> gmpe.soil.MMI.mean, plotted against the
     corresponding distances.rrup array
       plotted as a continuous line, colored along its length by MMI

All markers (and the attenuation curve) are colored according to the
ShakeMap "shake.cpt" GMT color palette table, so colors are consistent
with the companion GMT shake maps.

Output: MMI vs. Rrup plot as a PDF (mmi_vs_rrup.pdf)
"""

import json
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
#from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.colors import ListedColormap, BoundaryNorm, Normalize, LinearSegmentedColormap
from matplotlib.collections import LineCollection
from matplotlib.cm import ScalarMappable
from matplotlib import rcParams
from pathlib import Path

rcParams.update({'font.size': 16})
rcParams['font.sans-serif'] = "Helvetica"
rcParams['font.family'] = "sans-serif"

def parse_cpt(filepath):
    """
    Parse a GMT-style .cpt color palette file with discrete MMI bins, e.g.:

        0    0 0 0     1    255 255 255
        1    255 255 255  2    191 204 255
        ...
        B    255 255 255
        F    255 255 255

    Each data line defines a color segment: z_low r g b z_high r g b.
    This function extracts the segment boundaries and the RGB color
    associated with each segment (using the z_low color, matching GMT's
    default "hard" discrete color behavior for ShakeMap CPTs).

    Returns
    -------
    boundaries : (N+1,) array of the N+1 bin edges (z values)
    cmap       : matplotlib ListedColormap with N colors
    norm       : matplotlib BoundaryNorm mapping z-values to color indices
    """
    boundaries = []
    colors = []

    with open(filepath, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip background/foreground/NaN special lines (B, F, N)
            if stripped[0] in ("B", "F", "N"):
                continue

            parts = stripped.split()
            if len(parts) < 8:
                continue

            z_low = float(parts[0])
            r_low, g_low, b_low = map(int, parts[1:4])
            z_high = float(parts[4])
            # r_high, g_high, b_high = map(int, parts[5:8])  # unused (hard discrete)

            if not boundaries:
                boundaries.append(z_low)
            boundaries.append(z_high)
            colors.append((r_low / 255.0, g_low / 255.0, b_low / 255.0))

    boundaries = np.array(boundaries)

    # Discrete colormap/norm -- used for actual marker/line colors so they
    # stay consistent with the GMT map's discrete MMI bins.
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(boundaries, cmap.N)

    # Continuous colormap -- used ONLY for a smooth-looking colorbar.
    # Anchor each bin's color at its bin center, then let matplotlib
    # linearly interpolate between them.
    bin_centers = (boundaries[:-1] + boundaries[1:]) / 2.0
    z_min, z_max = boundaries[0], boundaries[-1]
    positions = (bin_centers - z_min) / (z_max - z_min)

    # LinearSegmentedColormap.from_list needs positions in [0, 1] with the
    # first/last anchored there; clip endpoints defensively.
    positions[0] = 0.0
    positions[-1] = 1.0

    smooth_cmap = LinearSegmentedColormap.from_list(
       "shake_smooth", list(zip(positions, colors))
    )
    smooth_norm = Normalize(vmin=z_min, vmax=z_max)

    return boundaries, cmap, norm, smooth_cmap, smooth_norm
#    return np.array(boundaries), cmap, norm


def read_records_file(filepath):
    """
    Read records_test.txt: whitespace-delimited columns
        longitude latitude intensity rrup_distance
    Returns (rrup_array, mmi_array).
    """
    lons, lats, mmis, rrups = [], [], [], []
    with open(filepath, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 4:
                continue
            lon, lat, mmi, rrup = map(float, parts[:4])
            lons.append(lon)
            lats.append(lat)
            mmis.append(mmi)
            rrups.append(rrup)
    return np.array(rrups), np.array(mmis)


def _to_float_or_none(value):
    """
    Safely coerce a value to float. Returns None if the value is missing,
    the literal string "null" (common in ShakeMap stationlist JSON for
    unavailable fields), or otherwise not convertible.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == "null":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_stationlist(filepath):
    """
    Read a ShakeMap stationlist.json file and split stations into DYFI
    macroseismic points and instrumental seismic stations.

    Handles stationlist files where 'intensity' or distance fields are
    strings, missing, or the literal string "null" (all observed in real
    ShakeMap stationlist.json output) by skipping any station that lacks
    a valid numeric intensity and rrup.

    Returns dict with keys 'dyfi' and 'seismic', each mapping to
    (rrup_array, mmi_array).
    """
    with open(filepath, "r") as f:
        data = json.load(f)

    dyfi_rrup, dyfi_mmi = [], []
    seismic_rrup, seismic_mmi = [], []
    skipped = 0

    for feature in data["features"]:
        props = feature["properties"]
        station_type = props.get("station_type")
        intensity = _to_float_or_none(props.get("intensity"))
        rrup = _to_float_or_none(props.get("distances", {}).get("rrup"))

        if intensity is None or rrup is None:
            skipped += 1
            continue

        if station_type == "macroseismic":
            dyfi_rrup.append(rrup)
            dyfi_mmi.append(intensity)
        elif station_type == "seismic":
            seismic_rrup.append(rrup)
            seismic_mmi.append(intensity)

    if skipped:
        print(f"Note: skipped {skipped} station(s) with missing/invalid intensity or rrup.")

    return {
        "dyfi": (np.array(dyfi_rrup, dtype=float), np.array(dyfi_mmi, dtype=float)),
        "seismic": (np.array(seismic_rrup, dtype=float), np.array(seismic_mmi, dtype=float)),
    }


def read_attenuation_curve(filepath, site_condition="soil"):
    """
    Read attenuation_curves.json and extract the MMI mean attenuation
    curve for the given site condition ("soil" or "rock"), along with
    the corresponding Rrup distance array.

    Returns (rrup_array, mmi_mean_array).
    """
    with open(filepath, "r") as f:
        data = json.load(f)

    mmi_mean = np.array(data["gmpe"][site_condition]["MMI"]["mean"])
    rrup = np.array(data["distances"]["rrup"])

    if len(mmi_mean) != len(rrup):
        raise ValueError(
            f"Length mismatch: MMI mean array ({len(mmi_mean)}) vs. "
            f"rrup distance array ({len(rrup)}). Cannot pair reliably."
        )

    return rrup, mmi_mean


def colored_line_segments(x, y, cmap, norm):
    """
    Build a LineCollection for a curve whose color varies along its length
    according to its y-value (MMI), using the given cmap/norm.
    """
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    # Color each segment by the average MMI of its two endpoints
    seg_values = (y[:-1] + y[1:]) / 2.0
    lc = LineCollection(segments, cmap=cmap, norm=norm)
    lc.set_array(seg_values)
    lc.set_linewidth(2.2)
    return lc


def make_plot(records_file, stationlist_file, attenuation_file, cpt_file,
              output_file="mmi_vs_rrup.pdf", event_id=None):

#    boundaries, cmap, norm = parse_cpt(cpt_file)
    boundaries, cmap, norm, smooth_cmap, smooth_norm = parse_cpt(cpt_file)
    print(cmap)
    print(norm)

#    fig, ax = plt.subplots(figsize=(8, 6))
    fig, ax = plt.subplots(figsize=(12, 6))

#    # ── 1. GMPE attenuation curve (soil), colored along its length ──────
#    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "soil")
#    order = np.argsort(curve_rrup)
#    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
#    ax.plot(curve_rrup, curve_mmi, color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

#    lc = colored_line_segments(curve_rrup, curve_mmi, cmap, norm)
#    ax.add_collection(lc)
#    # Add an invisible plot handle for the legend (LineCollection doesn't
#    # auto-populate the legend the way Line2D does)
#    ax.plot([], [], color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

    # ── 2. Gemini AI LLM MMI estimates ───────────────────────────────────
    ai_rrup, ai_mmi = read_records_file(records_file)
    ax.scatter(
        ai_rrup, ai_mmi,
#        s=160, c=ai_mmi, cmap=cmap, norm=norm,
        s=50, c=ai_mmi, cmap=cmap, norm=norm,
        edgecolors="black", linewidths=1.0,
        marker="o", zorder=3, label="Gemini AI LLM estimate"
    )

    # ── 3. DYFI and instrumental stations from stationlist.json ─────────
    stations = read_stationlist(stationlist_file)

    dyfi_rrup, dyfi_mmi = stations["dyfi"]
    if len(dyfi_rrup):
        ax.scatter(
            dyfi_rrup, dyfi_mmi,
            s=20, c=dyfi_mmi, cmap=cmap, norm=norm,
            edgecolors="black", linewidths=0.5,
            marker="D", zorder=4, label="DYFI (macroseismic)"
        )

    seismic_rrup, seismic_mmi = stations["seismic"]
    if len(seismic_rrup):
        ax.scatter(
            seismic_rrup, seismic_mmi,
            s=100, c=seismic_mmi, cmap=cmap, norm=norm,
            edgecolors="black", linewidths=2.0,
            marker="^", zorder=4, label="Instrumental station"
        )

    # ── 1. GMPE attenuation curve (soil), colored along its length ──────
    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "soil")
    order = np.argsort(curve_rrup)
    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
    ax.plot(curve_rrup, curve_mmi, color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

    # ── 1. GMPE attenuation curve (rock), colored along its length ──────
    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "rock")
    order = np.argsort(curve_rrup)
    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
    ax.plot(curve_rrup, curve_mmi, color="brown", linewidth=2.2, label="ShakeMap GMPE (rock)")

    # ── Axes formatting ───────────────────────────────────────────────────
    ax.set_xscale("log")
    ax.set_ylabel("MMI")
    ax.set_xlabel(r"$R_{rup}$ nearest distance to fault rupture (km)")
    ax.set_ylim(0, 11)

    # Set x-limits to cover all plotted data with a little padding
    all_rrup = np.concatenate([
        curve_rrup, ai_rrup,
        dyfi_rrup if len(dyfi_rrup) else np.array([]),
        seismic_rrup if len(seismic_rrup) else np.array([]),
    ])
    all_rrup = all_rrup[all_rrup > 0]
    if len(all_rrup):
        ax.set_xlim(all_rrup.min() * 0.7, all_rrup.max() * 1.3)

#    title = "MMI vs. Rupture Distance"
#    if event_id:
#        title += f" — {event_id}"
#    ax.set_title(title)

    ax.grid(True, which="both", linestyle="--", linewidth=0.4, alpha=0.6)
#    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax.legend(loc="lower center", fontsize=12, framealpha=0.9)

    # Shared colorbar for the shake.cpt MMI scale
    sm = ScalarMappable(cmap=cmap, norm=norm)
#    sm = ScalarMappable(cmap=smooth_cmap, norm=smooth_norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, boundaries=boundaries)
#    cbar = fig.colorbar(sm, ax=ax, pad=0.02)
    midpoints = [(boundaries[i] + boundaries[i+1]) / 2 for i in range(len(boundaries)-1)]
    labels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    sm.set_clim(0.5, 10.5)
    cbar.set_label("MMI")
    cbar.set_ticks(midpoints)
    cbar.set_ticklabels(labels)

    fig.tight_layout()
    fig.savefig(output_file, format="pdf")
    print(f"Saved plot to {output_file}")

    return fig, ax


def make_orig_plot(records_file, stationlist_file, attenuation_file, cpt_file,
              output_file, event_id=None):

#    boundaries, cmap, norm = parse_cpt(cpt_file)
    boundaries, cmap, norm, smooth_cmap, smooth_norm = parse_cpt(cpt_file)

    fig, ax = plt.subplots(figsize=(8, 6))

#    # ── 1. GMPE attenuation curve (soil), colored along its length ──────
#    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "soil")
#    order = np.argsort(curve_rrup)
#    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
#    ax.plot(curve_rrup, curve_mmi, color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

#    lc = colored_line_segments(curve_rrup, curve_mmi, cmap, norm)
#    ax.add_collection(lc)
#    # Add an invisible plot handle for the legend (LineCollection doesn't
#    # auto-populate the legend the way Line2D does)
#    ax.plot([], [], color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

#    # ── 2. Gemini AI LLM MMI estimates ───────────────────────────────────
#    ai_rrup, ai_mmi = read_records_file(records_file)
#    ax.scatter(
#        ai_rrup, ai_mmi,
##        s=160, c=ai_mmi, cmap=cmap, norm=norm,
#        s=50, c=ai_mmi, cmap=cmap, norm=norm,
#        edgecolors="black", linewidths=1.0,
#        marker="o", zorder=3, label="Gemini AI LLM estimate"
#    )

    # ── 3. DYFI and instrumental stations from stationlist.json ─────────
    stations = read_stationlist(stationlist_file)

    dyfi_rrup, dyfi_mmi = stations["dyfi"]
    if len(dyfi_rrup):
        ax.scatter(
            dyfi_rrup, dyfi_mmi,
            s=20, c=dyfi_mmi, cmap=cmap, norm=norm,
            edgecolors="black", linewidths=0.5,
            marker="D", zorder=4, label="DYFI (macroseismic)"
        )

    seismic_rrup, seismic_mmi = stations["seismic"]
    if len(seismic_rrup):
        ax.scatter(
            seismic_rrup, seismic_mmi,
            s=100, c=seismic_mmi, cmap=cmap, norm=norm,
            edgecolors="black", linewidths=2.0,
            marker="^", zorder=4, label="Instrumental station"
        )

    # ── 1. GMPE attenuation curve (soil), colored along its length ──────
    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "soil")
    order = np.argsort(curve_rrup)
    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
    ax.plot(curve_rrup, curve_mmi, color="gray", linewidth=2.2, label="ShakeMap GMPE (soil)")

    # ── 1. GMPE attenuation curve (rock), colored along its length ──────
    curve_rrup, curve_mmi = read_attenuation_curve(attenuation_file, "rock")
    order = np.argsort(curve_rrup)
    curve_rrup, curve_mmi = curve_rrup[order], curve_mmi[order]
    ax.plot(curve_rrup, curve_mmi, color="brown", linewidth=2.2, label="ShakeMap GMPE (rock)")

    # ── Axes formatting ───────────────────────────────────────────────────
    ax.set_xscale("log")
    ax.set_ylabel("MMI")
    ax.set_xlabel(r"$R_{rup}$ nearest distance to fault rupture (km)")
    ax.set_ylim(0, 11)

    # Set x-limits to cover all plotted data with a little padding
    all_rrup = np.concatenate([
        curve_rrup, 
        dyfi_rrup if len(dyfi_rrup) else np.array([]),
        seismic_rrup if len(seismic_rrup) else np.array([]),
    ])
    all_rrup = all_rrup[all_rrup > 0]
    if len(all_rrup):
        ax.set_xlim(1, 2000)
#        ax.set_xlim(all_rrup.min() * 0.7, all_rrup.max() * 1.3)

#    title = "MMI vs. Rupture Distance"
#    if event_id:
#        title += f" — {event_id}"
#    ax.set_title(title)

    ax.grid(True, which="both", linestyle="--", linewidth=0.4, alpha=0.6)
#    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax.legend(loc="lower center", fontsize=12, framealpha=0.9)

    # Shared colorbar for the shake.cpt MMI scale
#    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    sm = ScalarMappable(cmap=cmap, norm=norm)
#    sm = ScalarMappable(cmap=smooth_cmap, norm=smooth_norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, boundaries=boundaries)
#    cbar = fig.colorbar(sm, ax=ax, pad=0.02)
    midpoints = [(boundaries[i] + boundaries[i+1]) / 2 for i in range(len(boundaries)-1)]
    labels = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    sm.set_clim(0.5, 10.5)
    cbar.set_label("MMI")
    cbar.set_ticks(midpoints)
    cbar.set_ticklabels(labels)

    fig.tight_layout()
    fig.savefig(output_file, format="pdf")
    print(f"Saved plot to {output_file}")

    return fig, ax


def main():
    parser = argparse.ArgumentParser(
        description="Plot MMI (linear) vs. Rrup (log) from multiple earthquake intensity data sources, colored by shake.cpt."
    )
    parser.add_argument(
        "--records", default="records_test.txt",
        help="Path to AI LLM records file (lon lat intensity rrup) (default: records_test.txt)"
    )
    parser.add_argument(
        "--stationlist", default="stationlist_test.json",
        help="Path to ShakeMap stationlist.json (default: stationlist_test.json)"
    )
    parser.add_argument(
        "--attenuation", default="attenuation_curves.json",
        help="Path to ShakeMap attenuation_curves.json (default: attenuation_curves.json)"
    )
    parser.add_argument(
        "--cpt", default="shake.cpt",
        help="Path to GMT shake.cpt color palette file (default: shake.cpt)"
    )
    parser.add_argument(
        "--output", default="mmi_vs_rrup.pdf",
        help="Output PDF file path (default: mmi_vs_rrup.pdf)"
    )
    parser.add_argument(
        "--event-id", default=None,
        help="Optional event ID string to include in plot title"
    )
    args = parser.parse_args()

    make_plot(
        records_file=args.records,
        stationlist_file=args.stationlist,
        attenuation_file=args.attenuation,
        cpt_file=args.cpt,
        output_file=args.output,
        event_id=args.event_id,
    )

    output_file_path = Path(args.output)
    added_chars = "_orig"
    orig_output_file = output_file_path.with_stem(f"{output_file_path.stem}{added_chars}")
    make_orig_plot(
        records_file=args.records,
        stationlist_file=args.stationlist,
        attenuation_file=args.attenuation,
        cpt_file=args.cpt,
        output_file=orig_output_file,
        event_id=args.event_id,
    )


if __name__ == "__main__":
    main()
