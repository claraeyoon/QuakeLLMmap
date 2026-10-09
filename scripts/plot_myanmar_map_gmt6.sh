#!/bin/bash
set -euo pipefail

gmt gmtset FORMAT_GEO_MAP D 
#gmt gmtset LABEL_FONT_SIZE 12p
gmt gmtset FONT_ANNOT 12p

# ── Inputs ──────────────────────────────────────────────────────────────────
DATA_DIR="../data/myanmar"
#INPUT_FILE="./assets/records.txt"
#INPUT_FILE="./assets/records_mmi_gemini_ai.txt"
INPUT_FILE="${DATA_DIR}/records_mmi_gemini_ai.txt"
#FAULT_FILE="./assets/rupture_finite_fault_myanmar.csv"
FAULT_FILE="${DATA_DIR}/rupture_finite_fault_myanmar.csv"
#STATION_FILE="./assets/stations.txt"
#STATION_FILE="./assets/stations_myanmar.txt"
STATION_FILE="${DATA_DIR}/stations_myanmar.txt"
#INTERPOLATE_FILE="./assets/DYFI_city_points.txt"
#INTERPOLATE_FILE="./assets/DYFI_geo_1km.txt"
INTERPOLATE_FILE="${DATA_DIR}/DYFI_geo_1km.txt"
#CITY_FILE="./assets/cities_myanmar.txt"
CITY_FILE="${DATA_DIR}/cities_myanmar.txt"
#CPT_FILE="./assets/shake.cpt"
CPT_FILE="../server/assets/shake.cpt"
#CPT_TOPO_FILE="./assets/GMT_globe_mod.cpt"
CPT_TOPO_FILE="../data/GMT_globe_mod.cpt"

# ── Outputs ─────────────────────────────────────────────────────────────────
#OUT_DIR="./assets"
OUT_DIR="../plots/myanmar"
#MAP_NAME="map_mmi_mandalay"          # gmt figure basename (no extension)
MAP_NAME=${OUT_DIR}/map_mmi_mandalay

# ── Work files (temporary, cleaned up automatically) ────────────────────────
#BLOCKMEAN_FILE="$(mktemp -t blockmean_XXXX.txt)"
#GRID_FILE="$(mktemp -t mmi_surface_XXXX.nc)"
#trap 'rm -f "$BLOCKMEAN_FILE" "$GRID_FILE"' EXIT

#BOUNDS="-R92.39/98.7/13.59/25.88"
BOUNDS="-R91/103/13/27"
PROJECTION="-JM9"
BLOCKMEAN_FILE=${OUT_DIR}/blockmean_full.txt
GRID_FILE=${OUT_DIR}/mmi_surface_full.txt

# ZOOMIN
ZBOUNDS="-R93/99/16/26"
ZPROJECTION="-JM10"
#MAP_ZNAME="map_zoom_mmi_mandalay"          # gmt figure basename (no extension)
MAP_ZNAME=${OUT_DIR}/map_zoom_mmi_mandalay
BLOCKMEAN_ZFILE=${OUT_DIR}/blockmean_zoom.txt
GRID_ZFILE=${OUT_DIR}/mmi_surface_zoom.txt

# DETAIL_MANDALAY_ZOOMIN
ZDMBOUNDS="-R95.5/96.5/21.3/22.3"
ZDMPROJECTION="-JM10"
MAP_ZDMNAME=${OUT_DIR}/map_zoom_mmi_detail_mandalay

# DETAIL_NAYPYIDAW_ZOOMIN
ZDNBOUNDS="-R95.7/96.7/19.2/20.2"
ZDNPROJECTION="-JM10"
MAP_ZDNNAME=${OUT_DIR}/map_zoom_mmi_detail_naypyidaw

# Cut topography file
#gmt grdcut @earth_relief_01m $BOUNDS -G${OUT_DIR}/myanmar_topo_01m.nc -V 
#gmt grdcut @earth_relief_01s $ZDMBOUNDS -G${OUT_DIR}/myanmar_topo_zdm_01s.nc -V 
#gmt grdcut @earth_relief_01s $ZDNBOUNDS -G${OUT_DIR}/myanmar_topo_zdn_01s.nc -V 

# ── Modern mode session ──────────────────────────────────────────────────────
#gmt begin "$MAP_NAME" png
gmt begin "$MAP_NAME"
    gmt set FONT_TITLE 14p,Helvetica-Bold MAP_FRAME_TYPE plain

    # Grid the DYFI intensity points onto a regular surface
#    gmt blockmean "$INTERPOLATE_FILE" $BOUNDS -I2m > "$BLOCKMEAN_FILE"
#    gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I2m $BOUNDS -T0.35
    awk '{print $1, $2, $3}' ${INTERPOLATE_FILE} | gmt blockmean $BOUNDS -I1m > "$BLOCKMEAN_FILE"
    gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I1m $BOUNDS -T0.35

    # Base map + title
