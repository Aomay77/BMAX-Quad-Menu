"""Data model: PropertyGroups, JSON persistence (single source of truth), migration."""

import json
import os
import uuid
from datetime import datetime

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty,
                       FloatVectorProperty, IntProperty, StringProperty)
from bpy.types import PropertyGroup

ADDON = __package__
CONFIG_NAME = 'bmax_quad.json'
FORMAT = 'BMAX Quad Menu'
VERSION = 3

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
MODES = [
    ('GLOBAL', 'Global (fallback)', 'Used when the current mode has no items in this quadrant'),
    ('OBJECT', 'Object', ''),
    ('EDIT_MESH', 'Edit Mesh', ''),
    ('EDIT_CURVE', 'Edit Curve', ''),
    ('EDIT_CURVES', 'Edit Curves (Hair)', ''),
    ('EDIT_SURFACE', 'Edit Surface', ''),
    ('EDIT_TEXT', 'Edit Text', ''),
    ('EDIT_ARMATURE', 'Edit Armature', ''),
    ('EDIT_METABALL', 'Edit Metaball', ''),
    ('EDIT_LATTICE', 'Edit Lattice', ''),
    ('EDIT_GREASE_PENCIL', 'Edit Grease Pencil', ''),
    ('POSE', 'Pose', ''),
    ('SCULPT', 'Sculpt', ''),
    ('SCULPT_CURVES', 'Sculpt Curves', ''),
    ('PAINT_VERTEX', 'Vertex Paint', ''),
    ('PAINT_WEIGHT', 'Weight Paint', ''),
    ('PAINT_TEXTURE', 'Texture Paint', ''),
    ('PAINT_GREASE_PENCIL', 'Grease Pencil Draw', ''),
    ('PARTICLE', 'Particle Edit', ''),
    ('ANIMATION', 'Track View (Dope Sheet / Graph / Timeline)', 'Used in animation editors'),
]
MODE_IDS = {m[0] for m in MODES}

# 3ds Max numbering: Quad 1 = lower right, then counter-clockwise.
QUADS = [
    ('TL', 'Quad 3 · Upper Left', 'Tools 1 in the 3ds Max default set'),
    ('TR', 'Quad 2 · Upper Right', 'Display in the 3ds Max default set'),
    ('BL', 'Quad 4 · Lower Left', 'Tools 2 in the 3ds Max default set'),
    ('BR', 'Quad 1 · Lower Right', 'Transform in the 3ds Max default set'),
]
QUAD_IDS = ('TL', 'TR', 'BL', 'BR')
MAX_QUAD_NUMBER = {'BR': 1, 'TR': 2, 'TL': 3, 'BL': 4}

KINDS = [
    ('OP', 'Command', 'Run a Blender operator or BMAX special command'),
    ('PROP', 'Toggle / Set Property', 'Toggle a boolean or set a value, shows a check mark'),
    ('SUB', 'Submenu', ''),
    ('DYN', 'Dynamic Submenu', 'Generated at run time (Create, Modes, Hidden Objects...)'),
    ('SEP', 'Separator', ''),
]

DYNAMIC_MENUS = [
    ('ADD', 'Create (Add Objects)', 'Primitive catalog plus Blender Add menu'),
    ('MODES', 'Object Modes', 'Interaction modes of the active object'),
    ('HIDDEN', 'Unhide by Name', 'List hidden objects; click to unhide'),
    ('ORIENTATIONS', 'Transform Orientations', 'Includes custom orientations'),
    ('PIVOTS', 'Pivot Point', 'Transform pivot point'),
    ('VIEWS', 'Views', 'Top / Front / Left / Camera...'),
]

OBJECT_TYPES = [
    ('MESH', 'Mesh', ''), ('CURVE', 'Curve', ''), ('SURFACE', 'Surface', ''),
    ('META', 'Metaball', ''), ('FONT', 'Text', ''), ('CURVES', 'Hair Curves', ''),
    ('POINTCLOUD', 'Point Cloud', ''), ('VOLUME', 'Volume', ''),
    ('GREASEPENCIL', 'Grease Pencil', ''), ('ARMATURE', 'Armature', ''),
    ('LATTICE', 'Lattice', ''), ('EMPTY', 'Empty', ''), ('LIGHT', 'Light', ''),
    ('LIGHT_PROBE', 'Light Probe', ''), ('CAMERA', 'Camera', ''),
    ('SPEAKER', 'Speaker', ''),
]

