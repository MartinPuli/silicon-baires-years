#!/usr/bin/env bash
# Trae la ciudad de Aerolab/silicon-baires, que es la base de esta pieza.
#
#   ./scripts/fetch_upstream.sh
#
# No está vendorizada a proposito: es el repo de otro y se clona fijado a un
# commit, asi que lo que hay aca adentro es solo la capa de tiempo. Lo que se
# usa de upstream son dos archivos:
#
#   upstream/renders/city.blend        la ciudad construida (20 MB)
#   upstream/renders/city_signs.json   que marca esta en que cartel
set -euo pipefail

COMMIT="963da3133d7cfd7cc30239cb57dca2696067d242"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/upstream"

if [ -d "$DEST/.git" ]; then
  echo "upstream/ ya existe; fijando el commit"
  git -C "$DEST" fetch --quiet origin "$COMMIT" || git -C "$DEST" fetch --quiet
  git -C "$DEST" checkout --quiet "$COMMIT"
else
  git clone --quiet https://github.com/Aerolab/silicon-baires.git "$DEST"
  git -C "$DEST" checkout --quiet "$COMMIT"
fi

for f in renders/city.blend renders/city_signs.json; do
  if [ ! -f "$DEST/$f" ]; then
    echo "Falta $DEST/$f — upstream cambió de estructura; revisa el commit fijado."
    exit 1
  fi
done

echo "upstream listo en $COMMIT"
echo "Ahora:  blender -b upstream/renders/city.blend -P scripts/timeline_layer.py -- --repo ."