#    gmt basemap $BOUNDS $PROJECTION -Bxa1f0.5 -Bya1f0.5 -B+t"Mandalay, Myanmar Earthquake Map"
    gmt basemap $BOUNDS $PROJECTION -Bxa1f1 -Bya1f1 #-B+t"Mandalay, Myanmar Earthquake Map"

    # Shaded MMI surface
    gmt grdimage "$GRID_FILE" -C"$CPT_FILE" $BOUNDS $PROJECTION

    # Plot topography
    gmt grdimage $BOUNDS $PROJECTION ${OUT_DIR}/myanmar_topo_01m.nc -I+a45+nt0.25 -t70 -C"$CPT_TOPO_FILE"

    # Coastline / political borders
    gmt coast $BOUNDS $PROJECTION -Dh -W0.5p,black -Slightblue -Na/0.5p,gray -Lg94/14+c98/14+w500+f+lkm
    
    # Cities
    gmt plot "$CITY_FILE" $BOUNDS $PROJECTION -Ss0.4c -G0 -W0.25p,black
    gmt text "$CITY_FILE" $BOUNDS $PROJECTION -D0.6/-0.3 -F+f9p,Helvetica,black

    # Countries
    gmt text $BOUNDS $PROJECTION -D0/0  -F+f8p,Helvetica-Oblique,black << EOF
92 26 INDIA
96 24 MYANMAR
96 23.5 (BURMA)
101 24 CHINA
102 20 LAOS
101 16 THAILAND
EOF

    # Zoom box
    gmt plot $BOUNDS $PROJECTION -W0.5,black,- << EOF
99 26
99 16
93 16
93 26
99 26
EOF

    # Finite fault rupture
    gmt plot "$FAULT_FILE" $BOUNDS $PROJECTION -W1.5p,black

    # Epicenter
    gmt plot $BOUNDS $PROJECTION -Sa0.5c -W1p,black -Gblack << EOF
95.936 22.011 10
EOF

    # Point observations (circles) and seismic stations (triangles)
#    gmt plot "$INPUT_FILE" $BOUNDS $PROJECTION -Sc0.45c -C"$CPT_FILE" -W0.25p,black
#    gmt plot "$STATION_FILE" $BOUNDS $PROJECTION -St0.6c -C"$CPT_FILE" -W0.5p,black -h1
    gmt plot "$STATION_FILE" $BOUNDS $PROJECTION -Si0.4c -C"$CPT_FILE" -W0.5p,black
    awk '{print $1, $2, $4}' "$STATION_FILE" | gmt text $BOUNDS $PROJECTION -D0/0.3 -F+f9p,Helvetica,black
    gmt plot "$INPUT_FILE" $BOUNDS $PROJECTION -Sc0.2c -C"$CPT_FILE" -W0.25p,black

    # Color scale
#    gmt colorbar -C"$CPT_FILE" -Dx8c/-1.2c+w10c/0.5c+jTC+h -Bx2+l"MMI"
    gmt colorbar -C"$CPT_FILE" -Dx4c/-1.2c+w8c/0.5c+jTC+h -Bx1+l"MMI" -G1/10 --FONT=18p
gmt end show

## gmt begin/end writes the PNG to the working directory; relocate if needed
#if [ -f "${MAP_NAME}.png" ] && [ "$OUT_DIR" != "." ]; then
#    mv -f "${MAP_NAME}.png" "${OUT_DIR}/${MAP_NAME}.png"
#fi
#echo "✅ Done. PNG map saved as ${OUT_DIR}/${MAP_NAME}.png"

# ── Modern mode session ZOOM MAP  ──────────────────────────────────────────────────────
#gmt begin "$MAP_ZNAME" png
gmt begin "$MAP_ZNAME"
    gmt set FONT_TITLE 14p,Helvetica-Bold MAP_FRAME_TYPE plain

    # Grid the DYFI intensity points onto a regular surface
#    awk '{print $1, $2, $3}' ${INTERPOLATE_FILE} | gmt blockmean $ZBOUNDS -I1m > "$BLOCKMEAN_FILE"
#    gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I1m $ZBOUNDS -T0.35
    awk '{print $1, $2, $3}' ${INTERPOLATE_FILE} | gmt blockmean $ZBOUNDS -I1m > "$BLOCKMEAN_ZFILE"
    gmt surface "$BLOCKMEAN_ZFILE" -G"$GRID_ZFILE" -I1m $ZBOUNDS -T0.35

    # Base map + title
    gmt basemap $ZBOUNDS $ZPROJECTION -Bxa1f1 -Bya1f1 #-B+t"Mandalay, Myanmar Earthquake Map"

    # Shaded MMI surface
