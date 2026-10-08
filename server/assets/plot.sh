#!/bin/bash

INPUT_FILE="./assets/records.txt"
STATION_FILE="./assets/stations.txt"
BLOCKMEAN_FILE="blockmean.txt"
GRID_FILE="./assets/mmi_surface.nc"
CPT_FILE="./assets/shake.cpt"
PS_FILE="./assets/mmi_mandalay_map.ps"
PNG_FILE="./assets/mmi_mandalay_map.png"
INTERPOLATE_FILE="./assets/DYFI_city_points.txt"
BOUNDS="-R92.39/98.7/13.59/25.88"
PROJECTION="-JM8c"

gmt blockmean "$INTERPOLATE_FILE" $BOUNDS -I2m > "$BLOCKMEAN_FILE"
gmt surface "$BLOCKMEAN_FILE" -G"$GRID_FILE" -I2m $BOUNDS -T0.35
gmt psbasemap $BOUNDS $PROJECTION -Bxa1f0.5 -Bya1f0.5 -B+t"Mandalay, Myanmar Earthquake Map" -K > $PS_FILE
gmt grdimage "$GRID_FILE" -C"$CPT_FILE" $BOUNDS $PROJECTION -O -K >> "$PS_FILE"
gmt pscoast $BOUNDS $PROJECTION -Dh -W0.5p,black -Slightblue -Na/0.25p,gray -O -K >> "$PS_FILE"
gmt psxy "$INPUT_FILE" $BOUNDS $PROJECTION -Sc0.45c -C"$CPT_FILE" -W0.25p,black -O -K >> "$PS_FILE"
gmt psxy "$STATION_FILE" $BOUNDS $PROJECTION -St0.6c -C"$CPT_FILE" -W0.5p,black -h1 -O -K >> "$PS_FILE"
gmt psscale -C"$CPT_FILE" -Dx8c/-1.2c+w10c/0.5c+jTC+h -Bx2+l"MMI" -O >> "$PS_FILE"
gmt psconvert "$PS_FILE" -A1.0c -Tg -P
rm -f "$BLOCKMEAN_FILE" "$GRID_FILE"
echo '✅ Done. PNG map saved as $PNG_FILE'
