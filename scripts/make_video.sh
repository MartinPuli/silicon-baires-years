#!/usr/bin/env bash
# Renderiza los 608 fotogramas de la linea de tiempo y arma el MP4.
#
#   ./scripts/make_video.sh [ruta/a/blender]
#
# Son 608 fotogramas a 1920x1080 con Cycles, el motor que usa la escena de
# upstream. En una Mac M-series da unos 15 s por fotograma: dos horas y media.
# Los PNG no se versionan.
set -euo pipefail

BLENDER="${1:-/Applications/Blender.app/Contents/MacOS/Blender}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLEND="$ROOT/scene_city/city_timeline.blend"
FRAMES="$ROOT/renders/frames"

if [ ! -f "$BLEND" ]; then
  echo "Falta $BLEND. Construilo primero:"
  echo "  ./scripts/fetch_upstream.sh"
  echo "  $BLENDER -b upstream/renders/city.blend -P scripts/timeline_layer.py -- --repo ."
  exit 1
fi

mkdir -p "$FRAMES"

# Ojo: en Blender '//' es relativo al .blend, no al cwd, asi que los fotogramas
# terminarian dentro de scene_city/. La ruta va absoluta.
"$BLENDER" -b "$BLEND" --python-expr "
import bpy
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.cycles.samples = 24
sc.cycles.use_denoising = True
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = '$FRAMES/f_'
bpy.ops.render.render(animation=True)
"

COUNT=$(find "$FRAMES" -name 'f_*.png' | wc -l | tr -d ' ')
echo "Fotogramas renderizados: $COUNT"

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -framerate 24 -i "$FRAMES/f_%04d.png" \
    -c:v libx264 -pix_fmt yuv420p -crf 19 \
    "$ROOT/renders/silicon_baires_years.mp4"
  echo "Video: $ROOT/renders/silicon_baires_years.mp4"
else
  echo "ffmpeg no esta instalado: quedaron los PNG en $FRAMES"
fi