REQUIREMENTS = [
    ('SELECTION', 'Has Selection', 'At least one selected object'),
    ('SINGLE', 'Single Selection', 'Exactly one selected object'),
    ('LOCAL_VIEW', 'In Isolate', 'Only while in Local View (Isolate)'),
    ('NOT_LOCAL_VIEW', 'Not Isolated', 'Only while not in Local View'),
    ('VERT', 'Vertex Level', 'Mesh sub-object level: vertex'),
    ('EDGE', 'Edge Level', 'Mesh sub-object level: edge'),
    ('FACE', 'Polygon Level', 'Mesh sub-object level: face'),
]

_EXCLUDED_EVENTS = {
    'NONE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE',
    'MOUSESMARTZOOM', 'PEN', 'ERASER', 'LEFT_CTRL', 'LEFT_ALT', 'LEFT_SHIFT', 'RIGHT_ALT',
    'RIGHT_CTRL', 'RIGHT_SHIFT', 'OSKEY', 'HYPER', 'ESC', 'TEXTINPUT', 'WINDOW_DEACTIVATE',
    'NDOF_MOTION', 'XR_ACTION'}


def _event_keys():
    """Every keyboard / mouse / NDOF button Blender can bind (from Blender's own Event enum)."""
    try:
        items = bpy.types.Event.bl_rna.properties['type'].enum_items
        keys = [(e.identifier, e.name or e.identifier, '') for e in items
                if e.identifier not in _EXCLUDED_EVENTS
                and not e.identifier.startswith(('TIMER', 'ACTIONZONE'))]
    except (AttributeError, KeyError):
        keys = []
    if not keys:  # fallback
        keys = [(k, k.title(), '') for k in
                ['RIGHTMOUSE', 'MIDDLEMOUSE', 'BUTTON4MOUSE', 'BUTTON5MOUSE', 'SPACE', 'TAB']
                + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ['F%d' % i for i in range(1, 13)]]
    return keys


EVENT_KEYS = _event_keys()
TRIGGER_KEYS = [('NONE', 'None', 'No trigger')] + EVENT_KEYS
SHORTCUT_KEYS = [('NONE', 'None', 'No shortcut')] + EVENT_KEYS
SHORTCUT_KEY_IDS = {k[0] for k in SHORTCUT_KEYS}
TRIGGER_KEY_IDS = {k[0] for k in TRIGGER_KEYS} - {'NONE'}


def uid():
    return uuid.uuid4().hex[:12]


def prefs():
    return bpy.context.preferences.addons[ADDON].preferences


# --------------------------------------------------------------------------
# Debounced auto-save. Every UI edit lands in JSON; JSON is loaded on start.
# --------------------------------------------------------------------------
_state = {'loading': False, 'save_pending': False}


def _deferred_save():
    _state['save_pending'] = False
    try:
        save_config()
    except Exception as exc:  # pragma: no cover - report only
        print('BMAX Quad: save failed:', exc)
    return None


def schedule_save(self=None, context=None):
    if _state['loading'] or _state['save_pending']:
        return
    _state['save_pending'] = True
    bpy.app.timers.register(_deferred_save, first_interval=0.6)


def _keymap_update(self, context):
    schedule_save()
    from . import keymaps
    keymaps.schedule_refresh()


