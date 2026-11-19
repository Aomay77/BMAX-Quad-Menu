"""Run-time logic: menu resolution, availability, check marks, commands, dynamic menus."""

import json
import re
from types import SimpleNamespace

import bpy

from .model import prefs, MODE_IDS

# --------------------------------------------------------------------------
# Context helpers
# --------------------------------------------------------------------------
ANIM_AREAS = {'DOPESHEET_EDITOR', 'GRAPH_EDITOR'}


def current_mode(context):
    area = context.area
    if area is not None and area.type in ANIM_AREAS:
        return 'ANIMATION'
    mode = context.mode
    # Blender 5.x legacy aliases
    mode = {'PAINT_GPENCIL': 'PAINT_GREASE_PENCIL', 'EDIT_GPENCIL': 'EDIT_GREASE_PENCIL'}.get(mode, mode)
    return mode if mode in MODE_IDS else 'GLOBAL'


def anim_editor(context):
    area = context.area
    if area is None:
        return ''
    if area.type == 'GRAPH_EDITOR':
        return 'GRAPH'
    if area.type == 'DOPESHEET_EDITOR':
        return 'TIMELINE' if getattr(area, 'ui_type', '') == 'TIMELINE' else 'DOPESHEET'
    return ''


# --------------------------------------------------------------------------
# Safe property paths: identifiers and [int] only, resolved from bpy.context.
# 'selected_objects.<attr>' applies to every selected object.
# --------------------------------------------------------------------------
_TOKEN = re.compile(r'([A-Za-z_]\w*)(\[(\d+)\])?$')


class PathError(Exception):
    pass


def _split(path):
    parts = []
    for raw in path.split('.'):
        m = _TOKEN.match(raw.strip())
        if not m:
            raise PathError('Invalid property path: ' + path)
        parts.append((m.group(1), int(m.group(3)) if m.group(3) is not None else None))
    if not parts:
        raise PathError('Empty property path')
    return parts


def _walk(root, parts):
    obj = root
    for name, index in parts:
        obj = getattr(obj, name)
        if index is not None:
            obj = obj[index]
    return obj


def resolve(context, path):
    """Return list of (owner, attr, index) targets. Raises on failure."""
    parts = _split(path)
    if parts[0][0] == 'selected_objects' and parts[0][1] is None:
        owners = list(getattr(context, 'selected_objects', []) or [])
        rest = parts[1:]
        if not rest:
            raise PathError('selected_objects needs a property')
        targets = []
        for ob in owners:
            owner = _walk(ob, rest[:-1])
            targets.append((owner, rest[-1][0], rest[-1][1]))
        return targets
    owner = _walk(context, parts[:-1])
    if owner is None:
        raise PathError('Path not available here')
    name, index = parts[-1]
    return [(owner, name, index)]


def read(owner, name, index):
    v = getattr(owner, name)
    return v[index] if index is not None else v


def _is_flag(owner, name):
    try:
        p = owner.bl_rna.properties[name]
        return p.type == 'ENUM' and p.is_enum_flag
    except (AttributeError, KeyError):
        return False


