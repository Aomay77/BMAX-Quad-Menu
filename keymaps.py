"""Keymap registration for quad set triggers and per-item shortcuts.

Blender's right-click context menus live in the mode keymaps (Object Mode, Mesh, ...),
which are evaluated before the generic '3D View' keymap. Triggers are therefore added
to every mode keymap so a right-click quad really replaces the context menu."""

import bpy

from .model import prefs

VIEW3D_KEYMAPS = ('3D View', 'Object Mode', 'Mesh', 'Curve', 'Curves', 'Armature', 'Metaball',
                  'Lattice', 'Font', 'Pose', 'Vertex Paint', 'Weight Paint', 'Image Paint',
                  'Sculpt', 'Sculpt Curves', 'Particle', 'Point Cloud',
                  'Grease Pencil Edit Mode', 'Grease Pencil Paint Mode',
                  'Grease Pencil Sculpt Mode', 'Grease Pencil Weight Paint',
                  'Grease Pencil Vertex Paint')
ANIM_KEYMAPS = ('Dopesheet', 'Graph Editor')

MODE_KEYMAP = {
    'GLOBAL': ('3D View',), 'OBJECT': ('Object Mode',), 'EDIT_MESH': ('Mesh',),
    'EDIT_CURVE': ('Curve',), 'EDIT_SURFACE': ('Curve',), 'EDIT_CURVES': ('Curves',),
    'EDIT_TEXT': ('Font',), 'EDIT_ARMATURE': ('Armature',), 'EDIT_METABALL': ('Metaball',),
    'EDIT_LATTICE': ('Lattice',), 'EDIT_GREASE_PENCIL': ('Grease Pencil Edit Mode',),
    'POSE': ('Pose',), 'SCULPT': ('Sculpt',), 'SCULPT_CURVES': ('Sculpt Curves',),
    'PAINT_VERTEX': ('Vertex Paint',), 'PAINT_WEIGHT': ('Weight Paint',),
    'PAINT_TEXTURE': ('Image Paint',), 'PAINT_GREASE_PENCIL': ('Grease Pencil Paint Mode',),
    'PARTICLE': ('Particle',), 'ANIMATION': ANIM_KEYMAPS,
}

_registered = []
_state = {'pending': False}


def _space_region(name):
    """Look up the space/region of a keymap from Blender's default keyconfig."""
    wm = bpy.context.window_manager
    default = wm.keyconfigs.default if wm else None
    if default is not None:
        km = default.keymaps.get(name)
        if km is not None:
            return km.space_type, km.region_type
    fallback = {'3D View': ('VIEW_3D', 'WINDOW'), 'Dopesheet': ('DOPESHEET_EDITOR', 'WINDOW'),
                'Graph Editor': ('GRAPH_EDITOR', 'WINDOW')}
    return fallback.get(name, (None, None))


def _keymap(kc, name):
    space, region = _space_region(name)
    if space is None:
        return None
    return kc.keymaps.new(name=name, space_type=space, region_type=region)


def unregister_keymaps():
    for km, kmi in _registered:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError, ValueError):
            pass
    _registered.clear()


def refresh():
    unregister_keymaps()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm else None
    if kc is None:
        return
    p = prefs()
    for s in p.sets:
        if not s.enabled or s.key == 'NONE':
            continue
        names = (VIEW3D_KEYMAPS if s.in_view3d else ()) + (ANIM_KEYMAPS if s.in_anim else ())
        for name in names:
            km = _keymap(kc, name)
            if km is None:
                continue
            kmi = km.keymap_items.new('bmaxquad.show', s.key, 'PRESS',
                                      ctrl=s.ctrl, shift=s.shift, alt=s.alt, oskey=s.oskey)
            kmi.properties.set_id = s.uid
            _registered.append((km, kmi))
    seen = set()
    for it in p.items:
        if not it.enabled or it.kind not in {'OP', 'PROP'} or it.shortcut_key == 'NONE':
            continue
        for name in MODE_KEYMAP.get(it.mode, ()):
            ident = (name, it.shortcut_key, it.shortcut_ctrl, it.shortcut_shift, it.shortcut_alt,
                     it.shortcut_oskey)
            if ident in seen:
                continue
            seen.add(ident)
            km = _keymap(kc, name)
            if km is None:
                continue
            kmi = km.keymap_items.new('bmaxquad.invoke_item', it.shortcut_key, 'PRESS',
                                      ctrl=it.shortcut_ctrl, shift=it.shortcut_shift,
                                      alt=it.shortcut_alt, oskey=it.shortcut_oskey)
            kmi.properties.uid = it.uid
            _registered.append((km, kmi))


def _deferred():
    _state['pending'] = False
    try:
        refresh()
    except Exception as exc:
        print('BMAX Quad: keymap refresh failed:', exc)
    return None


def schedule_refresh():
    if not _state['pending']:
        _state['pending'] = True
        bpy.app.timers.register(_deferred, first_interval=0.3)


def conflicts(key, ctrl, shift, alt, oskey, keymap_names, ignore_idname='bmaxquad.'):
    """Best-effort list of existing bindings with the same key combination."""
    found = []
    wm = bpy.context.window_manager
    for kc in (wm.keyconfigs.user,):
        if kc is None:
            continue
        for name in keymap_names:
            km = kc.keymaps.get(name)
            if km is None:
                continue
            for kmi in km.keymap_items:
                if not kmi.active or kmi.type != key or kmi.value not in {'PRESS', 'CLICK'}:
                    continue
                if (bool(kmi.ctrl), bool(kmi.shift), bool(kmi.alt), bool(kmi.oskey)) != \
                        (ctrl, shift, alt, oskey):
                    continue
                if kmi.idname.startswith(ignore_idname):
                    continue
                label = '%s: %s' % (name, kmi.name or kmi.idname)
                if label not in found:
                    found.append(label)
    return found
