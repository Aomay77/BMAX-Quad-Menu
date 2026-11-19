"""Preferences (3ds Max 'Customize User Interface > Quads' + 'Advanced Quad Menu Options'),
in-Blender menu editor, sidebar panel and the 'Add to BMAX Quad Menu' button context entry."""

import ast
import json
import os
import re

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, StringProperty)
from bpy.types import AddonPreferences, Menu, Operator, Panel, UIList

from . import actions, keymaps, model
from .model import (ADDON, MAX_QUAD_NUMBER, QUADS, QUAD_IDS, SHORTCUT_KEY_IDS, prefs, schedule_save,
                    uid)


def _keymap_update(self, context):
    schedule_save()
    keymaps.schedule_refresh()


def color(name, default):
    return FloatVectorProperty(name=name, subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0,
                               default=default, update=schedule_save)


# --------------------------------------------------------------------------
# Preferences
# --------------------------------------------------------------------------
class BMAXQUAD_AP_prefs(AddonPreferences):
    bl_idname = ADDON

    sets: CollectionProperty(type=model.BMAXQUAD_PG_set)
    items: CollectionProperty(type=model.BMAXQUAD_PG_item)
    active_set_index: IntProperty(default=0)
    active_item_index: IntProperty(default=0)
    show_conditions: BoolProperty(name='Show When', default=False)

    # Fonts group
    menu_font_size: IntProperty(name='Menu Font Size', default=12, min=8, max=30, update=schedule_save)
    title_font_size: IntProperty(name='Title Font Size', default=11, min=8, max=30, update=schedule_save)
    font_path: StringProperty(name='Font File', subtype='FILE_PATH', update=schedule_save,
                              description='Optional .ttf/.otf; empty uses the Blender UI font')
    # Display group
    vertical_margin: IntProperty(name='Vertical Margins', default=3, min=0, max=14, update=schedule_save)
    min_width: IntProperty(name='Minimum Quad Width', default=140, min=60, max=400, update=schedule_save)
    uniform_width: BoolProperty(name='Uniform Quad Width', default=False, update=schedule_save,
                                description='All quadrants use the width of the widest one')
    mirror_quads: BoolProperty(name='Mirror Quads', default=True, update=schedule_save,
                               description='Left quads right-justify their text toward the cursor')
    opacity: FloatProperty(name='Opacity Amount', default=1.0, min=0.2, max=1.0, update=schedule_save)
    show_shortcuts: BoolProperty(name='Show Hotkeys', default=True, update=schedule_save)
    unavailable: EnumProperty(name='Unavailable Commands', update=schedule_save, default='HIDE', items=[
        ('HIDE', 'Hide (3ds Max)', 'Items whose command is not available are hidden; empty quads disappear'),
        ('GREY', 'Grey Out', 'Show unavailable items dimmed')])
    # Positioning group
    reposition: BoolProperty(name='Reposition Quad When Off Screen', default=True, update=schedule_save)
    move_cursor: BoolProperty(name='Move Cursor When Repositioned', default=True, update=schedule_save)
    return_cursor: BoolProperty(name='Return Cursor After Repositioned', default=True, update=schedule_save)
    # Animation group
    animation: EnumProperty(name='Animation', default='NONE', update=schedule_save, items=[
        ('NONE', 'None', 'Quad menus open immediately'),
        ('FADE', 'Fade', 'Quads fade in counter-clockwise from Quad 1 (lower right)')])
    fade_steps: IntProperty(name='Steps', default=6, min=1, max=30, update=schedule_save)
    fade_pause: IntProperty(name='Pause (ms)', default=35, min=0, max=300, update=schedule_save)
    # Behaviour
    submenu_pause: IntProperty(name='Submenu Pause (ms)', default=120, min=0, max=1000,
                               update=schedule_save,
                               description='Delay before a submenu opens or switches on hover')
    use_last_executed: BoolProperty(name='Click Title to Repeat Last', default=True,
                                    update=schedule_save,
                                    description='Click a quad title to repeat the last command used in it')
    release_to_execute: BoolProperty(name='Hold, Move, Release to Execute', default=True,
                                     update=schedule_save)
    start_at_click: BoolProperty(
        name='Interactive Tools Start at Click Point', default=True, update=schedule_save,
        description='Before running an interactive command (Loop Cut, Knife, Extrude...), move the '
                    'mouse back to where you opened the quad menu, so the tool works on the '
                    'edge/face you right-clicked')
    starting_quad: EnumProperty(name='Starting Quadrant', items=QUADS, default='BR', update=schedule_save)
    # Colors group
    lock_colors: BoolProperty(name='Lock (same colors in all quads)', default=True, update=schedule_save)
    col_background: color('Background', (0.20, 0.20, 0.20, 0.97))
    col_border: color('Border', (0.06, 0.06, 0.06, 1.0))
    col_text: color('Text', (0.88, 0.88, 0.88, 1.0))
    col_disabled: color('Disabled Text', (0.45, 0.45, 0.45, 1.0))
    col_shortcut: color('Hotkey Text', (0.58, 0.62, 0.68, 1.0))
    col_title: color('Title Bar', (0.13, 0.13, 0.13, 1.0))
    col_title_text: color('Title Text', (0.90, 0.90, 0.90, 1.0))
    col_title_active: color('Title Bar (Active)', (0.30, 0.45, 0.68, 1.0))
    col_highlight: color('Highlight', (0.27, 0.42, 0.64, 1.0))
    col_last: color('Last Executed', (0.29, 0.29, 0.29, 1.0))
    col_title_active_TL: color('Quad 3 Title (Active)', (0.62, 0.42, 0.18, 1.0))
    col_title_active_TR: color('Quad 2 Title (Active)', (0.22, 0.52, 0.34, 1.0))
    col_title_active_BL: color('Quad 4 Title (Active)', (0.52, 0.30, 0.50, 1.0))
    col_title_active_BR: color('Quad 1 Title (Active)', (0.30, 0.45, 0.68, 1.0))
    col_highlight_TL: color('Quad 3 Highlight', (0.55, 0.38, 0.17, 1.0))
    col_highlight_TR: color('Quad 2 Highlight', (0.20, 0.46, 0.30, 1.0))
    col_highlight_BL: color('Quad 4 Highlight', (0.46, 0.27, 0.44, 1.0))
    col_highlight_BR: color('Quad 1 Highlight', (0.27, 0.42, 0.64, 1.0))

    def draw(self, context):
        draw_editor(self.layout, context, full=True)