# --------------------------------------------------------------------------
# PropertyGroups
# --------------------------------------------------------------------------
class BMAXQUAD_PG_item(PropertyGroup):
    uid: StringProperty()
    set_id: StringProperty()
    mode: EnumProperty(name='Mode', items=MODES, default='OBJECT', update=schedule_save)
    quad: EnumProperty(name='Quadrant', items=QUADS, default='TL', update=schedule_save)
    parent: StringProperty()
    kind: EnumProperty(name='Type', items=KINDS, default='OP', update=schedule_save)
    label: StringProperty(name='Label', default='New Command', update=schedule_save)
    operator: StringProperty(
        name='Command', update=schedule_save,
        description='Operator ID (mesh.bevel), TOOL:builtin.move, or SPECIAL:...')
    kwargs: StringProperty(name='Parameters', default='{}', update=schedule_save,
                           description='JSON object of operator parameters')
    invoke: BoolProperty(name='Interactive (Invoke)', default=True, update=schedule_save,
                         description='Run like a button click (modal tools, dialogs). Off = execute directly')
    path: StringProperty(
        name='Property Path', update=schedule_save,
        description='Context path, e.g. space_data.shading.show_xray, tool_settings.use_snap, '
                    'selected_objects.hide_render. For commands, optional: shows a check mark')
    value: StringProperty(
        name='Value', update=schedule_save,
        description='JSON value to set (e.g. "WIREFRAME"). Empty = toggle a boolean. '
                    'For flag sets, toggles membership')
    dynamic: EnumProperty(name='Generator', items=DYNAMIC_MENUS, default='ADD', update=schedule_save)
    object_types: EnumProperty(name='Object Types', items=OBJECT_TYPES, options={'ENUM_FLAG'},
                               default=set(), update=schedule_save,
                               description='Show only when the active object is one of these types (empty = any)')
    require: EnumProperty(name='Show When', items=REQUIREMENTS, options={'ENUM_FLAG'},
                          default=set(), update=schedule_save)
    caddy: BoolProperty(name='Settings Box', default=False, update=schedule_save,
                        description='Show a 3ds Max style settings box; click it to run and open Adjust Last Operation')
    enabled: BoolProperty(name='Enabled', default=True, update=schedule_save)
    shortcut_key: EnumProperty(name='Key', items=SHORTCUT_KEYS, default='NONE', update=_keymap_update)
    shortcut_ctrl: BoolProperty(name='Ctrl', update=_keymap_update)
    shortcut_shift: BoolProperty(name='Shift', update=_keymap_update)
    shortcut_alt: BoolProperty(name='Alt', update=_keymap_update)
    shortcut_oskey: BoolProperty(name='OS', update=_keymap_update)


class BMAXQUAD_PG_set(PropertyGroup):
    uid: StringProperty()
    name: StringProperty(name='Name', default='Quad Set', update=schedule_save)
    enabled: BoolProperty(name='Enabled', default=False, update=_keymap_update)
    key: EnumProperty(name='Trigger', items=TRIGGER_KEYS, default='NONE', update=_keymap_update,
                      description='Any key or mouse button; combine with Ctrl / Shift / Alt / OS')
    ctrl: BoolProperty(name='Ctrl', update=_keymap_update)
    shift: BoolProperty(name='Shift', update=_keymap_update)
    alt: BoolProperty(name='Alt', update=_keymap_update)
    oskey: BoolProperty(name='OS', update=_keymap_update)
    in_view3d: BoolProperty(name='3D Viewport', default=True, update=_keymap_update)
    in_anim: BoolProperty(name='Animation Editors', default=False, update=_keymap_update,
                          description='Also trigger in Dope Sheet, Timeline and Graph Editor (Track View)')
    show_all: BoolProperty(name='Show All Quads', default=True, update=schedule_save,
                           description='On: right-click shows all four quads. Off: one quad at a time, '
                                       'hover a title to switch (3ds Max "Show All Quads")')
    title_TL: StringProperty(name='Quad 3 Title', default='tools 1', update=schedule_save)
    title_TR: StringProperty(name='Quad 2 Title', default='display', update=schedule_save)
    title_BL: StringProperty(name='Quad 4 Title', default='tools 2', update=schedule_save)
    title_BR: StringProperty(name='Quad 1 Title', default='transform', update=schedule_save)


class BMAXQUAD_PG_ui(PropertyGroup):
    """Transient editor location (WindowManager, not saved)."""
    set_id: StringProperty()
    mode: EnumProperty(name='Mode', items=MODES, default='OBJECT')
    quad: EnumProperty(name='Quadrant', items=QUADS, default='BR')
    parent: StringProperty()
    tab: EnumProperty(items=[('SETS', 'Quad Sets', '', 'MENU_PANEL', 0),
                             ('MENUS', 'Menu Editor', '', 'PRESET', 1),
                             ('OPTIONS', 'Advanced Options', '', 'PREFERENCES', 2)],
                      default='MENUS')


ITEM_FIELDS = ('uid', 'set_id', 'mode', 'quad', 'parent', 'kind', 'label', 'operator', 'kwargs',
               'invoke', 'path', 'value', 'dynamic', 'object_types', 'require', 'caddy', 'enabled',
               'shortcut_key', 'shortcut_ctrl', 'shortcut_shift', 'shortcut_alt', 'shortcut_oskey')
