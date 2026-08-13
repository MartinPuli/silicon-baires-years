"""Convierte la ciudad de silicon-baires en una linea de tiempo.

silicon-baires (Aerolab) genera una Buenos Aires isometrica en Blender headless
y le reparte carteles de empresas reales por los techos y las medianeras. Su
pieza es un travelling de 24 segundos: la camara se mueve y la ciudad esta toda
ahi desde el primer fotograma.

Esto invierte las dos cosas. La camara se clava —se congela en el angulo
isometrico de su plano de apertura, recentrada para que entre la ciudad
entera— y lo que se mueve es el ano: cada cartel de empresa con ano de
fundacion citable arranca apagado y se prende en su ano. El transito y la
gente de la escena original siguen animados, asi que la ciudad esta viva
mientras el ecosistema se va llenando.

No se toca nada de la geometria de upstream: se lee su .blend, se le suma esta
capa y se guarda una copia aparte.

Uso:
    blender -b upstream/renders/city.blend \
        -P scripts/timeline_layer.py -- --repo .
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

YEAR_START = 1995     # Technisys, la mas vieja de la tabla con ano citable
YEAR_END = 2026
FRAMES_PER_YEAR = 19  # 32 anos * 19 = 608, y el .blend de upstream llega a 624

TAG = "TL_"

# La camara de upstream hace un travelling: sale de un plano ancho y termina
# cerrada sobre el titulo. Se congela en el ANGULO del fotograma 1 (el mas
# abierto) y se recentra sobre la ciudad, porque el encuadre final lo ocupan
# las letras rojas de BUENOS AIRES y aca lo que hay que ver son los carteles.
FREEZE_FRAME = 1
MARGIN = 1.22         # aire alrededor de la caja de los carteles con ano
# Topes del encuadre. Abajo, el plano de apertura de upstream (306), que es lo
# mas cerrado que se puede estar y seguir viendo varias marcas. Arriba, el
# punto donde la ciudad empieza a ser una isla en el fondo y los logos dejan
# de leerse.
ORTHO_MIN = 306.0
ORTHO_MAX = 620.0


def argv_after_ddash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def repo_root():
    args = argv_after_ddash()
    if "--repo" in args:
        return os.path.abspath(args[args.index("--repo") + 1])
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def year_to_frame(year):
    return int(round((year - YEAR_START) * FRAMES_PER_YEAR)) + 1


def purge_previous():
    for obj in [o for o in bpy.data.objects if o.name.startswith(TAG)]:
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in [c for c in bpy.data.collections if c.name.startswith(TAG)]:
        bpy.data.collections.remove(coll)
    for mat in [m for m in bpy.data.materials if m.name.startswith(TAG)]:
        bpy.data.materials.remove(mat)
    for curve in [c for c in bpy.data.curves if c.name.startswith(TAG)]:
        bpy.data.curves.remove(curve)


def emission_material(name, rgb, strength):
    mat = bpy.data.materials.new(TAG + name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    emit.inputs["Strength"].default_value = strength
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def set_key_interpolation(kind):
    """Blender 5 saco Action.fcurves (acciones con slots y capas), asi que la
    interpolacion se fija en las preferencias ANTES de insertar en vez de
    recorrer las curvas despues."""
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def keyframe_visible_from(obj, frame_in):
    set_key_interpolation("CONSTANT")
    for prop in ("hide_viewport", "hide_render"):
        setattr(obj, prop, True)
        obj.keyframe_insert(prop, frame=1)
        obj.keyframe_insert(prop, frame=max(1, frame_in - 1))
        setattr(obj, prop, False)
        obj.keyframe_insert(prop, frame=frame_in)


def keyframe_visible_range(obj, frame_in, frame_out):
    set_key_interpolation("CONSTANT")
    for prop in ("hide_viewport", "hide_render"):
        setattr(obj, prop, True)
        obj.keyframe_insert(prop, frame=max(1, frame_in - 1))
        setattr(obj, prop, False)
        obj.keyframe_insert(prop, frame=frame_in)
        setattr(obj, prop, True)
        obj.keyframe_insert(prop, frame=frame_out)


# ---------------------------------------------------------------------------


def extent_in_camera_plane(cam, objects):
    """Caja de esos objetos medida en el plano de la camara, no en el mundo.

    Un bounding box alineado a los ejes del mundo no dice nada sobre cuanto
    ortho_scale hace falta: lo que importa es cuanto ocupan sobre los ejes
    derecha/arriba de ESTA camara.
    """
    basis = cam.matrix_world.to_3x3()
    right, up = basis @ Vector((1, 0, 0)), basis @ Vector((0, 1, 0))
    us, vs = [], []
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            us.append(world.dot(right))
            vs.append(world.dot(up))
    return right, up, min(us), max(us), min(vs), max(vs)


def freeze_camera(scene, report, subjects):
    """Le saca la animacion a la camara y la deja mirando la ciudad entera.

    Hay DOS animaciones que sacar: la del objeto (posicion) y la del dato de
    camara (ortho_scale, que en upstream va de 306 a 170). Borrar solo la del
    objeto deja la camara quieta pero el encuadre siguiendo haciendo zoom, que
    es justo lo que esta pieza no quiere.
    """
    cam = scene.camera
    scene.frame_set(FREEZE_FRAME)
    rotation = cam.rotation_euler.copy()
    location = cam.location.copy()

    cam.animation_data_clear()
    if cam.data.animation_data:
        cam.data.animation_data_clear()
    cam.rotation_euler = rotation
    cam.location = location

    # El encuadre se calcula sobre los carteles QUE TIENEN ANO, no sobre la
    # ciudad entera: encuadrar la ciudad completa la deja como una isla chica
    # en medio del fondo y no se lee ni un logo, que es justo lo que la pieza
    # tiene para mostrar.
    right, up, u0, u1, v0, v1 = extent_in_camera_plane(cam, subjects)
    width, height = u1 - u0, v1 - v0
    aspect = scene.render.resolution_x / scene.render.resolution_y
    # ortho_scale es la dimension MAYOR del encuadre, asi que hay que cubrir
    # tanto el ancho como la altura convertida a ancho equivalente.
    fitted = max(width, height * aspect) * MARGIN
    cam.data.ortho_scale = max(ORTHO_MIN, min(ORTHO_MAX, fitted))

    # Recentrar: correr la camara sobre su propio plano hasta que el centro de
    # la ciudad caiga en el centro del cuadro.
    target_u, target_v = (u0 + u1) * 0.5, (v0 + v1) * 0.5
    cam.location = (location
                    + right * (target_u - location.dot(right))
                    + up * (target_v - location.dot(up)))

    report["camera"] = {
        "congelada_en_frame": FREEZE_FRAME,
        "location": [round(v, 1) for v in cam.location],
        "rotation_deg": [round(math.degrees(v), 2) for v in cam.rotation_euler],
        "ortho_scale": round(cam.data.ortho_scale, 1),
        "ciudad_ancho_m": round(width, 1),
        "ciudad_alto_m": round(height, 1),
        "keyframes": 0,
        "nota": "Se limpio la animacion del objeto Y la del dato de camara "
                "(upstream anima ortho_scale de 306 a 170).",
    }
    return cam


def hitos_de(info):
    """`hito` puede venir como texto o como lista. Devuelve siempre lista."""
    hito = info.get("hito")
    if not hito:
        return []
    return [hito] if isinstance(hito, str) else list(hito)


def hito_year(text):
    head = text.split(":", 1)[0].strip()
    return int(head) if head.isdigit() else None


# Que fraccion de su altura tiene el edificio el dia que la empresa se funda.
# El resto lo gana creciendo.
SEED_HEIGHT = 0.42
# Si la empresa no tiene hitos con fecha, tarda esto en llegar a su altura.
DEFAULT_GROWTH_YEARS = 7


def growth_steps(founded, info):
    """Los escalones de altura del edificio, de la fundacion a su tamano final.

    El edificio NO aparece entero: nace chico y va subiendo. Los escalones caen
    en los hitos con fecha de la empresa (salidas a bolsa, rondas, compras),
    que es lo unico documentado que tenemos para las veintidos por igual. NO es
    una curva de valuacion: no hay valuaciones comparables para todas, y
    fabricar uma seria inventar el dato.

    Sin hitos, el edificio crece parejo durante DEFAULT_GROWTH_YEARS.
    """
    years = sorted({y for y in (hito_year(h) for h in hitos_de(info))
                    if y and y > founded})
    if not years:
        years = [founded + DEFAULT_GROWTH_YEARS]
    span = 1.0 - SEED_HEIGHT
    steps = [(founded, SEED_HEIGHT)]
    for index, year in enumerate(years, start=1):
        steps.append((year, SEED_HEIGHT + span * index / len(years)))
    return steps


def site_index(root):
    """Los 126 sitios de upstream, indexados por su coordenada.

    city_buildings.json trae, por cada edificio, su punto 'at', su altura 'top'
    y los rectangulos 'wings' que lo componen. El campo 'owner' de cada cartel
    es exactamente ese 'at', asi que la marca se puede atar a su edificio sin
    adivinar nada.
    """
    with open(os.path.join(root, "upstream", "renders", "city_buildings.json"),
              encoding="utf-8") as fh:
        return json.load(fh)["sites"]


def site_for_owner(sites, owner):
    """Encuentra el sitio al que pertenece el 'owner' de un cartel.

    NO se puede matchear por igualdad: el 'owner' del cartel viene redondeado
    (-26.0, -167.0) y el 'at' del sitio cae en la grilla con decimales
    (-351.75, -327.75). Se busca el sitio cuyo rectangulo contiene el punto, y
    si ninguno lo contiene, el mas cercano dentro de un radio corto.
    """
    ox, oy = owner
    best, best_d = None, 1e18
    for site in sites:
        for wx, wy, ww, wd in site["wings"]:
            if (abs(ox - wx) <= ww * 0.5 + 1.0
                    and abs(oy - wy) <= wd * 0.5 + 1.0):
                return site
        dx, dy = ox - site["at"][0], oy - site["at"][1]
        d = dx * dx + dy * dy
        if d < best_d:
            best, best_d = site, d
    return best if best_d <= 30.0 ** 2 else None


def site_rects(site):
    return [(w[0] - w[2] * 0.5 - 0.6, w[0] + w[2] * 0.5 + 0.6,
             w[1] - w[3] * 0.5 - 0.6, w[1] + w[3] * 0.5 + 0.6)
            for w in site["wings"]]


def split_buildings(city, targets, collection):
    """Separa del mesh unico de la ciudad los edificios que hay que animar.

    upstream une TODA la ciudad en un solo objeto llamado 'buildings', asi que
    no hay nada que escalar por edificio. Se hace con bmesh y NO con
    bpy.ops.mesh.separate: en background el operador depende del contexto y del
    objeto activo, y en una tanda de veintipico separaciones deja de encontrar
    geometria despues de la primera.

    Cada parte nace con su origen en el piso del sitio. Si el origen queda en
    el centro del volumen, escalar en Z hunde media torre bajo tierra en vez de
    hacerla crecer desde el suelo.

    `targets` es [(clave, site)]. Devuelve {clave: objeto}.
    """
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(city.data)
    bm.faces.ensure_lookup_table()

    boxes = [(key, site, site_rects(site), float(site["top"]) + 2.0)
             for key, site in targets]
    claimed = {}
    for face in bm.faces:
        center = face.calc_center_median()
        for key, site, rects, top in boxes:
            if center.z > top:
                continue
            if any(x0 <= center.x <= x1 and y0 <= center.y <= y1
                   for x0, x1, y0, y1 in rects):
                claimed.setdefault(key, []).append(face)
                break

    made = {}
    materials = list(city.data.materials)
    for key, site in targets:
        faces = claimed.get(key)
        if not faces or len(faces) < 4:
            continue
        base = Vector((site["at"][0], site["at"][1], 0.0))
        part_bm = bmesh.new()
        vmap = {}
        for face in faces:
            verts = []
            for vert in face.verts:
                if vert not in vmap:
                    vmap[vert] = part_bm.verts.new(vert.co - base)
                verts.append(vmap[vert])
            try:
                new_face = part_bm.faces.new(verts)
            except ValueError:
                continue          # cara duplicada: la geometria unida las tiene
            new_face.material_index = face.material_index
            new_face.smooth = face.smooth
        mesh = bpy.data.meshes.new(TAG + "bld_" + key)
        part_bm.to_mesh(mesh)
        part_bm.free()
        for material in materials:
            mesh.materials.append(material)
        obj = bpy.data.objects.new(TAG + "bld_" + key, mesh)
        obj.location = base
        collection.objects.link(obj)
        made[key] = obj

    bmesh.ops.delete(
        bm, geom=[f for group in claimed.values() for f in group],
        context="FACES")
    bm.to_mesh(city.data)
    bm.free()
    city.data.update()
    return made


def plan_closed(root, sites, targets, report):
    """Le busca terreno a las empresas que cerraron.

    Ninguna tiene cartel en la ciudad de upstream, asi que se les asigna un
    sitio libre —de los que ningun cartel con ano reclamo— cerca del centro del
    cuadro y con altura suficiente para que se note cuando se cae.
    """
    path = os.path.join(root, "data", "cerraron.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        empresas = json.load(fh)["empresas"]

    taken = {key for key, _ in targets}
    taken_at = {(round(s["at"][0], 2), round(s["at"][1], 2))
                for _, s in targets}
    # El centro del cuadro es el de los sitios que ya reclamaron los carteles
    # con ano: es sobre esa caja que despues se calcula el encuadre.
    if targets:
        focus = Vector((sum(s["at"][0] for _, s in targets) / len(targets),
                        sum(s["at"][1] for _, s in targets) / len(targets)))
    else:
        focus = Vector((0.0, 0.0))
    free = [s for s in sites
            if (round(s["at"][0], 2), round(s["at"][1], 2)) not in taken_at
            and float(s["top"]) >= 18.0]
    free.sort(key=lambda s: (Vector((s["at"][0], s["at"][1])) - focus).length)

    planned = []
    for empresa in empresas:
        if not free:
            report["warnings"].append(
                "sin terreno libre para %s" % empresa["name"])
            continue
        site = free.pop(0)
        key = "cerro_" + empresa["id"]
        if key in taken:
            continue
        targets.append((key, site))
        planned.append((empresa, site, key))
    return planned


def animate_closed(planned, parts, collection, by_year, end_by_year, report):
    """Sube el edificio en el ano de fundacion y lo baja el ano que cerro."""
    grow = int(FRAMES_PER_YEAR * 0.7)
    hechas = []
    for empresa, site, key in planned:
        part = parts.get(key)
        founded, closed = int(empresa["founded"]), int(empresa["closed"])
        frame_in, frame_out = year_to_frame(founded), year_to_frame(closed)

        if part is not None:
            set_key_interpolation("BEZIER")
            part.scale = (1.0, 1.0, 0.001)
            part.keyframe_insert("scale", index=2, frame=1)
            part.keyframe_insert("scale", index=2, frame=frame_in)
            part.scale = (1.0, 1.0, 1.0)
            part.keyframe_insert("scale", index=2, frame=frame_in + grow)
            part.keyframe_insert("scale", index=2, frame=frame_out)
            part.scale = (1.0, 1.0, 0.001)
            part.keyframe_insert("scale", index=2, frame=frame_out + grow)

        # Cartel propio: la ciudad de upstream no trae uno para estas.
        at = (site["at"][0], site["at"][1])
        curve = bpy.data.curves.new(TAG + "cerro_" + empresa["id"], type="FONT")
        curve.body = empresa["name"]
        curve.size = max(7.0, min(13.0, float(site["top"]) * 0.35))
        curve.align_x = "CENTER"
        curve.align_y = "BOTTOM"
        curve.extrude = 0.4
        sign = bpy.data.objects.new(TAG + "cerro_" + empresa["id"], curve)
        sign.location = (at[0], at[1], float(site["top"]) + 1.5)
        # Encarar la camara es copiarle la rotacion: es ortografica, asi que
        # todos los rayos son paralelos y una sola rotacion sirve para todos
        # los carteles, esten donde esten.
        sign.rotation_euler = bpy.context.scene.camera.rotation_euler
        sign.data.materials.append(emission_material(
            "cerro_%s" % empresa["id"], (1.0, 0.30, 0.22), 4.0))
        collection.objects.link(sign)
        keyframe_visible_range(sign, frame_in + grow, frame_out)

        by_year.setdefault(founded, set()).add(empresa["name"])
        end_by_year.setdefault(closed, set()).add(empresa["name"])
        hechas.append({
            "empresa": empresa["name"],
            "founded": founded,
            "closed": closed,
            "como_termino": empresa["como_termino"],
            "edificio": part.name if part else None,
            "sitio": [round(v, 2) for v in site["at"]],
        })
    report["cerraron"] = hechas


def animate_signs(root, scene, report, collection):
    """Cada empresa levanta su edificio en su ano y lo baja cuando deja de ser
    independiente. El cartel se prende cuando el edificio termino de crecer."""
    with open(os.path.join(root, "data", "brand_years.json"),
              encoding="utf-8") as fh:
        table = json.load(fh)["years"]
    with open(os.path.join(root, "upstream", "renders", "city_signs.json"),
              encoding="utf-8") as fh:
        manifest = json.load(fh)
    sites = site_index(root)
    city = bpy.data.objects.get("buildings")

    grow = int(FRAMES_PER_YEAR * 0.7)
    by_year, end_by_year = {}, {}
    animated, missing_objects, sin_ano, objects = [], [], set(), []
    built = 0

    # Primera pasada: que carteles tienen ano y a que sitio pertenecen.
    plan, targets = [], []
    for entry in manifest:
        obj = bpy.data.objects.get(entry["name"])
        brand = entry["text"]
        if obj is None:
            missing_objects.append(entry["name"])
            continue
        info = table.get(brand)
        if info is None:
            # Sin ano citable no se anima: queda en la ciudad desde el primer
            # fotograma, exactamente como la dejo upstream.
            sin_ano.add(brand)
            continue
        key = "%s_%s" % (brand.replace(" ", "_").lower(),
                         entry["name"].split(".")[-1])
        site = site_for_owner(sites, entry["owner"])
        plan.append((entry, obj, info, key, site))
        if site is not None:
            targets.append((key, site))

    # Las que cerraron no tienen cartel en la ciudad de upstream: se les da un
    # terreno libre. Van en la MISMA tanda de bmesh, porque separar el mesh dos
    # veces sobre el mismo objeto duplicaria caras ya sacadas.
    closed = plan_closed(root, sites, targets, report)

    # Segunda pasada: una sola de bmesh para separarlos a todos.
    parts = split_buildings(city, targets, collection) if (
        city is not None and targets) else {}

    for entry, obj, info, key, site in plan:
        brand = entry["text"]
        year = int(info["year"])
        frame_in = year_to_frame(year)
        end_year = info.get("end_year")
        frame_end = year_to_frame(int(end_year)) if end_year else None
        part = parts.get(key)

        if part is not None:
            built += 1
            steps = growth_steps(year, info)
            set_key_interpolation("BEZIER")
            part.scale = (1.0, 1.0, 0.001)
            part.keyframe_insert("scale", index=2, frame=1)
            part.keyframe_insert("scale", index=2, frame=frame_in)
            for step_year, height in steps:
                part.scale = (1.0, 1.0, height)
                part.keyframe_insert(
                    "scale", index=2,
                    frame=year_to_frame(step_year) + grow)
            if frame_end:
                part.keyframe_insert("scale", index=2, frame=frame_end)
                part.scale = (1.0, 1.0, 0.001)
                part.keyframe_insert("scale", index=2, frame=frame_end + grow)

        # El cartel entra cuando el edificio termino de subir, y se va cuando
        # empieza a bajar.
        keyframe_visible_from(obj, frame_in + (grow if part else 0))
        if frame_end:
            set_key_interpolation("CONSTANT")
            for prop in ("hide_viewport", "hide_render"):
                setattr(obj, prop, True)
                obj.keyframe_insert(prop, frame=frame_end)

        by_year.setdefault(year, set()).add(brand)
        if end_year:
            end_by_year.setdefault(int(end_year), set()).add(brand)
        objects.append(obj)
        animated.append({
            "sign": entry["name"],
            "brand": brand,
            "year": year,
            "frame_in": frame_in,
            "end_year": end_year,
            "end_reason": info.get("end_reason"),
            "edificio": part.name if part else None,
            "sitio": [round(v, 2) for v in site["at"]] if site else None,
            "confidence": info.get("confidence"),
        })

    animate_closed(closed, parts, collection, by_year, end_by_year, report)

    report["signs_animated"] = animated
    report["edificios_animados"] = built
    report["signs_sin_ano"] = sorted(sin_ano)
    report["objetos_del_manifiesto_ausentes"] = missing_objects
    if missing_objects:
        report["warnings"].append(
            "%d entradas del manifiesto no tienen objeto en el .blend"
            % len(missing_objects))
    if built < len(animated):
        report["warnings"].append(
            "%d carteles quedaron sin edificio propio: su 'owner' no matchea "
            "ningun sitio de city_buildings.json (son anclajes de fachada). El "
            "cartel se anima igual, el edificio no."
            % (len(animated) - built))
    return by_year, end_by_year, table, objects


def build_hud(cam, scene, by_year, end_by_year, table, collection, report):
    """Ano y titulares, pegados a la camara. Como la camara es fija, quedan
    clavados en el cuadro."""
    half_w = cam.data.ortho_scale * 0.5
    half_h = half_w * scene.render.resolution_y / scene.render.resolution_x
    # Justo delante del plano de recorte, no a mitad de la ciudad: a 600 el
    # texto quedaba DENTRO del casco urbano y las torres lo tapaban.
    cam.data.clip_start = min(cam.data.clip_start, 0.5)
    depth = -8.0

    year_mat = emission_material("hud_year", (1.0, 0.97, 0.92), 3.4)
    # Fuerte a proposito: las lineas cruzan techos claros y un rojo apagado
    # sobre hormigon blanco no se lee.
    line_mat = emission_material("hud_line", (1.0, 0.42, 0.26), 7.0)
    fixed_mat = emission_material("hud_fixed", (0.92, 0.93, 0.95), 2.0)

    def text(name, body, x, y, size, mat, align="LEFT"):
        curve = bpy.data.curves.new(TAG + name, type="FONT")
        curve.body = body
        curve.size = size
        curve.align_x = align
        curve.align_y = "CENTER"
        obj = bpy.data.objects.new(TAG + name, curve)
        obj.location = (x, y, depth)
        obj.data.materials.append(mat)
        collection.objects.link(obj)
        obj.parent = cam
        return obj

    # Los hitos van en SU ano, no en el de fundacion. El hito de Ualá habla de
    # 2026 y aparecia debajo de un cartel que decia 2017.
    hitos = {}
    for brand, info in table.items():
        for hito in hitos_de(info):
            year = hito_year(hito)
            if year is None:
                continue
            hitos.setdefault(year, []).append(
                "%s  -  %s" % (brand, hito.split(":", 1)[1].strip()))

    for year in range(YEAR_START, YEAR_END + 1):
        frame_in = year_to_frame(year)
        frame_out = frame_in + FRAMES_PER_YEAR
        year_obj = text("hud_year_%d" % year, str(year),
                        -half_w * 0.90, half_h * 0.78, half_h * 0.20, year_mat)
        keyframe_visible_range(year_obj, frame_in, frame_out)

        lines = ["se funda " + b for b in sorted(by_year.get(year, ()))]
        lines += ["cae " + b for b in sorted(end_by_year.get(year, ()))]
        lines += sorted(hitos.get(year, ()))
        if lines:
            line = text("hud_line_%d" % year, "\n".join(lines[:4]),
                        -half_w * 0.90, half_h * 0.56, half_h * 0.045,
                        line_mat)
            keyframe_visible_range(line, frame_in, frame_out)

    # Arriba a la izquierda, sobre el fondo oscuro: abajo a la derecha caia
    # sobre los edificios claros y el texto gris no se leia.
    text("hud_title",
         "SILICON BAIRES TIMELINE  -  ciudad de Aerolab/silicon-baires",
         -half_w * 0.90, half_h * 0.90, half_h * 0.030, fixed_mat)
    report["hud"] = {"anos": YEAR_END - YEAR_START + 1,
                     "titulares": len(by_year)}


def main():
    root = repo_root()
    scene = bpy.context.scene
    purge_previous()

    report = {
        "upstream": "https://github.com/Aerolab/silicon-baires",
        "upstream_commit": "963da3133d7cfd7cc30239cb57dca2696067d242",
        "year_start": YEAR_START,
        "year_end": YEAR_END,
        "frames_per_year": FRAMES_PER_YEAR,
        "fps": scene.render.fps,
        "warnings": [],
    }

    scene.frame_start = 1
    scene.frame_end = year_to_frame(YEAR_END) + FRAMES_PER_YEAR - 1
    report["frame_end"] = scene.frame_end
    if scene.frame_end > 624:
        report["warnings"].append(
            "la linea de tiempo (%d) pasa los 624 fotogramas que tiene animado "
            "el transito de upstream" % scene.frame_end)

    # Los carteles primero: el encuadre se decide a partir de donde caen los
    # que tienen ano, asi que hay que saber cuales son antes de tocar la camara.
    bld_coll = bpy.data.collections.new(TAG + "BUILDINGS")
    scene.collection.children.link(bld_coll)
    by_year, end_by_year, table, sign_objects = animate_signs(
        root, scene, report, bld_coll)
    if not sign_objects:
        raise SystemExit("ningun cartel del manifiesto tiene ano en "
                         "data/brand_years.json: no hay linea de tiempo")
    cam = freeze_camera(scene, report, sign_objects)

    hud_coll = bpy.data.collections.new(TAG + "HUD")
    scene.collection.children.link(hud_coll)
    build_hud(cam, scene, by_year, end_by_year, table, hud_coll, report)

    out_dir = os.path.join(root, "scene_city")
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir,
                                                      "city_timeline.blend"))
    with open(os.path.join(out_dir, "timeline_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("TIMELINE OK:", json.dumps({
        "frames": scene.frame_end,
        "carteles_animados": len(report["signs_animated"]),
        "marcas_sin_ano": len(report["signs_sin_ano"]),
        "ortho_scale": report["camera"]["ortho_scale"],
        "warnings": report["warnings"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