# --------------------------------------------------------------------------
# Editor helpers
# --------------------------------------------------------------------------
def ui_state(context):
    return context.window_manager.bmaxquad_ui


def active_set(p=None):
    p = p or prefs()
    if not p.sets:
        return None
    return p.sets[max(0, min(p.active_set_index, len(p.sets) - 1))]


def in_view(it, s, ui):
    return (s is not None and it.set_id == s.uid and it.mode == ui.mode and it.quad == ui.quad
            and it.parent == ui.parent)


def active_item(context):
    p = prefs()
    s = active_set(p)
    ui = ui_state(context)
    i = p.active_item_index
    if 0 <= i < len(p.items) and in_view(p.items[i], s, ui):
        return p.items[i]
    return None


def descendants(items, root_uid):
    out = {root_uid}
    changed = True
    while changed:
        changed = False
        for it in items:
            if it.parent in out and it.uid not in out:
                out.add(it.uid)
                changed = True
    return out


def trigger_text(s):
    if s.key == 'NONE':
        return 'no trigger'
    mods = [n for n, on in (('Ctrl', s.ctrl), ('Shift', s.shift), ('Alt', s.alt), ('OS', s.oskey)) if on]
    key = {'RIGHTMOUSE': 'RMB', 'BUTTON4MOUSE': 'Mouse4', 'BUTTON5MOUSE': 'Mouse5'}.get(
        s.key, s.key.replace('_', ' ').title())
    return '+'.join(mods + [key])


def save_now():
    model.save_config()


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------
class BMAXQUAD_UL_sets(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.prop(item, 'enabled', text='')
        row.label(text=item.name, icon='MENU_PANEL')
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text=trigger_text(item))


KIND_ICON = {'OP': 'PLAY', 'PROP': 'CHECKBOX_HLT', 'SUB': 'RIGHTARROW', 'DYN': 'FILE_REFRESH',
             'SEP': 'REMOVE'}