SET_FIELDS = ('uid', 'name', 'enabled', 'key', 'ctrl', 'shift', 'alt', 'oskey', 'in_view3d',
              'in_anim', 'show_all', 'title_TL', 'title_TR', 'title_BL', 'title_BR')
OPTION_FIELDS = ('menu_font_size', 'title_font_size', 'font_path', 'vertical_margin', 'min_width',
                 'uniform_width', 'mirror_quads', 'opacity', 'reposition', 'move_cursor',
                 'return_cursor', 'starting_quad', 'animation', 'fade_steps', 'fade_pause',
                 'submenu_pause', 'use_last_executed', 'unavailable', 'show_shortcuts',
                 'release_to_execute', 'start_at_click', 'lock_colors',
                 'col_background', 'col_border', 'col_text', 'col_disabled', 'col_shortcut',
                 'col_title', 'col_title_text', 'col_title_active', 'col_highlight', 'col_last',
                 'col_title_active_TL', 'col_title_active_TR', 'col_title_active_BL',
                 'col_title_active_BR', 'col_highlight_TL', 'col_highlight_TR',
                 'col_highlight_BL', 'col_highlight_BR')


def item_to_dict(it):
    d = {}
    for k in ITEM_FIELDS:
        v = getattr(it, k)
        if isinstance(v, set):
            v = sorted(v)
        d[k] = v
    # Store parameters as real JSON, not as an escaped string.
    try:
        d['kwargs'] = json.loads(it.kwargs or '{}')
    except ValueError:
        d['kwargs'] = {}
    return d


def assign(target, data, fields):
    for k in fields:
        if k not in data:
            continue
        v = data[k]
        if k == 'kwargs' and not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)
        if k in ('object_types', 'require'):
            v = set(v or [])
        try:
            setattr(target, k, v)
        except (TypeError, ValueError, AttributeError):
            pass


# --------------------------------------------------------------------------
# Paths and persistence
# --------------------------------------------------------------------------
def config_dir():
    return bpy.utils.user_resource('CONFIG', path='bmax_quad_menu', create=True)


def config_path():
    return os.path.join(config_dir(), CONFIG_NAME)


def legacy_config_path():
    return os.path.join(bpy.utils.user_resource('CONFIG', path='max_quad_menu'), 'menus.json')


def config_to_dict():
    p = prefs()
    options = {}
    for k in OPTION_FIELDS:
        v = getattr(p, k)
        options[k] = list(v) if hasattr(v, '__len__') and not isinstance(v, str) else v
    return {'format': FORMAT, 'version': VERSION,
            'options': options,
            'sets': [{k: getattr(s, k) for k in SET_FIELDS} for s in p.sets],
            'items': [item_to_dict(it) for it in p.items]}