#    gmt grdimage "$GRID_FILE" -C"$CPT_FILE" $ZBOUNDS $ZPROJECTION
    gmt grdimage "$GRID_ZFILE" -C"$CPT_FILE" $ZBOUNDS $ZPROJECTION

    # Plot topography
    gmt grdimage $ZBOUNDS $ZPROJECTION ${OUT_DIR}/myanmar_topo_01m.nc -I+a45+nt0.25 -t70 -C"$CPT_TOPO_FILE"

    # Coastline / political borders
    gmt coast $ZBOUNDS $ZPROJECTION -Dh -W0.5p,black -Slightblue -Na/0.5p,gray -Lg95/25+c99/25+w300+f+lkm
    
    # Cities
    gmt plot "$CITY_FILE" $ZBOUNDS $ZPROJECTION -Ss0.4c -G0 -W0.25p,black
    gmt text "$CITY_FILE" $ZBOUNDS $ZPROJECTION -D0.6/-0.3 -F+f12p,Helvetica,black

    # Countries
    gmt text $ZBOUNDS $ZPROJECTION -D0/0  -F+f12p,Helvetica-Oblique,black << EOF
92 26 INDIA
96 24 MYANMAR
96 23.5 (BURMA)
101 24 CHINA
102 20 LAOS
101 16 THAILAND
EOF

    # Zoom box
    gmt plot $ZBOUNDS $ZPROJECTION -W1,black,- << EOF
96.5 22.3
96.5 21.3
95.5 21.3
95.5 22.3
96.5 22.3
EOF

    # Zoom box
    gmt plot $ZBOUNDS $ZPROJECTION -W1,black,- << EOF
96.7 20.2
96.7 19.2
95.7 19.2
95.7 20.2
96.7 20.2
EOF

    # Finite fault rupture
    gmt plot "$FAULT_FILE" $ZBOUNDS $ZPROJECTION -W1.5p,black

    # Epicenter
    gmt plot $ZBOUNDS $ZPROJECTION -Sa0.5c -W1p,black -Gblack << EOF
95.936 22.011 10
EOF
    # Point observations (circles) and seismic stations (triangles)
    gmt plot "$STATION_FILE" $ZBOUNDS $ZPROJECTION -Si0.4c -C"$CPT_FILE" -W1.0p,black
    awk '{print $1, $2, $4}' "$STATION_FILE" | gmt text $ZBOUNDS $ZPROJECTION -D0/0.4 -F+f12p,Helvetica,black
    gmt plot "$INPUT_FILE" $ZBOUNDS $ZPROJECTION -Sc0.2c -C"$CPT_FILE" -W1.0p,black

    # Color scale
#    gmt colorbar -C"$CPT_FILE" -Dx4c/-1.2c+w8c/0.5c+jTC+h -Bx1+l"MMI" -G1/10 --FONT=18p
gmt end show

## gmt begin/end writes the PNG to the working directory; relocate if needed
#if [ -f "${MAP_ZNAME}.png" ] && [ "$OUT_DIR" != "." ]; then
#    mv -f "${MAP_ZNAME}.png" "${OUT_DIR}/${MAP_ZNAME}.png"
#fi
#echo "✅ Done. PNG map saved as ${OUT_DIR}/${MAP_ZNAME}.png"

# ── Modern mode session ZOOM MAP DETAIL MANDALAY ──────────────────────────────────────────────────────
gmt begin "$MAP_ZDMNAME"
    gmt set FONT_TITLE 14p,Helvetica-Bold MAP_FRAME_TYPE plain

    # Grid the DYFI intensity points onto a regular surface
#    awk '{print $1, $2, $3}' ${INTERPOLATE_FILE} | gmt blockmean $ZDMBOUNDS -I10s > "$BLOCKMEAN_FILE"
#    gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I10s $ZDMBOUNDS -T0.35

    # Base map + title
    gmt basemap $ZDMBOUNDS $ZDMPROJECTION -Ba0.2f0.1 -BneWS

    # Shaded MMI surface
#    gmt grdimage "$GRID_FILE" -C"$CPT_FILE" $ZDMBOUNDS $ZDMPROJECTION
    gmt grdimage "$GRID_ZFILE" -C"$CPT_FILE" $ZDMBOUNDS $ZDMPROJECTION

    # Plot topography
    gmt grdimage $ZDMBOUNDS $ZDMPROJECTION ${OUT_DIR}/myanmar_topo_zdm_01s.nc -I+a45+nt0.25 -t70 -C"$CPT_TOPO_FILE"

    # Coastline / political borders
    gmt coast $ZDMBOUNDS $ZDMPROJECTION -Dh -W0.5p,black -Slightblue -Na/0.5p,gray -Lg95.8/21.4+c96.2/21.4+w50+f+lkm
    
    # Cities
    gmt plot "$CITY_FILE" $ZDMBOUNDS $ZDMPROJECTION -Ss0.4c -G0 -W0.25p,black
    gmt text "$CITY_FILE" $ZDMBOUNDS $ZDMPROJECTION -D0.6/-0.3 -F+f12p,Helvetica,black

    # Finite fault rupture
    gmt plot "$FAULT_FILE" $ZDMBOUNDS $ZDMPROJECTION -W1.5p,black

    # Epicenter
    gmt plot $ZDMBOUNDS $ZDMPROJECTION -Sa0.5c -W1p,black -Gblack << EOF