class BMAXQUAD_UL_items(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        s = active_set()
        ui = ui_state(context)
        flags = [self.bitflag_filter_item if in_view(it, s, ui) else 0 for it in items]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.prop(item, 'enabled', text='')
        if item.kind == 'SEP':
            row.label(text='──────────', icon='REMOVE')
            return
        label = item.label or '(untitled)'
        if item.kind == 'DYN':
            label += '  [%s]' % item.dynamic.title()
        row.label(text=label, icon=KIND_ICON.get(item.kind, 'DOT'))
        tags = []
        if item.object_types:
            tags.append('/'.join(sorted(item.object_types)).title())
        lv = [r for r in ('VERT', 'EDGE', 'FACE') if r in item.require]
        if lv:
            tags.append('/'.join(x.title() for x in lv))
        if item.caddy:
            tags.append('□')
        if item.shortcut_key != 'NONE':
            tags.append(actions._own_shortcut_text(item))
        if tags:
            sub = row.row()
            sub.alignment = 'RIGHT'
            sub.label(text='  '.join(tags))


class BMAXQUAD_MT_sets(Menu):
    bl_label = 'Quad Sets'
    bl_idname = 'BMAXQUAD_MT_sets'

    def draw(self, context):
        for i, s in enumerate(prefs().sets):
            op = self.layout.operator('bmaxquad.select_set', text='%s   (%s)' % (s.name, trigger_text(s)),
                                      icon='CHECKBOX_HLT' if s.enabled else 'CHECKBOX_DEHLT')
            op.index = i


class BMAXQUAD_MT_move_to_quad(Menu):
    bl_label = 'Move to Quadrant'
    bl_idname = 'BMAXQUAD_MT_move_to_quad'

    def draw(self, context):
        s = active_set()
        for q, name, _ in QUADS:
            title = getattr(s, 'title_' + q) if s else ''
            self.layout.operator('bmaxquad.item_to_quad', text='%s  (%s)' % (name, title)).quad = q


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def draw_editor(layout, context, full=True):
    p = prefs()
    ui = ui_state(context)
    if not any(s.enabled and s.key != 'NONE' for s in p.sets):
        box = layout.box()
        box.label(text='No quad set is active, so Blender menus are untouched.', icon='INFO')
        box.label(text='Quad Sets tab: pick a set, set its shortcut (Record), tick Trigger.')
    if full:
        row = layout.row()
        row.prop(ui, 'tab', expand=True)
        tab = ui.tab
    else:
        tab = 'MENUS'
    if tab == 'SETS':
        draw_sets(layout, context, p)
    elif tab == 'MENUS':
        draw_menus(layout, context, p, full)
    else:
        draw_options(layout, context, p)
    if full:
        box = layout.box()
        row = box.row(align=True)
        row.operator('bmaxquad.load', text='Load...', icon='IMPORT')
        row.operator('bmaxquad.save_as', text='Save As...', icon='EXPORT')
        row.operator('bmaxquad.open_folder', text='', icon='FILE_FOLDER')
        row = box.row(align=True)
        row.operator('bmaxquad.restore_missing', icon='FILE_REFRESH')
        row.operator('bmaxquad.factory_reset', icon='LOOP_BACK')
        box.operator('bmaxquad.import_legacy', text='Import old menus.json (v0.0.x / v0.1, adds as new sets)',
                     icon='FILE_PARENT')
        box.label(text='Settings auto-save to: ' + model.config_path(), icon='INFO')


def draw_sets(layout, context, p):
    row = layout.row()
    row.template_list('BMAXQUAD_UL_sets', '', p, 'sets', p, 'active_set_index', rows=8)
    col = row.column(align=True)
    col.operator('bmaxquad.set_add', text='', icon='ADD')
    col.operator('bmaxquad.set_remove', text='', icon='REMOVE')
    col.operator('bmaxquad.set_duplicate', text='', icon='DUPLICATE')
    col.separator()
    col.operator('bmaxquad.set_move', text='', icon='TRIA_UP').direction = 'UP'
    col.operator('bmaxquad.set_move', text='', icon='TRIA_DOWN').direction = 'DOWN'
    s = active_set(p)
    if s is None:
        return
    box = layout.box()
    box.prop(s, 'name')
    row = box.row(align=True)
    row.prop(s, 'enabled', text='Trigger')
    sub = row.row(align=True)
    sub.active = s.enabled
    sub.prop(s, 'ctrl', toggle=True)
    sub.prop(s, 'shift', toggle=True)
    sub.prop(s, 'alt', toggle=True)
    sub.prop(s, 'oskey', toggle=True)
    sub.prop(s, 'key', text='')
    row.operator('bmaxquad.record_trigger', text='', icon='REC')
    row = box.row(align=True)
    row.prop(s, 'in_view3d', toggle=True)
    row.prop(s, 'in_anim', toggle=True)
    box.prop(s, 'show_all')
    grid = box.grid_flow(columns=2, even_columns=True, align=True)
    grid.prop(s, 'title_TL')
    grid.prop(s, 'title_TR')
    grid.prop(s, 'title_BL')
    grid.prop(s, 'title_BR')
    # Conflict information
    if s.key == 'NONE':
        box.label(text='No trigger yet: choose a key or press Record, then tick Trigger.',
                  icon='INFO')
    if s.enabled and s.key != 'NONE':
        names = (keymaps.VIEW3D_KEYMAPS if s.in_view3d else ()) + (keymaps.ANIM_KEYMAPS if s.in_anim else ())
        found = keymaps.conflicts(s.key, s.ctrl, s.shift, s.alt, s.oskey, names)
        if found:
            col = box.column(align=True)
            col.label(text='Overrides these Blender bindings while enabled:', icon='ERROR')
            for f in found[:6]:
                col.label(text='   ' + f)
            if len(found) > 6:
                col.label(text='   ... and %d more' % (len(found) - 6))
        kc = context.window_manager.keyconfigs.active
        kp = getattr(kc, 'preferences', None)
        if s.key == 'RIGHTMOUSE' and kp is not None and getattr(kp, 'select_mouse', 'LEFT') == 'RIGHT':
            box.label(text='Your keymap selects with Right Click: right-click quads will '
                           'replace selection.', icon='ERROR')


def draw_quad_picker(layout, p, s, ui):
    counts = {q: 0 for q in QUAD_IDS}
    for it in p.items:
        if s and it.set_id == s.uid and it.mode == ui.mode and not it.parent and it.kind != 'SEP':
            counts[it.quad] += 1
    col = layout.column(align=True)
    for pair in (('TL', 'TR'), ('BL', 'BR')):
        row = col.row(align=True)
        for q in pair:
            title = getattr(s, 'title_' + q) if s else q
            op = row.operator('bmaxquad.pick_quad', depress=(ui.quad == q),
                              text='%s   Q%d · %d' % (title, MAX_QUAD_NUMBER[q], counts[q]))
            op.quad = q


def draw_menus(layout, context, p, full):
    ui = ui_state(context)
    s = active_set(p)
    if s is None:
        layout.label(text='No quad sets. Use Restore Missing Defaults.')
        return
    row = layout.row(align=True)
    row.menu('BMAXQUAD_MT_sets', text='%s  (%s)' % (s.name, trigger_text(s)), icon='MENU_PANEL')
    row.prop(ui, 'mode', text='')
    draw_quad_picker(layout, p, s, ui)

    has_root = any(it.set_id == s.uid and it.mode == ui.mode and it.quad == ui.quad and not it.parent
                   for it in p.items)
    row = layout.row(align=True)
    if ui.parent:
        chain = []
        lookup = {it.uid: it for it in p.items}
        cur = lookup.get(ui.parent)
        guard = 0
        while cur is not None and guard < 20:
            chain.append(cur.label)
            cur = lookup.get(cur.parent)
            guard += 1
        row.operator('bmaxquad.item_back', text='', icon='BACK')
        row.label(text='Root › ' + ' › '.join(reversed(chain)))
    else:
        row.label(text='Root of quad', icon='DOT')
        if not has_root and ui.mode not in {'GLOBAL', 'ANIMATION'}:
            row.label(text='(empty: uses Global)', icon='INFO')

    row = layout.row()
    row.template_list('BMAXQUAD_UL_items', '', p, 'items', p, 'active_item_index', rows=10 if full else 7)
    col = row.column(align=True)
    for kind, icon in (('OP', 'ADD'), ('PROP', 'CHECKBOX_HLT'), ('SUB', 'RIGHTARROW'),
                       ('DYN', 'FILE_REFRESH'), ('SEP', 'REMOVE')):
        col.operator('bmaxquad.item_add', text='', icon=icon).kind = kind
    col.separator()
    col.operator('bmaxquad.item_remove', text='', icon='X')
    col.operator('bmaxquad.item_duplicate', text='', icon='DUPLICATE')
    col.separator()
    col.operator('bmaxquad.item_move', text='', icon='TRIA_UP').direction = 'UP'
    col.operator('bmaxquad.item_move', text='', icon='TRIA_DOWN').direction = 'DOWN'
    col.separator()
    col.operator('bmaxquad.item_enter', text='', icon='TRIA_RIGHT')
    col.menu('BMAXQUAD_MT_move_to_quad', text='', icon='SNAP_GRID')

    it = active_item(context)
    if it is None:
        layout.label(text='Tip: right-click any Blender button > Add to BMAX Quad Menu', icon='INFO')
        return
    box = layout.box()
    box.prop(it, 'label')
    box.prop(it, 'kind')
    if it.kind == 'OP':
        row = box.row(align=True)
        row.prop(it, 'operator')
        row.operator('bmaxquad.pick_clipboard', text='', icon='PASTEDOWN')
        if it.operator and ':' not in it.operator and not actions.op_exists(it.operator):
            box.label(text='Unknown operator: ' + it.operator, icon='ERROR')
        box.prop(it, 'kwargs')
        row = box.row()
        row.prop(it, 'invoke')
        row.prop(it, 'caddy')
        sub = box.column(align=True)
        sub.label(text='Optional check mark:')
        r = sub.row(align=True)
        r.prop(it, 'path', text='')
        r.prop(it, 'value', text='')
    elif it.kind == 'PROP':
        box.prop(it, 'path')
        box.prop(it, 'value')
        state = actions.path_state(context, it.path, it.value) if it.path else None
        box.label(text='Not resolvable in this editor' if state is None else
                  ('Current: checked' if state else 'Current: unchecked'),
                  icon='INFO')
    elif it.kind == 'DYN':
        box.prop(it, 'dynamic')
    elif it.kind == 'SUB':
        box.operator('bmaxquad.item_enter', text='Edit Submenu Items', icon='TRIA_RIGHT')
    if it.kind != 'SEP':
        box.prop(p, 'show_conditions', icon='TRIA_DOWN' if p.show_conditions else 'TRIA_RIGHT',
                 emboss=False)
        if p.show_conditions:
            c = box.column()
            c.label(text='Object types (empty = any):')
            c.grid_flow(columns=4, align=True).prop(it, 'object_types')
            c.label(text='Show only when:')
            c.grid_flow(columns=4, align=True).prop(it, 'require')
    if it.kind in {'OP', 'PROP'}:
        sc = box.box()
        row = sc.row(align=True)
        row.label(text='Shortcut', icon='KEYINGSET')
        row.prop(it, 'shortcut_ctrl', toggle=True)
        row.prop(it, 'shortcut_shift', toggle=True)
        row.prop(it, 'shortcut_alt', toggle=True)
        row.prop(it, 'shortcut_oskey', toggle=True)
        row.prop(it, 'shortcut_key', text='')
        row.operator('bmaxquad.record_shortcut', text='', icon='REC').target = it.uid
        if it.shortcut_key != 'NONE':
            found = keymaps.conflicts(it.shortcut_key, it.shortcut_ctrl, it.shortcut_shift,
                                      it.shortcut_alt, it.shortcut_oskey,
                                      keymaps.MODE_KEYMAP.get(it.mode, ()) + ('Window', 'Screen'))
            if found:
                sc.label(text='Also bound: ' + ', '.join(found[:3]), icon='ERROR')


def draw_options(layout, context, p):
    col = layout.column()
    b = col.box()
    b.label(text='Colors', icon='COLOR')
    b.prop(p, 'starting_quad')
    b.prop(p, 'lock_colors')
    g = b.grid_flow(columns=2, even_columns=True)
    for k in ('col_background', 'col_border', 'col_text', 'col_disabled', 'col_shortcut',
              'col_title', 'col_title_text', 'col_last'):
        g.prop(p, k)
    if p.lock_colors:
        g.prop(p, 'col_title_active')
        g.prop(p, 'col_highlight')
    else:
        g2 = b.grid_flow(columns=2, even_columns=True)
        for q in ('TL', 'TR', 'BL', 'BR'):
            g2.prop(p, 'col_title_active_' + q)
            g2.prop(p, 'col_highlight_' + q)
    b = col.box()
    b.label(text='Display', icon='WINDOW')
    for k in ('uniform_width', 'mirror_quads', 'vertical_margin', 'min_width', 'opacity',
              'show_shortcuts', 'unavailable'):
        b.prop(p, k)
    b = col.box()
    b.label(text='Positioning', icon='ORIENTATION_CURSOR')
    b.prop(p, 'reposition')
    r = b.column()
    r.active = p.reposition
    r.prop(p, 'move_cursor')
    r2 = r.column()
    r2.active = p.move_cursor
    r2.prop(p, 'return_cursor')
    b = col.box()
    b.label(text='Fonts', icon='FONT_DATA')
    b.prop(p, 'title_font_size')
    b.prop(p, 'menu_font_size')
    b.prop(p, 'font_path')
    b = col.box()
    b.label(text='Animation', icon='ANIM')
    b.prop(p, 'animation')
    r = b.row()
    r.active = p.animation == 'FADE'
    r.prop(p, 'fade_steps')
    r.prop(p, 'fade_pause')
    b = col.box()
    b.label(text='Behavior', icon='MOUSE_RMB')
    b.prop(p, 'submenu_pause')
    b.prop(p, 'use_last_executed')
    b.prop(p, 'release_to_execute')
    b.prop(p, 'start_at_click')


# --------------------------------------------------------------------------
# Operators: editor navigation and editing
# --------------------------------------------------------------------------
class _Edit:
    bl_options = {'INTERNAL'}

    def done(self, context):
        save_now()
        keymaps.schedule_refresh()
        for w in context.window_manager.windows:
            for a in w.screen.areas:
                a.tag_redraw()
        return {'FINISHED'}


class BMAXQUAD_OT_select_set(_Edit, Operator):
    bl_idname = 'bmaxquad.select_set'
    bl_label = 'Edit Quad Set'
    index: IntProperty()

    def execute(self, context):
        p = prefs()
        p.active_set_index = self.index
        ui_state(context).parent = ''
        return {'FINISHED'}


class BMAXQUAD_OT_pick_quad(_Edit, Operator):
    bl_idname = 'bmaxquad.pick_quad'
    bl_label = 'Edit Quadrant'
    quad: StringProperty()

    def execute(self, context):
        ui = ui_state(context)
        ui.quad = self.quad
        ui.parent = ''
        return {'FINISHED'}


class BMAXQUAD_OT_item_add(_Edit, Operator):
    bl_idname = 'bmaxquad.item_add'
    bl_label = 'Add Quad Item'
    bl_description = 'Add a command / toggle / submenu / dynamic submenu / separator here'
    kind: StringProperty(default='OP')

    def execute(self, context):
        p = prefs()
        s = active_set(p)
        if s is None:
            return {'CANCELLED'}
        ui = ui_state(context)
        it = p.items.add()
        model._state['loading'] = True
        try:
            it.uid = uid()
            it.set_id, it.mode, it.quad, it.parent = s.uid, ui.mode, ui.quad, ui.parent
            it.kind = self.kind
            it.label = {'OP': 'New Command', 'PROP': 'New Toggle', 'SUB': 'New Submenu',
                        'DYN': 'Create', 'SEP': ''}[self.kind]
            if self.kind == 'PROP':
                it.path = 'space_data.shading.show_xray'
        finally:
            model._state['loading'] = False
        cur = p.active_item_index
        new_index = len(p.items) - 1
        if 0 <= cur < new_index and in_view(p.items[cur], s, ui):
            p.items.move(new_index, cur + 1)
            new_index = cur + 1
        p.active_item_index = new_index
        return self.done(context)


class BMAXQUAD_OT_item_remove(_Edit, Operator):
    bl_idname = 'bmaxquad.item_remove'
    bl_label = 'Remove Quad Item'

    def execute(self, context):
        p = prefs()
        it = active_item(context)
        if it is None:
            return {'CANCELLED'}
        doomed = descendants(p.items, it.uid)
        index = p.active_item_index
        for i in range(len(p.items) - 1, -1, -1):
            if p.items[i].uid in doomed:
                p.items.remove(i)
        s, ui = active_set(p), ui_state(context)
        cands = [i for i, x in enumerate(p.items) if in_view(x, s, ui)]
        p.active_item_index = min(cands, key=lambda i: abs(i - index)) if cands else 0
        return self.done(context)


class BMAXQUAD_OT_item_duplicate(_Edit, Operator):
    bl_idname = 'bmaxquad.item_duplicate'
    bl_label = 'Duplicate Quad Item'

    def execute(self, context):
        p = prefs()
        it = active_item(context)
        if it is None:
            return {'CANCELLED'}
        subtree = descendants(p.items, it.uid)
        recs = [model.item_to_dict(x) for x in p.items if x.uid in subtree]
        remap = {r['uid']: uid() for r in recs}
        src_index = p.active_item_index
        model._state['loading'] = True
        try:
            for r in recs:
                r['parent'] = remap.get(r['parent'], r['parent'])
                r['uid'] = remap[r['uid']]
                if r['uid'] == remap[it.uid]:
                    r['label'] += ' Copy'
                model.assign(p.items.add(), r, model.ITEM_FIELDS)
        finally:
            model._state['loading'] = False
        new_root = next(i for i, x in enumerate(p.items) if x.uid == remap[it.uid])
        p.items.move(new_root, src_index + 1)
        p.active_item_index = src_index + 1
        return self.done(context)


class BMAXQUAD_OT_item_move(_Edit, Operator):
    bl_idname = 'bmaxquad.item_move'
    bl_label = 'Move Quad Item'
    direction: StringProperty(default='UP')

    def execute(self, context):
        p = prefs()
        it = active_item(context)
        if it is None:
            return {'CANCELLED'}
        s, ui = active_set(p), ui_state(context)
        n = p.active_item_index
        step = -1 if self.direction == 'UP' else 1
        j = n + step
        while 0 <= j < len(p.items) and not in_view(p.items[j], s, ui):
            j += step
        if 0 <= j < len(p.items):
            p.items.move(n, j)
            p.active_item_index = j
        return self.done(context)


class BMAXQUAD_OT_item_enter(_Edit, Operator):
    bl_idname = 'bmaxquad.item_enter'
    bl_label = 'Enter Submenu'

    def execute(self, context):
        it = active_item(context)
        if it is None or it.kind != 'SUB':
            self.report({'INFO'}, 'Select a submenu first')
            return {'CANCELLED'}
        ui_state(context).parent = it.uid
        p = prefs()
        s, ui = active_set(p), ui_state(context)
        p.active_item_index = next((i for i, x in enumerate(p.items) if in_view(x, s, ui)), 0)
        return {'FINISHED'}


class BMAXQUAD_OT_item_back(_Edit, Operator):
    bl_idname = 'bmaxquad.item_back'
    bl_label = 'Parent Menu'

    def execute(self, context):
        p = prefs()
        ui = ui_state(context)
        cur = next((x for x in p.items if x.uid == ui.parent), None)
        ui.parent = cur.parent if cur else ''
        if cur is not None:
            p.active_item_index = next((i for i, x in enumerate(p.items) if x.uid == cur.uid), 0)
        return {'FINISHED'}


class BMAXQUAD_OT_item_to_quad(_Edit, Operator):
    bl_idname = 'bmaxquad.item_to_quad'
    bl_label = 'Move to Quadrant'
    quad: StringProperty()

    def execute(self, context):
        p = prefs()
        it = active_item(context)
        if it is None:
            return {'CANCELLED'}
        subtree = descendants(p.items, it.uid)
        model._state['loading'] = True
        try:
            for x in p.items:
                if x.uid in subtree:
                    x.quad = self.quad
            if it.parent:      # moving a nested item moves it to the root of the target quad
                it.parent = ''
        finally:
            model._state['loading'] = False
        ui = ui_state(context)
        ui.quad = self.quad
        ui.parent = ''
        return self.done(context)


# ---- sets -----------------------------------------------------------------
class BMAXQUAD_OT_set_add(_Edit, Operator):
    bl_idname = 'bmaxquad.set_add'
    bl_label = 'New Quad Set'

    def execute(self, context):
        p = prefs()
        model._state['loading'] = True
        try:
            s = p.sets.add()
            s.uid, s.name, s.key = uid(), 'New Quad Set', 'NONE'
            s.title_TL, s.title_TR, s.title_BL, s.title_BR = 'quad 3', 'quad 2', 'quad 4', 'quad 1'
        finally:
            model._state['loading'] = False
        p.active_set_index = len(p.sets) - 1
        return self.done(context)


class BMAXQUAD_OT_set_remove(_Edit, Operator):
    bl_idname = 'bmaxquad.set_remove'
    bl_label = 'Delete Quad Set'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        p = prefs()
        s = active_set(p)
        if s is None or len(p.sets) < 2:
            self.report({'WARNING'}, 'Keep at least one quad set')
            return {'CANCELLED'}
        model.backup('before_delete_set')
        sid = s.uid
        for i in range(len(p.items) - 1, -1, -1):
            if p.items[i].set_id == sid:
                p.items.remove(i)
        p.sets.remove(p.active_set_index)
        p.active_set_index = max(0, p.active_set_index - 1)
        ui_state(context).parent = ''
        return self.done(context)


class BMAXQUAD_OT_set_duplicate(_Edit, Operator):
    bl_idname = 'bmaxquad.set_duplicate'
    bl_label = 'Duplicate Quad Set'

    def execute(self, context):
        p = prefs()
        s = active_set(p)
        if s is None:
            return {'CANCELLED'}
        rec = {k: getattr(s, k) for k in model.SET_FIELDS}
        rec.update(uid=uid(), name=s.name + ' Copy', key='NONE')
        items = [model.item_to_dict(x) for x in p.items if x.set_id == s.uid]
        remap = {r['uid']: uid() for r in items}
        model._state['loading'] = True
        try:
            model.assign(p.sets.add(), rec, model.SET_FIELDS)
            for r in items:
                r['uid'] = remap[r['uid']]
                r['parent'] = remap.get(r['parent'], '')
                r['set_id'] = rec['uid']
                model.assign(p.items.add(), r, model.ITEM_FIELDS)
        finally:
            model._state['loading'] = False
        p.active_set_index = len(p.sets) - 1
        return self.done(context)


class BMAXQUAD_OT_set_move(_Edit, Operator):
    bl_idname = 'bmaxquad.set_move'
    bl_label = 'Move Quad Set'
    direction: StringProperty(default='UP')

    def execute(self, context):
        p = prefs()
        n = p.active_set_index
        j = n - 1 if self.direction == 'UP' else n + 1
        if 0 <= j < len(p.sets):
            p.sets.move(n, j)
            p.active_set_index = j
        return self.done(context)


# ---- files ----------------------------------------------------------------
class BMAXQUAD_OT_save_as(Operator):
    bl_idname = 'bmaxquad.save_as'
    bl_label = 'Save Quad Menus As'
    filepath: StringProperty(subtype='FILE_PATH', default='bmax_quad.json')
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            model.save_config(self.filepath)
        except OSError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Saved ' + self.filepath)
        return {'FINISHED'}


class BMAXQUAD_OT_load(Operator):
    bl_idname = 'bmaxquad.load'
    bl_label = 'Load Quad Menus'
    bl_description = 'Replace all quad sets with a saved file (current settings are backed up first)'
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            b = model.backup('before_load')
            model.load_config(self.filepath)
            model.save_config()
            keymaps.refresh()
        except Exception as exc:
            self.report({'ERROR'}, 'Load failed: %s' % exc)
            return {'CANCELLED'}
        ui_state(context).parent = ''
        self.report({'INFO'}, 'Loaded. Backup: ' + b)
        return {'FINISHED'}


class BMAXQUAD_OT_import_legacy(Operator):
    bl_idname = 'bmaxquad.import_legacy'
    bl_label = 'Import Old BMAX Menus'
    bl_description = 'Add each page of an old (v0.0.x / v0.1) menus.json as a new quad set (nothing is removed)'
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})

    def invoke(self, context, event):
        legacy = model.legacy_config_path()
        if os.path.isfile(legacy):
            self.filepath = legacy
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            model.backup('before_legacy_import')
            n_sets, n_items = model.append_legacy(self.filepath)
            model.save_config()
            keymaps.refresh()
        except Exception as exc:
            self.report({'ERROR'}, 'Import failed: %s' % exc)
            return {'CANCELLED'}
        self.report({'INFO'}, 'Imported %d sets, %d items' % (n_sets, n_items))
        return {'FINISHED'}