def save_config(path=None):
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(config_to_dict(), f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def backup(prefix):
    path = os.path.join(config_dir(), 'backup_%s_%s.json' % (
        prefix, datetime.now().strftime('%Y%m%d_%H%M%S')))
    save_config(path)
    return path


def validate(data):
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError('Not a BMAX Quad Menu file')
    if not isinstance(data.get('items'), list) or not isinstance(data.get('sets'), list):
        raise ValueError('Invalid BMAX Quad file: sets/items must be lists')
    for rec in data['items']:
        if not isinstance(rec, dict):
            raise ValueError('Invalid menu entry')
        if rec.get('mode', 'OBJECT') not in MODE_IDS:
            raise ValueError('Unknown mode: %s' % rec.get('mode'))
        if rec.get('quad', 'TL') not in QUAD_IDS:
            raise ValueError('Unknown quadrant: %s' % rec.get('quad'))
        kw = rec.get('kwargs', {})
        if isinstance(kw, str):
            kw = json.loads(kw or '{}')
        if not isinstance(kw, dict):
            raise ValueError('Parameters must be a JSON object')


def apply_dict(data):
    """Replace the whole configuration in memory from a v2 dict."""
    if data.get('version', 1) < 2 and 'pages' in data:
        data = migrate_legacy(data)
    validate(data)
    if data.get('version', 2) < 3:
        # v1.0.0 enabled right-click sets out of the box. From v1.1 nothing is enabled
        # until the user turns a set on, so Blender's own menus are never overridden.
        for rec in data['sets']:
            rec['enabled'] = False
    p = prefs()
    _state['loading'] = True
    try:
        p.sets.clear()
        for rec in data['sets']:
            s = p.sets.add()
            assign(s, rec, SET_FIELDS)
            if not s.uid:
                s.uid = uid()
        p.items.clear()
        for rec in data['items']:
            it = p.items.add()
            assign(it, rec, ITEM_FIELDS)
            if not it.uid:
                it.uid = uid()
        opts = data.get('options', {})
        for k in OPTION_FIELDS:
            if k in opts:
                try:
                    setattr(p, k, opts[k])
                except (TypeError, ValueError):
                    pass
    finally:
        _state['loading'] = False


def load_config(path=None):
    with open(path or config_path(), 'r', encoding='utf-8') as f:
        data = json.load(f)
    apply_dict(data)


def items_dicts_from_defaults():
    from . import defaults
    return defaults.build()


def load_factory():
    from . import defaults
    sets, items = defaults.build()
    _state['loading'] = True
    try:
        p = prefs()
        p.sets.clear()
        p.items.clear()
        for rec in sets:
            assign(p.sets.add(), rec, SET_FIELDS)
        for rec in items:
            assign(p.items.add(), rec, ITEM_FIELDS)
    finally:
        _state['loading'] = False


def restore_missing():
    """Add factory sets/items that are missing; never delete or overwrite user items.

    Items match on (set, mode, quad, parent label path, label)."""
    from . import defaults
    sets, items = defaults.build()
    p = prefs()
    added = 0
    _state['loading'] = True
    try:
        have_sets = {s.uid for s in p.sets}
        for rec in sets:
            if rec['uid'] not in have_sets:
                assign(p.sets.add(), rec, SET_FIELDS)
                added += 1
        by_uid = {it.uid: it for it in p.items}

        def label_path(uid_, lookup):
            path = []
            seen = set()
            while uid_ and uid_ not in seen:
                seen.add(uid_)
                node = lookup.get(uid_)
                if node is None:
                    break
                path.append(node['label'] if isinstance(node, dict) else node.label)
                uid_ = node['parent'] if isinstance(node, dict) else node.parent
            return tuple(reversed(path))

        existing = {}
        for it in p.items:
            key = (it.set_id, it.mode, it.quad, label_path(it.parent, by_uid), it.label)
            existing[key] = it.uid
        factory_lookup = {r['uid']: r for r in items}
        uid_map = {}
        for rec in items:
            ppath = label_path(rec['parent'], factory_lookup)
            key = (rec['set_id'], rec['mode'], rec['quad'], ppath, rec['label'])
            if key in existing:
                uid_map[rec['uid']] = existing[key]
                continue
            new = dict(rec)
            new['uid'] = uid()
            new['parent'] = uid_map.get(rec['parent'], '') if rec['parent'] else ''
            if rec['parent'] and not new['parent']:
                continue
            uid_map[rec['uid']] = new['uid']
            existing[key] = new['uid']
            assign(p.items.add(), new, ITEM_FIELDS)
            added += 1
    finally:
        _state['loading'] = False
    return added


# --------------------------------------------------------------------------
# Migration from v0.0.18 (menus.json: pages, Q1..Q4 = TL, TR, BL, BR)
# --------------------------------------------------------------------------
LEGACY_QUAD = {'Q1': 'TL', 'Q2': 'TR', 'Q3': 'BL', 'Q4': 'BR'}


def _legacy_special(op):
    """Translate v0.0.18 SPECIAL: commands -> (kind, operator, path, value, kwargs)."""
    s = op[8:]
    if s.startswith('SHADING_'):
        return 'PROP', '', 'space_data.shading.type', json.dumps(s[8:]), {}
    if s == 'XRAY':
        return 'PROP', '', 'space_data.shading.show_xray', '', {}
    if s in ('SELECT_VERT', 'SELECT_EDGE', 'SELECT_FACE'):
        t = s[7:]
        return 'OP', 'mesh.select_mode', '', '', {'type': t}
    if s == 'BLENDER_ADD_MENU':
        return 'OP', 'SPECIAL:ADD_MENU', '', '', {}
    if s.startswith('GIZMO_'):
        tool = {'MOVE': 'builtin.move', 'ROTATE': 'builtin.rotate', 'SCALE': 'builtin.scale',
                'ALL': 'builtin.transform'}.get(s[6:], 'builtin.move')
        return 'OP', 'TOOL:' + tool, '', '', {}
    if s.startswith('ORIENTATION_'):
        return 'PROP', '', 'scene.transform_orientation_slots[0].type', json.dumps(s[12:]), {}
    if s == 'PROPERTIES_OBJECT':
        return 'OP', 'SPECIAL:OBJECT_PROPERTIES', '', '', {}
    if s.startswith('SMART_SELECT_'):
        return 'OP', 'SPECIAL:' + s, '', '', {}
    return 'OP', op, '', '', {}


def migrate_legacy(data):
    """Turn every v0.0.18 page into its own quad set. Triggers start disabled except the
    Default page, which keeps the old keyboard shortcut."""
    if not isinstance(data.get('items'), list):
        raise ValueError('Invalid v0.0.18 file')
    pages = data.get('pages') or ['Default']
    sc = data.get('shortcut', {})
    sets, items = [], []
    page_set = {}
    for n, page in enumerate(pages):
        sid = 'legacy_' + uid()
        page_set[page] = sid
        key = sc.get('key', 'Q') if page == 'Default' else 'NONE'
        if key not in {k[0] for k in TRIGGER_KEYS}:
            key = 'NONE'
        sets.append(dict(uid=sid, name='Imported · ' + page, enabled=False,
                         key=key, ctrl=bool(sc.get('ctrl', True)), shift=bool(sc.get('shift', True)),
                         alt=bool(sc.get('alt', False)), oskey=bool(sc.get('oskey', False)), in_view3d=True,
                         in_anim=False, show_all=True,
                         title_TL='Q1', title_TR='Q2', title_BL='Q3', title_BR='Q4'))
    for rec in data['items']:
        if not isinstance(rec, dict):
            continue
        page = rec.get('page', 'Default')
        if page not in page_set:
            continue
        mode = rec.get('mode', 'OBJECT')
        if mode == 'OTHER' or mode not in MODE_IDS:
            mode = 'GLOBAL'
        kind = rec.get('kind', 'OP')
        op = rec.get('operator', '') or ''
        path = value = ''
        try:
            kwargs = json.loads(rec.get('kwargs', '{}') or '{}')
        except ValueError:
            kwargs = {}
        if kind == 'OP' and op.startswith('SPECIAL:'):
            kind, op, path, value, extra = _legacy_special(op)
            kwargs.update(extra)
        items.append(dict(
            uid=rec.get('uid') or uid(), set_id=page_set[page], mode=mode,
            quad=LEGACY_QUAD.get(rec.get('quad', 'Q1'), 'TL'), parent=rec.get('parent', ''),
            kind=kind if kind in {'OP', 'SUB', 'SEP', 'PROP'} else 'OP',
            label=rec.get('label', ''), operator=op, kwargs=kwargs,
            invoke=bool(rec.get('invoke', True)), path=path, value=value,
            enabled=bool(rec.get('enabled', True)),
            shortcut_key=rec.get('shortcut_key', 'NONE') if rec.get('shortcut_key', 'NONE') in SHORTCUT_KEY_IDS else 'NONE',
            shortcut_ctrl=bool(rec.get('shortcut_ctrl')), shortcut_shift=bool(rec.get('shortcut_shift')),
            shortcut_alt=bool(rec.get('shortcut_alt')), shortcut_oskey=bool(rec.get('shortcut_oskey'))))
    return {'format': FORMAT, 'version': VERSION, 'sets': sets, 'items': items}


def append_legacy(path):
    """Import a v0.0.18 file next to the current sets (non-destructive)."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if data.get('format') == FORMAT and data.get('version', 1) >= 2:
        raise ValueError('This is already a v2 file; use Load instead')
    converted = migrate_legacy(data)
    validate(converted)
    p = prefs()
    # The old default trigger may clash with an existing set; keep it but report.
    _state['loading'] = True
    try:
        for rec in converted['sets']:
            assign(p.sets.add(), rec, SET_FIELDS)
        for rec in converted['items']:
            assign(p.items.add(), rec, ITEM_FIELDS)
    finally:
        _state['loading'] = False
    return len(converted['sets']), len(converted['items'])


classes = (BMAXQUAD_PG_item, BMAXQUAD_PG_set, BMAXQUAD_PG_ui)