def decode_value(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text  # bare enum identifiers are accepted without quotes


def path_state(context, path, value_text):
    """None = unavailable, else bool checked."""
    try:
        targets = resolve(context, path)
    except Exception:
        return None
    if not targets:
        return None
    owner, name, index = targets[0]  # active / first selected decides the check mark
    try:
        cur = read(owner, name, index)
    except Exception:
        return None
    value = decode_value(value_text)
    if value is None:
        return bool(cur)
    if _is_flag(owner, name) and index is None:
        return value in cur
    return cur == value


def path_apply(context, path, value_text):
    targets = resolve(context, path)
    if not targets:
        raise RuntimeError('Nothing to change (no selection?)')
    value = decode_value(value_text)
    first_state = None
    for owner, name, index in targets:
        cur = read(owner, name, index)
        if value is None:                       # boolean toggle
            if first_state is None:
                first_state = not bool(cur)
            new = first_state
        elif _is_flag(owner, name) and index is None:   # flag set membership toggle
            cur = set(cur)
            if first_state is None:
                first_state = value not in cur
            new = (cur | {value}) if first_state else (cur - {value})
            if not new:
                continue  # Blender rejects an empty flag set
        else:
            new = value
        if index is not None:
            arr = getattr(owner, name)
            arr[index] = new
        else:
            setattr(owner, name, new)


# --------------------------------------------------------------------------
# Specials and tools
# --------------------------------------------------------------------------
def tool_active(context, tool_id):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return tool is not None and tool.idname == tool_id
    except (AttributeError, RuntimeError, TypeError):
        return False


def in_local_view(context):
    space = context.space_data
    return getattr(space, 'local_view', None) is not None


OBJECT_MODE_CATALOG = (
    ('OBJECT', 'Object Mode', None),
    ('EDIT', 'Edit Mode', {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE', 'LATTICE',
                           'GREASEPENCIL', 'CURVES', 'POINTCLOUD'}),
    ('SCULPT', 'Sculpt Mode', {'MESH'}),
    ('VERTEX_PAINT', 'Vertex Paint', {'MESH'}),
    ('WEIGHT_PAINT', 'Weight Paint', {'MESH'}),
    ('TEXTURE_PAINT', 'Texture Paint', {'MESH'}),
    ('POSE', 'Pose Mode', {'ARMATURE'}),
    ('SCULPT_CURVES', 'Sculpt Mode', {'CURVES'}),
    ('PAINT_GREASE_PENCIL', 'Draw Mode', {'GREASEPENCIL'}),
    ('SCULPT_GREASE_PENCIL', 'Sculpt Mode', {'GREASEPENCIL'}),
    ('WEIGHT_GREASE_PENCIL', 'Weight Paint', {'GREASEPENCIL'}),
    ('VERTEX_GREASE_PENCIL', 'Vertex Paint', {'GREASEPENCIL'}),
)


def object_modes(context):
    ob = context.active_object
    if ob is None:
        return []
    try:
        available = {e.identifier for e in
                     bpy.ops.object.mode_set.get_rna_type().properties['mode'].enum_items}
    except (AttributeError, KeyError, RuntimeError):
        available = {m for m, _, _ in OBJECT_MODE_CATALOG}
    return [(m, label) for m, label, types in OBJECT_MODE_CATALOG
            if m in available and (types is None or ob.type in types)]


def special_available(context, name):
    if name.startswith('MODE:'):
        return any(m == name[5:] for m, _ in object_modes(context))
    if name in ('FREEZE_SELECTED',):
        return bool(context.selected_objects)
    if name == 'UNFREEZE_ALL':
        return context.view_layer is not None
    if name == 'OBJECT_PROPERTIES':
        return context.active_object is not None
    if name == 'ADD_MENU':
        return context.mode == 'OBJECT'
    if name == 'CAMERA_FROM_VIEW':
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'
    if name.startswith('UNHIDE:'):
        return True
    if name.startswith('SMART_SELECT_'):
        return True
    return True


def special_checked(context, name):
    if name.startswith('MODE:'):
        ob = context.active_object
        return ob is not None and ob.mode == name[5:]
    return False


def run_special(context, name):
    if name.startswith('MODE:'):
        mode = name[5:]
        ob = context.active_object
        if ob is None:
            raise RuntimeError('No active object')
        if ob.mode == mode:
            return {'FINISHED'}
        return bpy.ops.object.mode_set('EXEC_DEFAULT', mode=mode)
    if name == 'ADD_MENU':
        return bpy.ops.wm.call_menu('INVOKE_DEFAULT', name='VIEW3D_MT_add')
    if name == 'FREEZE_SELECTED':
        for ob in list(context.selected_objects):
            ob.select_set(False)
            ob.hide_select = True
        return {'FINISHED'}
    if name == 'UNFREEZE_ALL':
        for ob in context.view_layer.objects:
            ob.hide_select = False
        return {'FINISHED'}
    if name.startswith('UNHIDE:'):
        ob = context.view_layer.objects.get(name[7:])
        if ob is None:
            raise RuntimeError('Object not found: ' + name[7:])
        ob.hide_set(False)
        ob.hide_viewport = False
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {'FINISHED'}
    if name == 'OBJECT_PROPERTIES':
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                area.spaces.active.context = 'OBJECT'
                area.tag_redraw()
                return {'FINISHED'}
        raise RuntimeError('Open a Properties editor first')
    if name == 'CAMERA_FROM_VIEW':
        # 3ds Max "Create Camera From View" (Ctrl+C)
        bpy.ops.object.camera_add('EXEC_DEFAULT')
        cam = context.view_layer.objects.active
        context.scene.camera = cam
        r3d = context.space_data.region_3d
        cam.matrix_world = r3d.view_matrix.inverted()
        cam.data.lens = context.space_data.lens
        if r3d.view_perspective != 'CAMERA':
            r3d.view_perspective = 'CAMERA'
        return {'FINISHED'}
    if name.startswith('SMART_SELECT_'):
        action = 'SELECT' if name.endswith('_ALL') else 'INVERT'
        group = {'EDIT_MESH': 'mesh', 'EDIT_CURVE': 'curve', 'EDIT_ARMATURE': 'armature',
                 'POSE': 'pose', 'OBJECT': 'object'}.get(context.mode)
        if group is None:
            raise RuntimeError('Selection command unavailable in this mode')
        return getattr(bpy.ops, group).select_all('EXEC_DEFAULT', action=action)
    raise ValueError('Unknown special command: ' + name)


# --------------------------------------------------------------------------
# Operator helpers
# --------------------------------------------------------------------------
def op_function(op_id):
    parts = op_id.split('.')
    if len(parts) != 2 or not all(p.isidentifier() for p in parts):
        raise ValueError('Operator ID must look like category.name')
    fn = getattr(getattr(bpy.ops, parts[0]), parts[1])
    fn.get_rna_type()  # raises KeyError if missing
    return fn


def op_exists(op_id):
    try:
        op_function(op_id)
        return True
    except (AttributeError, KeyError, ValueError, RuntimeError):
        return False


def has_redo_props(op_id):
    try:
        rna = op_function(op_id).get_rna_type()
        return any(p.identifier != 'rna_type' and not p.is_readonly for p in rna.properties)
    except (AttributeError, KeyError, ValueError, RuntimeError):
        return False


def parse_kwargs(text_or_dict):
    if isinstance(text_or_dict, dict):
        return text_or_dict
    kw = json.loads(text_or_dict or '{}')
    if not isinstance(kw, dict):
        raise ValueError('Parameters must be a JSON object')
    return kw


def run_entry(context, e, caddy=False):
    """Execute a resolved entry (SimpleNamespace)."""
    if e.kind == 'PROP':
        path_apply(context, e.path, e.value)
        _redraw_all(context)
        return {'FINISHED'}
    op = e.operator
    if op.startswith('TOOL:'):
        if caddy:
            space = context.space_data
            space.show_region_ui = not space.show_region_ui
            return {'FINISHED'}
        space = context.space_data
        if hasattr(space, 'show_gizmo'):
            space.show_gizmo = True
            space.show_gizmo_tool = True
        return bpy.ops.wm.tool_set_by_id('EXEC_DEFAULT', name=op[5:], space_type='VIEW_3D')
    if op.startswith('SPECIAL:'):
        return run_special(context, op[8:])
    fn = op_function(op)
    kwargs = parse_kwargs(e.kwargs)
    if not fn.poll():
        raise RuntimeError('Not available here: ' + op)
    if caddy:
        # 3ds Max settings box: run with current settings, then open the parameters
        # (Blender: Adjust Last Operation popup at the cursor).
        result = fn('EXEC_DEFAULT', **kwargs)
        if 'FINISHED' in result and bpy.ops.screen.redo_last.poll():
            bpy.ops.screen.redo_last('INVOKE_DEFAULT')
        return result
    return fn('INVOKE_DEFAULT' if e.invoke else 'EXEC_DEFAULT', **kwargs)


def _redraw_all(context):
    screen = context.screen
    if screen:
        for area in screen.areas:
            area.tag_redraw()


# --------------------------------------------------------------------------
# Dynamic submenus
# --------------------------------------------------------------------------
ADD_CATALOG = (
    ('Standard Primitives', (
        ('Plane', 'mesh.primitive_plane_add', {}), ('Box', 'mesh.primitive_cube_add', {}),
        ('Sphere', 'mesh.primitive_uv_sphere_add', {}), ('GeoSphere', 'mesh.primitive_ico_sphere_add', {}),
        ('Cylinder', 'mesh.primitive_cylinder_add', {}), ('Cone', 'mesh.primitive_cone_add', {}),
        ('Torus', 'mesh.primitive_torus_add', {}), ('Circle', 'mesh.primitive_circle_add', {}),
        ('Grid', 'mesh.primitive_grid_add', {}), ('Monkey', 'mesh.primitive_monkey_add', {}))),
    ('Shapes (Curves)', (
        ('Bezier', 'curve.primitive_bezier_curve_add', {}), ('Circle', 'curve.primitive_bezier_circle_add', {}),
        ('NURBS Curve', 'curve.primitive_nurbs_curve_add', {}), ('Path', 'curve.primitive_nurbs_path_add', {}),
        ('Text', 'object.text_add', {}))),
    ('Lights', (
        ('Point', 'object.light_add', {'type': 'POINT'}), ('Sun', 'object.light_add', {'type': 'SUN'}),
        ('Spot', 'object.light_add', {'type': 'SPOT'}), ('Area', 'object.light_add', {'type': 'AREA'}))),
    ('Cameras', (('Camera', 'object.camera_add', {}), ('Camera From View', 'SPECIAL:CAMERA_FROM_VIEW', {}))),
    ('Helpers (Empties)', (
        ('Point (Plain Axes)', 'object.empty_add', {'type': 'PLAIN_AXES'}),
        ('Arrows', 'object.empty_add', {'type': 'ARROWS'}), ('Cube', 'object.empty_add', {'type': 'CUBE'}),
        ('Sphere', 'object.empty_add', {'type': 'SPHERE'}), ('Circle', 'object.empty_add', {'type': 'CIRCLE'}),
        ('Reference Image', 'object.empty_image_add', {'background': False}))),
    ('Space Warps (Force Fields)', (
        ('Force', 'object.effector_add', {'type': 'FORCE'}), ('Wind', 'object.effector_add', {'type': 'WIND'}),
        ('Vortex', 'object.effector_add', {'type': 'VORTEX'}),
        ('Turbulence', 'object.effector_add', {'type': 'TURBULENCE'}))),
    ('Systems', (
        ('Bone (Armature)', 'object.armature_add', {}), ('Lattice', 'object.add', {'type': 'LATTICE'}),
        ('Grease Pencil', 'object.grease_pencil_add', {'type': 'STROKE'}),
        ('Collection Instance...', 'object.collection_instance_add', {}))),
)


def ns(**kw):
    base = dict(uid='', kind='OP', label='', operator='', kwargs='{}', invoke=True, path='',
                value='', dynamic='', caddy=False, available=True, checked=None, shortcut='',
                source=None, children=None)
    base.update(kw)
    return SimpleNamespace(**base)


def dynamic_entries(context, gen, parent_uid):
    out = []
    if gen == 'ADD':
        if context.mode != 'OBJECT':
            return out
        for n, (cat, cmds) in enumerate(ADD_CATALOG):
            kids = []
            for i, (label, op, kw) in enumerate(cmds):
                if op.startswith('SPECIAL:') or op_exists(op):
                    kids.append(ns(uid='%s/add/%d/%d' % (parent_uid, n, i), label=label,
                                   operator=op, kwargs=json.dumps(kw)))
            if kids:
                out.append(ns(uid='%s/add/%d' % (parent_uid, n), kind='SUB', label=cat, children=kids))
        out.append(ns(kind='SEP', uid=parent_uid + '/add/sep'))
        out.append(ns(uid=parent_uid + '/add/native', label='Blender Add Menu (All, Add-ons)',
                      operator='SPECIAL:ADD_MENU'))
    elif gen == 'MODES':
        for m, label in object_modes(context):
            out.append(ns(uid='%s/mode/%s' % (parent_uid, m), label=label, operator='SPECIAL:MODE:' + m))
    elif gen == 'HIDDEN':
        vl = context.view_layer
        hidden = [ob for ob in vl.objects if ob.hide_get()] if vl else []
        for ob in sorted(hidden, key=lambda o: o.name.lower())[:30]:
            out.append(ns(uid='%s/unhide/%s' % (parent_uid, ob.name), label=ob.name,
                          operator='SPECIAL:UNHIDE:' + ob.name))
    elif gen == 'ORIENTATIONS':
        try:
            slot = context.scene.transform_orientation_slots[0]
            items = slot.bl_rna.properties['type'].enum_items_static
            names = [(e.identifier, e.name) for e in items]
            names += [(o.name, o.name) for o in getattr(context.scene, 'transform_orientations', [])]
        except (AttributeError, KeyError, IndexError):
            names = []
        for ident, label in names:
            out.append(ns(uid='%s/orient/%s' % (parent_uid, ident), kind='PROP', label=label,
                          path='scene.transform_orientation_slots[0].type', value=json.dumps(ident)))
    elif gen == 'PIVOTS':
        for ident, label in (('BOUNDING_BOX_CENTER', 'Bounding Box Center'), ('CURSOR', '3D Cursor'),
                             ('INDIVIDUAL_ORIGINS', 'Individual Origins'),
                             ('MEDIAN_POINT', 'Median Point'), ('ACTIVE_ELEMENT', 'Active Element')):
            out.append(ns(uid='%s/pivot/%s' % (parent_uid, ident), kind='PROP', label=label,
                          path='tool_settings.transform_pivot_point', value=json.dumps(ident)))
    elif gen == 'VIEWS':
        for t in ('TOP', 'BOTTOM', 'FRONT', 'BACK', 'LEFT', 'RIGHT'):
            out.append(ns(uid='%s/view/%s' % (parent_uid, t), label=t.title(),
                          operator='view3d.view_axis', kwargs=json.dumps({'type': t}), invoke=False))
        out.append(ns(uid=parent_uid + '/view/cam', label='Camera', operator='view3d.view_camera'))
    return out


# --------------------------------------------------------------------------
# Shortcut text lookup (3ds Max shows hotkeys next to quad items)
# --------------------------------------------------------------------------
_SHORTCUT_KEYMAPS = ('Window', 'Screen', '3D View', '3D View Generic', 'Object Mode', 'Mesh', 'Curve',
                     'Armature', 'Pose', 'Sculpt', 'Frames', 'Object Non-modal', 'Dopesheet',
                     'Graph Editor', 'Animation', 'Markers')


def build_shortcut_table(context):
    table = {}
    try:
        kc = context.window_manager.keyconfigs.user
    except AttributeError:
        return table
    if kc is None:
        return table
    for name in _SHORTCUT_KEYMAPS:
        km = kc.keymaps.get(name)
        if km is None:
            continue
        for kmi in km.keymap_items:
            if not kmi.active or kmi.map_type not in {'KEYBOARD', 'MOUSE'}:
                continue
            if kmi.type in {'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE', 'MOUSEMOVE'}:
                continue
            table.setdefault(kmi.idname, []).append(kmi)
    return table


def shortcut_for(table, op_id, kwargs):
    for kmi in table.get(op_id, ()):
        props = kmi.properties
        ok = True
        if props is not None:
            for k, v in kwargs.items():
                try:
                    cur = getattr(props, k)
                    if hasattr(cur, '__len__') and not isinstance(cur, str):
                        cur = list(cur)
                        v = list(v) if isinstance(v, (list, tuple)) else v
                    if props.is_property_set(k) and cur != v:
                        ok = False
                        break
                    if not props.is_property_set(k):
                        ok = False
                        break
                except (AttributeError, TypeError, KeyError):
                    ok = False
                    break
        elif kwargs:
            ok = False
        if ok:
            try:
                return kmi.to_string()
            except (AttributeError, RuntimeError):
                return ''
    return ''


# --------------------------------------------------------------------------
# Resolver: builds the visible menu tree once per opening
# --------------------------------------------------------------------------
class Resolver:
    def __init__(self, context, set_id, mode):
        self.context = context
        self.set_id = set_id
        self.mode = mode
        p = prefs()
        self.hide_unavailable = p.unavailable == 'HIDE'
        self.show_shortcuts = p.show_shortcuts
        self.editor = anim_editor(context)
        self.poll_cache = {}
        self.by_key = {}
        self.by_parent = {}
        for it in p.items:
            if not it.enabled or it.set_id != set_id:
                continue
            e = ns(uid=it.uid, kind=it.kind, label=it.label, operator=it.operator, kwargs=it.kwargs,
                   invoke=it.invoke, path=it.path, value=it.value, dynamic=it.dynamic,
                   caddy=it.caddy, object_types=set(it.object_types), require=set(it.require),
                   mode=it.mode, quad=it.quad,
                   own_shortcut=_own_shortcut_text(it))
            if it.parent:
                self.by_parent.setdefault(it.parent, []).append(e)
            else:
                self.by_key.setdefault((it.mode, it.quad), []).append(e)
        self.shortcuts = build_shortcut_table(context) if self.show_shortcuts else {}
        ob = context.active_object
        self.ob_type = ob.type if ob is not None else None
        self.n_selected = len(getattr(context, 'selected_objects', None) or [])
        self.local_view = in_local_view(context)
        try:
            msm = tuple(context.tool_settings.mesh_select_mode)
        except AttributeError:
            msm = (False, False, False)
        self.select_levels = {lvl for lvl, on in zip(('VERT', 'EDGE', 'FACE'), msm) if on}
        self.is_edit_mesh = context.mode == 'EDIT_MESH'

    # ---- conditions ------------------------------------------------------
    def conditions_ok(self, e):
        types = getattr(e, 'object_types', None)
        if types and self.ob_type not in types:
            return False
        req = getattr(e, 'require', None) or set()
        if 'SELECTION' in req and self.n_selected == 0:
            return False
        if 'SINGLE' in req and self.n_selected != 1:
            return False
        if 'LOCAL_VIEW' in req and not self.local_view:
            return False
        if 'NOT_LOCAL_VIEW' in req and self.local_view:
            return False
        levels = req & {'VERT', 'EDGE', 'FACE'}
        if levels and (not self.is_edit_mesh or not (levels & self.select_levels)):
            return False
        return True

    def _poll(self, op_id):
        if op_id in self.poll_cache:
            return self.poll_cache[op_id]
        ok = False
        try:
            group = op_id.split('.', 1)[0]
            if self.mode == 'ANIMATION':
                if group == 'graph' and self.editor != 'GRAPH':
                    raise RuntimeError
                if group == 'action' and self.editor != 'DOPESHEET':
                    raise RuntimeError
            ok = bool(op_function(op_id).poll())
        except Exception:
            ok = False
        self.poll_cache[op_id] = ok
        return ok

    def annotate(self, e):
        """Fill e.available / e.checked / e.shortcut."""
        ctx = self.context
        if e.kind == 'PROP':
            state = path_state(ctx, e.path, e.value)
            e.available = state is not None
            e.checked = bool(state) if state is not None else None
            return
        if e.kind != 'OP':
            return
        op = e.operator
        if not op:
            e.available = False
            return
        if op.startswith('TOOL:'):
            e.available = self.mode != 'ANIMATION' and ctx.area is not None and ctx.area.type == 'VIEW_3D'
            e.checked = tool_active(ctx, op[5:])
        elif op.startswith('SPECIAL:'):
            try:
                e.available = special_available(ctx, op[8:])
                e.checked = special_checked(ctx, op[8:]) or None
            except Exception:
                e.available = False
        else:
            e.available = self._poll(op)
            if e.available and self.show_shortcuts:
                try:
                    e.shortcut = shortcut_for(self.shortcuts, op, parse_kwargs(e.kwargs))
                except Exception:
                    e.shortcut = ''
        if e.path:  # optional check mark for commands
            state = path_state(ctx, e.path, e.value)
            e.checked = bool(state) if state is not None else e.checked
        if getattr(e, 'own_shortcut', ''):
            e.shortcut = e.own_shortcut

    # ---- tree ------------------------------------------------------------
    def root(self, quad):
        entries = self.by_key.get((self.mode, quad))
        if not entries and self.mode != 'ANIMATION':
            entries = self.by_key.get(('GLOBAL', quad))
        return self.visible(entries or [], depth=0)

    def children(self, e):
        if e.children is not None:
            return e.children
        if e.kind == 'DYN':
            raw = dynamic_entries(self.context, e.dynamic, e.uid)
        elif e.kind == 'SUB':
            raw = self.by_parent.get(e.uid, [])
        else:
            raw = []
        e.children = self.visible(raw, depth=1)
        return e.children

    def visible(self, entries, depth):
        out = []
        for e in entries:
            if e.kind == 'SEP':
                out.append(e)
                continue
            if not self.conditions_ok(e):
                continue
            if e.kind in ('SUB', 'DYN'):
                if depth > 12:
                    continue
                kids = self.children(e)
                if not any(k.kind != 'SEP' for k in kids):
                    continue
                e.available = any(k.kind != 'SEP' and k.available for k in kids)
                if not e.available and self.hide_unavailable:
                    continue
                out.append(e)
                continue
            self.annotate(e)
            if not e.available and self.hide_unavailable:
                continue
            out.append(e)
        # tidy separators (no leading, trailing or double)
        tidy = []
        for e in out:
            if e.kind == 'SEP' and (not tidy or tidy[-1].kind == 'SEP'):
                continue
            tidy.append(e)
        while tidy and tidy[-1].kind == 'SEP':
            tidy.pop()
        return tidy


def _own_shortcut_text(it):
    if it.shortcut_key == 'NONE':
        return ''
    mods = [n for n, on in (('Ctrl', it.shortcut_ctrl), ('Shift', it.shortcut_shift),
                            ('Alt', it.shortcut_alt), ('OS', it.shortcut_oskey)) if on]
    return ' '.join(mods + [it.shortcut_key.replace('_', ' ').title()])