class BMAXQUAD_OT_factory_reset(Operator):
    bl_idname = 'bmaxquad.factory_reset'
    bl_label = 'Reset to 3ds Max Defaults'
    bl_description = 'Replace everything with the factory quad sets (a backup is written first)'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        b = model.backup('before_reset')
        model.load_factory()
        model.save_config()
        keymaps.refresh()
        ui_state(context).parent = ''
        self.report({'INFO'}, 'Factory quad sets restored. Backup: ' + b)
        return {'FINISHED'}


class BMAXQUAD_OT_restore_missing(Operator):
    bl_idname = 'bmaxquad.restore_missing'
    bl_label = 'Restore Missing Defaults'
    bl_description = 'Add factory sets and items that are missing. Never deletes or changes your items'

    def execute(self, context):
        model.backup('before_restore')
        n = model.restore_missing()
        model.save_config()
        keymaps.refresh()
        self.report({'INFO'}, 'Restored %d entries' % n if n else 'Nothing missing')
        return {'FINISHED'}


class BMAXQUAD_OT_open_folder(Operator):
    bl_idname = 'bmaxquad.open_folder'
    bl_label = 'Open Settings Folder'

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=model.config_dir())
        return {'FINISHED'}


# ---- picking ----------------------------------------------------------------
def parse_python_command(source):
    """Read Blender's 'Copy Python Command' safely (no eval)."""
    source = source.strip()
    if re.fullmatch(r'[A-Za-z_]\w*\.[A-Za-z_]\w*', source):
        return source, {}, None
    try:
        tree = ast.parse(source, mode='exec')
    except SyntaxError as exc:
        raise ValueError('Clipboard is not a Blender Python command') from exc
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Attribute)
             and isinstance(n.func.value.value, ast.Attribute)
             and isinstance(n.func.value.value.value, ast.Name)
             and n.func.value.value.value.id == 'bpy' and n.func.value.value.attr == 'ops']
    if len(calls) != 1:
        raise ValueError('Right-click a Blender button > Copy Python Command first')
    node = calls[0]
    op_id = node.func.value.attr + '.' + node.func.attr
    kwargs = {}
    for kw in node.keywords:
        if kw.arg is None:
            raise ValueError('**kwargs not supported')
        kwargs[kw.arg] = ast.literal_eval(kw.value)
        json.dumps(kwargs[kw.arg])
    invoke = None
    if node.args:
        try:
            mode = ast.literal_eval(node.args[0])
            if mode in {'INVOKE_DEFAULT', 'EXEC_DEFAULT'}:
                invoke = mode == 'INVOKE_DEFAULT'
        except (ValueError, SyntaxError):
            pass
    return op_id, kwargs, invoke