95.936 22.011 10
EOF

    # Plot individual DYFI
    gmt plot "$INTERPOLATE_FILE" $ZDMBOUNDS $ZDMPROJECTION -Sd0.3c -C"$CPT_FILE" -W0.6p,black

    # Point observations (circles) and seismic stations (triangles)
    gmt plot "$STATION_FILE" $ZDMBOUNDS $ZDMPROJECTION -Si0.4c -C"$CPT_FILE" -W1.0p,black
    awk '{print $1, $2, $4}' "$STATION_FILE" | gmt text $ZDMBOUNDS $ZDMPROJECTION -D0/0.4 -F+f12p,Helvetica,black
    gmt plot "$INPUT_FILE" $ZDMBOUNDS $ZDMPROJECTION -Sc0.3c -C"$CPT_FILE" -W1.0p,black

    # Color scale
#    gmt colorbar -C"$CPT_FILE" -Dx4c/-1.2c+w8c/0.5c+jTC+h -Bx1+l"MMI" -G1/10 --FONT=18p
gmt end show

# ── Modern mode session ZOOM MAP DETAIL NAYPYIDAW ──────────────────────────────────────────────────────
gmt begin "$MAP_ZDNNAME"
    gmt set FONT_TITLE 14p,Helvetica-Bold MAP_FRAME_TYPE plain

    # Grid the DYFI intensity points onto a regular surface
#    awk '{print $1, $2, $3}' ${INTERPOLATE_FILE} | gmt blockmean $ZDNBOUNDS -I10s > "$BLOCKMEAN_FILE"
#    gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I10s $ZDNBOUNDS -T0.35

    # Base map + title
    gmt basemap $ZDNBOUNDS $ZDNPROJECTION -Ba0.2f0.1 -BneWS

    # Shaded MMI surface
#    gmt grdimage "$GRID_FILE" -C"$CPT_FILE" $ZDNBOUNDS $ZDNPROJECTION
    gmt grdimage "$GRID_ZFILE" -C"$CPT_FILE" $ZDNBOUNDS $ZDNPROJECTION

    # Plot topography
    gmt grdimage $ZDNBOUNDS $ZDNPROJECTION ${OUT_DIR}/myanmar_topo_zdn_01s.nc -I+a45+nt0.25 -t70 -C"$CPT_TOPO_FILE"

    # Coastline / political borders
    gmt coast $ZDNBOUNDS $ZDNPROJECTION -Dh -W0.5p,black -Slightblue -Na/0.5p,gray -Lg96.0/19.3+c96.4/19.3+w50+f+lkm
    
    # Cities
    gmt plot "$CITY_FILE" $ZDNBOUNDS $ZDNPROJECTION -Ss0.4c -G0 -W0.25p,black
    gmt text "$CITY_FILE" $ZDNBOUNDS $ZDNPROJECTION -D0.6/-0.3 -F+f12p,Helvetica,black

    # Finite fault rupture
    gmt plot "$FAULT_FILE" $ZDNBOUNDS $ZDNPROJECTION -W1.5p,black

    # Epicenter
    gmt plot $ZDNBOUNDS $ZDNPROJECTION -Sa0.5c -W1p,black -Gblack << EOF
95.936 22.011 10
EOF
    # Plot individual DYFI
    gmt plot "$INTERPOLATE_FILE" $ZDMBOUNDS $ZDMPROJECTION -Sd0.3c -C"$CPT_FILE" -W0.6p,black

    # Point observations (circles) and seismic stations (triangles)
    gmt plot "$STATION_FILE" $ZDNBOUNDS $ZDNPROJECTION -Si0.4c -C"$CPT_FILE" -W1.0p,black
    awk '{print $1, $2, $4}' "$STATION_FILE" | gmt text $ZDNBOUNDS $ZDNPROJECTION -D0/0.4 -F+f12p,Helvetica,black
    gmt plot "$INPUT_FILE" $ZDNBOUNDS $ZDNPROJECTION -Sc0.3c -C"$CPT_FILE" -W1.0p,black

    # Color scale
#    gmt colorbar -C"$CPT_FILE" -Dx4c/-1.2c+w8c/0.5c+jTC+h -Bx1+l"MMI" -G1/10 --FONT=18p
gmt end show