class BMAXQUAD_OT_pick_clipboard(_Edit, Operator):
    bl_idname = 'bmaxquad.pick_clipboard'
    bl_label = 'Paste Python Command'
    bl_description = 'Fill the command from the clipboard (right-click a button > Copy Python Command)'

    def execute(self, context):
        it = active_item(context)
        if it is None or it.kind != 'OP':
            self.report({'WARNING'}, 'Select a command item first')
            return {'CANCELLED'}
        try:
            op_id, kwargs, inv = parse_python_command(context.window_manager.clipboard)
            if not actions.op_exists(op_id):
                raise ValueError('Unknown operator ' + op_id)
        except (ValueError, TypeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        it.operator = op_id
        it.kwargs = json.dumps(kwargs, ensure_ascii=False)
        if inv is not None:
            it.invoke = inv
        return self.done(context)


# Map RNA struct types to safe context paths for property buttons.
POINTER_PATHS = {
    'View3DShading': 'space_data.shading', 'View3DOverlay': 'space_data.overlay',
    'SpaceView3D': 'space_data', 'ToolSettings': 'tool_settings', 'Scene': 'scene',
    'RenderSettings': 'scene.render', 'SceneEEVEE': 'scene.eevee', 'View3DCursor': 'scene.cursor',
    'TransformOrientationSlot': 'scene.transform_orientation_slots[0]',
    'MeshStatVis': 'tool_settings.statvis', 'UnifiedPaintSettings': 'tool_settings.unified_paint_settings',
}


def button_payload(context):
    """-> dict for a new item from the right-clicked button, or None."""
    btn = getattr(context, 'button_operator', None)
    if btn is not None:
        try:
            rna = btn.bl_rna
            ident = rna.identifier
            if '_OT_' not in ident:
                return None
            cat, act = ident.split('_OT_', 1)
            op_id = cat.lower() + '.' + act.lower()
            if not actions.op_exists(op_id):
                return None
            props = {}
            for prop in rna.properties:
                k = prop.identifier
                if k == 'rna_type' or prop.is_readonly or prop.type in {'POINTER', 'COLLECTION'}:
                    continue
                if hasattr(btn, 'is_property_set') and not btn.is_property_set(k):
                    continue
                v = getattr(btn, k)
                if prop.type == 'ENUM' and getattr(prop, 'is_enum_flag', False):
                    v = sorted(v)
                elif getattr(prop, 'is_array', False):
                    v = list(v)
                json.dumps(v)
                props[k] = v
            return dict(kind='OP', operator=op_id, kwargs=props, label=rna.name or op_id)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None
    ptr = getattr(context, 'button_pointer', None)
    prop = getattr(context, 'button_prop', None)
    if ptr is None or prop is None:
        return None
    try:
        sname = ptr.bl_rna.identifier
        base = POINTER_PATHS.get(sname)
        if base is None:
            ob = context.active_object
            if ob is not None and ptr == ob:
                base = 'selected_objects'
            elif ob is not None and ob.data is not None and ptr == ob.data:
                base = 'active_object.data'
        if base is None or getattr(prop, 'is_array', False):
            return None
        path = base + '.' + prop.identifier
        if prop.type == 'BOOLEAN':
            value = ''
        elif prop.type == 'ENUM' and getattr(prop, 'is_enum_flag', False):
            return None
        else:
            value = json.dumps(getattr(ptr, prop.identifier))
        label = prop.name or prop.identifier
        if prop.type == 'ENUM':
            cur = getattr(ptr, prop.identifier)
            names = {e.identifier: e.name for e in prop.enum_items}
            label = '%s: %s' % (label, names.get(cur, cur))
        return dict(kind='PROP', path=path, value=value, label=label)
    except (AttributeError, TypeError, ValueError, ReferenceError):
        return None


class BMAXQUAD_OT_add_from_button(Operator):
    bl_idname = 'bmaxquad.add_from_button'
    bl_label = 'Add to BMAX Quad Menu'
    bl_options = {'INTERNAL'}
    payload: StringProperty()

    def execute(self, context):
        if not self.payload:
            self.report({'WARNING'}, 'This button has no command or supported property')
            return {'CANCELLED'}
        p = prefs()
        s = active_set(p)
        if s is None:
            return {'CANCELLED'}
        ui = ui_state(context)
        data = json.loads(self.payload)
        model._state['loading'] = True
        try:
            it = p.items.add()
            it.uid = uid()
            it.set_id, it.mode, it.quad, it.parent = s.uid, ui.mode, ui.quad, ui.parent
            it.kind = data['kind']
            it.label = data.get('label', 'Command')
            it.operator = data.get('operator', '')
            it.kwargs = json.dumps(data.get('kwargs', {}), ensure_ascii=False)
            it.path = data.get('path', '')
            it.value = data.get('value', '')
        finally:
            model._state['loading'] = False
        p.active_item_index = len(p.items) - 1
        save_now()
        self.report({'INFO'}, 'Added "%s" to %s › %s › Q%d' % (
            it.label, s.name, ui.mode.replace('_', ' ').title(), MAX_QUAD_NUMBER[ui.quad]))
        return {'FINISHED'}


def button_context_menu(self, context):
    try:
        payload = button_payload(context)
        p = prefs()
        s = active_set(p)
        ui = ui_state(context)
    except Exception:
        return
    if s is None:
        return
    self.layout.separator()
    text = 'Add to BMAX Quad  (%s › %s › Q%d)' % (s.name.split(' [')[0],
                                                ui.mode.replace('_', ' ').title(),
                                                MAX_QUAD_NUMBER[ui.quad])
    op = self.layout.operator('bmaxquad.add_from_button', text=text, icon='ADD')
    op.payload = json.dumps(payload, ensure_ascii=False) if payload else ''


# ---- shortcut recording -------------------------------------------------------
class BMAXQUAD_OT_record_shortcut(Operator):
    bl_idname = 'bmaxquad.record_shortcut'
    bl_label = 'Record Shortcut'
    bl_description = 'Press a key combination (Esc cancels, Backspace clears)'
    target: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        self.report({'INFO'}, 'Press a key combination... (Esc cancels, Backspace clears)')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type == 'ESC':
            return {'CANCELLED'}
        it = next((x for x in prefs().items if x.uid == self.target), None)
        if it is None:
            return {'CANCELLED'}
        if event.type == 'BACK_SPACE':
            it.shortcut_key = 'NONE'
            return {'FINISHED'}
        if event.type not in SHORTCUT_KEY_IDS or event.type == 'NONE':
            return {'RUNNING_MODAL'}
        it.shortcut_key = event.type
        it.shortcut_ctrl = event.ctrl
        it.shortcut_shift = event.shift
        it.shortcut_alt = event.alt
        it.shortcut_oskey = event.oskey
        self.report({'INFO'}, 'Shortcut set for ' + it.label)
        return {'FINISHED'}


class BMAXQUAD_OT_record_trigger(Operator):
    bl_idname = 'bmaxquad.record_trigger'
    bl_label = 'Record Quad Set Shortcut'
    bl_description = ('Press any key or mouse button with modifiers to open this quad set '
                      '(Esc cancels). The set is switched on')

    def invoke(self, context, event):
        self.report({'INFO'}, 'Press the shortcut for this quad set... (Esc cancels)')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type == 'ESC':
            return {'CANCELLED'}
        if event.type not in model.TRIGGER_KEY_IDS:
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and not (event.ctrl or event.shift or event.alt or event.oskey):
            return {'RUNNING_MODAL'}   # plain left click would block selection
        s = active_set()
        if s is None:
            return {'CANCELLED'}
        s.key = event.type
        s.ctrl, s.shift, s.alt, s.oskey = event.ctrl, event.shift, event.alt, event.oskey
        s.enabled = True
        self.report({'INFO'}, '%s: %s' % (s.name, trigger_text(s)))
        for a in context.screen.areas:
            a.tag_redraw()
        return {'FINISHED'}


# ---- sidebar -------------------------------------------------------------------
class BMAXQUAD_OT_preview(Operator):
    bl_idname = 'bmaxquad.preview'
    bl_label = 'Open Quad Menu'
    bl_description = 'Open the quad set being edited in the middle of the viewport'

    def invoke(self, context, event):
        s = active_set()
        if s is None:
            return {'CANCELLED'}
        return bpy.ops.bmaxquad.show('INVOKE_DEFAULT', set_id=s.uid)


class BMAXQUAD_PT_sidebar(Panel):
    bl_label = 'BMAX Quad Menu'
    bl_idname = 'BMAXQUAD_PT_sidebar'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BMAX Quad'

    def draw(self, context):
        layout = self.layout
        layout.operator('bmaxquad.preview', icon='MENU_PANEL')
        draw_editor(layout, context, full=False)
        layout.operator('preferences.addon_show', text='All Settings...',
                        icon='PREFERENCES').module = ADDON


classes = (
    BMAXQUAD_AP_prefs, BMAXQUAD_UL_sets, BMAXQUAD_UL_items, BMAXQUAD_MT_sets,
    BMAXQUAD_MT_move_to_quad,
    BMAXQUAD_OT_select_set, BMAXQUAD_OT_pick_quad, BMAXQUAD_OT_item_add, BMAXQUAD_OT_item_remove,
    BMAXQUAD_OT_item_duplicate, BMAXQUAD_OT_item_move, BMAXQUAD_OT_item_enter,
    BMAXQUAD_OT_item_back, BMAXQUAD_OT_item_to_quad,
    BMAXQUAD_OT_set_add, BMAXQUAD_OT_set_remove, BMAXQUAD_OT_set_duplicate, BMAXQUAD_OT_set_move,
    BMAXQUAD_OT_save_as, BMAXQUAD_OT_load, BMAXQUAD_OT_import_legacy, BMAXQUAD_OT_factory_reset,
    BMAXQUAD_OT_restore_missing, BMAXQUAD_OT_open_folder, BMAXQUAD_OT_pick_clipboard,
    BMAXQUAD_OT_add_from_button, BMAXQUAD_OT_record_shortcut, BMAXQUAD_OT_record_trigger,
    BMAXQUAD_OT_preview,
    BMAXQUAD_PT_sidebar,
)
