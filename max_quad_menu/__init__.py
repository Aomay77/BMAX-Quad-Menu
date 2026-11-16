bl_info = {
    "name": "BMAX Quad Menu",
    "author": "BMAX Quad Menu contributors",
    "version": (0, 1, 0),
    "blender": (5, 3, 0),
    "location": "3D View / Dope Sheet / Timeline / Graph Editor",
    "description": "Autodesk-inspired contextual Quad layout; mode switching, Add menu and native gizmos",
    "category": "3D View",
}

import bpy
import ast
import re
import blf
import gpu
import json
import math
import os
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, StringProperty)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup, UIList
from gpu_extras.batch import batch_for_shader

ADDON = __package__ or __name__
MODES = [
    ('GLOBAL', 'Global', 'Fallback for all modes'),
    ('ANIMATION', 'Animation Editors (Dope / Timeline / Graph)', 'One shared menu preset, automatically filtered by editor'),
    ('OBJECT', 'Object', ''), ('EDIT_MESH', 'Edit Mesh', ''),
    ('EDIT_CURVE', 'Edit Curve', ''), ('EDIT_SURFACE', 'Edit Surface', ''),
    ('EDIT_ARMATURE', 'Edit Armature', ''), ('EDIT_LATTICE', 'Edit Lattice', ''),
    ('EDIT_TEXT', 'Edit Text', ''), ('SCULPT', 'Sculpt', ''),
    ('PAINT_VERTEX', 'Vertex Paint', ''), ('PAINT_WEIGHT', 'Weight Paint', ''),
    ('PAINT_TEXTURE', 'Texture Paint', ''), ('POSE', 'Pose', ''),
    ('PARTICLE', 'Particle Edit', ''), ('OTHER', 'Other', ''),
]
QUADS = [('Q1', 'Top left', ''), ('Q2', 'Top right', ''),
         ('Q3', 'Bottom left', ''), ('Q4', 'Bottom right', '')]
KINDS = [('OP', 'Blender Operator', ''), ('SUB', 'Submenu', ''),
         ('SEP', 'Separator', '')]
# Keep the enum numbers used by v0.0.18 in saved Blender preferences.
LEGACY_TRIGGER_KEYS = (
    'Q', 'W', 'E', 'R', 'T', 'A', 'S', 'D', 'F', 'SPACE', 'ACCENT_GRAVE',
    'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12',
)
DIGIT_KEYS = dict(zip('0123456789', (
    'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE',
    'SIX', 'SEVEN', 'EIGHT', 'NINE',
)))
LEGACY_COMMAND_KEYS = (
    ('NONE',) + tuple('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + tuple(DIGIT_KEYS.values()) +
    ('SPACE', 'TAB', 'ACCENT_GRAVE', 'MINUS', 'EQUAL', 'LEFT_BRACKET',
     'RIGHT_BRACKET', 'SEMI_COLON', 'COMMA', 'PERIOD', 'SLASH',
     'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12',
     'F13', 'F14', 'F15', 'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
     'BUTTON4MOUSE', 'BUTTON5MOUSE')
)

# Blender 5.3 groups physical keyboard events between A and TEXTINPUT.
KEYMAP_EVENTS = tuple(bpy.types.KeyMapItem.bl_rna.properties['type'].enum_items)
EVENT_IDS = tuple(event.identifier for event in KEYMAP_EVENTS)
KEYBOARD_IDS = EVENT_IDS[EVENT_IDS.index('A'):EVENT_IDS.index('TEXTINPUT')]
COMMAND_IDS = frozenset(KEYBOARD_IDS) | frozenset(LEGACY_COMMAND_KEYS[1:])
MODIFIER_KEYS = frozenset({
    'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT',
    'LEFT_ALT', 'RIGHT_ALT', 'OSKEY', 'HYPER',
})


def shortcut_enum(legacy, allowed):
    numbers = {key: number for number, key in enumerate(legacy)}
    return [
        (event.identifier, event.name, event.description,
         numbers.get(event.identifier, len(legacy) + index))
        for index, event in enumerate(KEYMAP_EVENTS)
        if event.identifier in allowed
    ]


KEYS = shortcut_enum(LEGACY_TRIGGER_KEYS, KEYBOARD_IDS)
KEY_LABELS = {key: label for key, label, *_ in KEYS}
COMMAND_KEYS = shortcut_enum(LEGACY_COMMAND_KEYS, COMMAND_IDS | {'NONE'})

# Items: (mode, quad, parent submenu label path, label, operator or submenu marker, kwargs)
# Parent paths are resolved into stable IDs at preset construction time.
# Autodesk-inspired layout based on the 3ds Max 2025 menu system and quad menu
# documentation. Blender-native operators are used, not 3ds Max code.
# Q1 = selection/editing, Q2 = display, Q3 = create/model/mode, Q4 = transform/object.
PRESETS = [
    # Shared viewport utilities.
    ('GLOBAL','Q1','', 'Undo', 'ed.undo', {}),
    ('GLOBAL','Q1','', 'Redo', 'ed.redo', {}),
    ('GLOBAL','Q1','', 'Select All', 'SPECIAL:SMART_SELECT_ALL', {}),
    ('GLOBAL','Q1','', 'Invert Selection', 'SPECIAL:SMART_SELECT_INVERT', {}),
    ('GLOBAL','Q1','', 'View Selected', 'view3d.view_selected', {'use_all_regions':False}),
    ('GLOBAL','Q2','', 'Viewport Shading', '>',''),
    ('GLOBAL','Q2','Viewport Shading', 'Wireframe', 'SPECIAL:SHADING_WIREFRAME', {}),
    ('GLOBAL','Q2','Viewport Shading', 'Solid', 'SPECIAL:SHADING_SOLID', {}),
    ('GLOBAL','Q2','Viewport Shading', 'Material Preview', 'SPECIAL:SHADING_MATERIAL', {}),
    ('GLOBAL','Q2','Viewport Shading', 'Rendered', 'SPECIAL:SHADING_RENDERED', {}),
    ('GLOBAL','Q2','', 'Toggle X-Ray', 'SPECIAL:XRAY', {}),
    ('GLOBAL','Q2','', 'Isolate / Local View', 'view3d.localview', {}),
    ('GLOBAL','Q2','', 'Frame All', 'view3d.view_all', {'center':False}),
    ('GLOBAL','Q3','', 'Add (Blender Menu)', 'SPECIAL:BLENDER_ADD_MENU', {}),
    ('GLOBAL','Q4','', 'Search Commands', 'wm.search_menu', {}),

    # Object mode: select / display / organize / transform.
    ('OBJECT','Q1','', 'Selection', '>',''),
    ('OBJECT','Q1','Selection', 'Select All', 'object.select_all', {'action':'SELECT'}),
    ('OBJECT','Q1','Selection', 'Invert Selection', 'object.select_all', {'action':'INVERT'}),
    ('OBJECT','Q1','Selection', 'Select by Type', 'object.select_by_type', {'type':'MESH'}),
    ('OBJECT','Q1','Selection', 'Select Linked', 'object.select_linked', {'type':'OBDATA'}),
    ('OBJECT','Q1','', 'Duplicate', 'object.duplicate_move', {}),
    ('OBJECT','Q1','', 'Linked Duplicate', 'object.duplicate_move_linked', {}),
    ('OBJECT','Q2','', 'Visibility', '>',''),
    ('OBJECT','Q2','Visibility', 'Hide Selected', 'object.hide_view_set', {'unselected':False}),
    ('OBJECT','Q2','Visibility', 'Hide Unselected', 'object.hide_view_set', {'unselected':True}),
    ('OBJECT','Q2','Visibility', 'Unhide All', 'object.hide_view_clear', {}),
    ('OBJECT','Q2','', 'Viewport Shading', '>',''),
    ('OBJECT','Q2','Viewport Shading', 'Wireframe', 'SPECIAL:SHADING_WIREFRAME', {}),
    ('OBJECT','Q2','Viewport Shading', 'Solid', 'SPECIAL:SHADING_SOLID', {}),
    ('OBJECT','Q2','Viewport Shading', 'Material Preview', 'SPECIAL:SHADING_MATERIAL', {}),
    ('OBJECT','Q2','Viewport Shading', 'Rendered', 'SPECIAL:SHADING_RENDERED', {}),
    ('OBJECT','Q2','', 'Toggle X-Ray', 'SPECIAL:XRAY', {}),
    ('OBJECT','Q2','', 'Isolate / Local View', 'view3d.localview', {}),
    ('OBJECT','Q3','', 'Create', '>',''),
    ('OBJECT','Q3','Create', 'Blender Add Menu / Add-ons', 'SPECIAL:BLENDER_ADD_MENU', {}),
    ('OBJECT','Q3','', 'Convert To', '>',''),
    ('OBJECT','Q3','Convert To', 'Mesh', 'object.convert', {'target':'MESH'}),
    ('OBJECT','Q3','Convert To', 'Curve', 'object.convert', {'target':'CURVE'}),
    ('OBJECT','Q3','', 'Modifiers', '>',''),
    ('OBJECT','Q3','Modifiers', 'Add Subdivision Surface', 'object.modifier_add', {'type':'SUBSURF'}),
    ('OBJECT','Q3','Modifiers', 'Add Mirror', 'object.modifier_add', {'type':'MIRROR'}),
    ('OBJECT','Q3','Modifiers', 'Add Bevel', 'object.modifier_add', {'type':'BEVEL'}),
    ('OBJECT','Q4','', 'Transform', '>',''),
    ('OBJECT','Q4','Transform', 'Move (interactive)', 'transform.translate', {}),
    ('OBJECT','Q4','Transform', 'Rotate (interactive)', 'transform.rotate', {}),
    ('OBJECT','Q4','Transform', 'Scale (interactive)', 'transform.resize', {}),
    ('OBJECT','Q4','', 'Apply', '>',''),
    ('OBJECT','Q4','Apply', 'Rotation & Scale', 'object.transform_apply', {'location':False,'rotation':True,'scale':True}),
    ('OBJECT','Q4','Apply', 'All Transforms', 'object.transform_apply', {'location':True,'rotation':True,'scale':True}),
    ('OBJECT','Q4','', 'Set Origin', '>',''),
    ('OBJECT','Q4','Set Origin', 'Origin to Geometry', 'object.origin_set', {'type':'ORIGIN_GEOMETRY'}),
    ('OBJECT','Q4','Set Origin', 'Geometry to Origin', 'object.origin_set', {'type':'GEOMETRY_ORIGIN'}),
    ('OBJECT','Q4','Set Origin', 'Origin to 3D Cursor', 'object.origin_set', {'type':'ORIGIN_CURSOR'}),
    ('OBJECT','Q4','', 'Join / Attach', 'object.join', {}),

    # Edit Mesh: similar mental model to Editable Poly.
    ('EDIT_MESH','Q1','', 'Selection Mode', '>',''),
    ('EDIT_MESH','Q1','Selection Mode', 'Vertex', 'SPECIAL:SELECT_VERT', {}),
    ('EDIT_MESH','Q1','Selection Mode', 'Edge', 'SPECIAL:SELECT_EDGE', {}),
    ('EDIT_MESH','Q1','Selection Mode', 'Face / Polygon', 'SPECIAL:SELECT_FACE', {}),
    ('EDIT_MESH','Q1','Selection Mode', 'Element (Linked)', 'mesh.select_linked', {}),
    ('EDIT_MESH','Q1','', 'Select Similar', 'mesh.select_similar', {}),
    ('EDIT_MESH','Q1','', 'Select Linked', 'mesh.select_linked', {}),
    ('EDIT_MESH','Q1','', 'Select All', 'mesh.select_all', {'action':'SELECT'}),
    ('EDIT_MESH','Q1','', 'Invert Selection', 'mesh.select_all', {'action':'INVERT'}),
    ('EDIT_MESH','Q2','', 'Visibility', '>',''),
    ('EDIT_MESH','Q2','Visibility', 'Hide Selected', 'mesh.hide', {'unselected':False}),
    ('EDIT_MESH','Q2','Visibility', 'Hide Unselected', 'mesh.hide', {'unselected':True}),
    ('EDIT_MESH','Q2','Visibility', 'Unhide All', 'mesh.reveal', {}),
    ('EDIT_MESH','Q2','', 'Normals', '>',''),
    ('EDIT_MESH','Q2','Normals', 'Recalculate Outside', 'mesh.normals_make_consistent', {'inside':False}),
    ('EDIT_MESH','Q2','Normals', 'Recalculate Inside', 'mesh.normals_make_consistent', {'inside':True}),
    ('EDIT_MESH','Q2','Normals', 'Flip Normals', 'mesh.flip_normals', {}),
    ('EDIT_MESH','Q2','', 'Toggle X-Ray', 'SPECIAL:XRAY', {}),
    ('EDIT_MESH','Q3','', 'Create / Extrude', '>',''),
    ('EDIT_MESH','Q3','Create / Extrude', 'Create Face', 'mesh.edge_face_add', {}),
    ('EDIT_MESH','Q3','Create / Extrude', 'Extrude Region', 'mesh.extrude_region_move', {}),
    ('EDIT_MESH','Q3','Create / Extrude', 'Extrude Edges', 'mesh.extrude_edges_move', {}),
    ('EDIT_MESH','Q3','Create / Extrude', 'Inset Faces', 'mesh.inset', {}),
    ('EDIT_MESH','Q3','', 'Cut / Divide', '>',''),
    ('EDIT_MESH','Q3','Cut / Divide', 'Knife / Cut Polygons', 'mesh.knife_tool', {}),
    ('EDIT_MESH','Q3','Cut / Divide', 'Loop Cut', 'mesh.loopcut_slide', {}),
    ('EDIT_MESH','Q3','Cut / Divide', 'Subdivide Edges', 'mesh.subdivide', {}),
    ('EDIT_MESH','Q3','', 'Bevel / Chamfer', '>',''),
    ('EDIT_MESH','Q3','Bevel / Chamfer', 'Bevel Edge / Chamfer', 'mesh.bevel', {'affect':'EDGES'}),
    ('EDIT_MESH','Q3','Bevel / Chamfer', 'Chamfer Vertices', 'mesh.bevel', {'affect':'VERTICES'}),
    ('EDIT_MESH','Q3','', 'Detach / Merge', '>',''),
    ('EDIT_MESH','Q3','Detach / Merge', 'Separate / Detach Selection', 'mesh.separate', {'type':'SELECTED'}),
    ('EDIT_MESH','Q3','Detach / Merge', 'Split', 'mesh.split', {}),
    ('EDIT_MESH','Q3','Detach / Merge', 'Merge at Center', 'mesh.merge', {'type':'CENTER'}),
    ('EDIT_MESH','Q4','', 'Move', 'transform.translate', {}),
    ('EDIT_MESH','Q4','', 'Rotate', 'transform.rotate', {}),
    ('EDIT_MESH','Q4','', 'Scale', 'transform.resize', {}),
    ('EDIT_MESH','Q4','', 'Duplicate / Clone', 'mesh.duplicate_move', {}),
    ('EDIT_MESH','Q4','', 'Flatten / Make Planar', '>',''),
    ('EDIT_MESH','Q4','Flatten / Make Planar', 'Flatten X', 'transform.resize', {'value':(0,1,1)}),
    ('EDIT_MESH','Q4','Flatten / Make Planar', 'Flatten Y', 'transform.resize', {'value':(1,0,1)}),
    ('EDIT_MESH','Q4','Flatten / Make Planar', 'Flatten Z', 'transform.resize', {'value':(1,1,0)}),

    # Other modes keep useful specialist tools without inventing 3ds Max support.
    ('EDIT_CURVE','Q1','', 'Select All', 'curve.select_all', {'action':'SELECT'}),
    ('EDIT_CURVE','Q2','', 'Hide Selected', 'curve.hide', {'unselected':False}),
    ('EDIT_CURVE','Q2','', 'Reveal', 'curve.reveal', {}),
    ('EDIT_CURVE','Q3','', 'Extrude', 'curve.extrude_move', {}),
    ('EDIT_CURVE','Q3','', 'Subdivide', 'curve.subdivide', {}),
    ('EDIT_CURVE','Q4','', 'Handle Type', 'curve.handle_type_set', {}),
    ('EDIT_ARMATURE','Q1','', 'Select All', 'armature.select_all', {'action':'SELECT'}),
    ('EDIT_ARMATURE','Q2','', 'Hide Selected', 'armature.hide', {'unselected':False}),
    ('EDIT_ARMATURE','Q2','', 'Reveal All', 'armature.reveal', {}),
    ('EDIT_ARMATURE','Q3','', 'Extrude Bone', 'armature.extrude_move', {}),
    ('EDIT_ARMATURE','Q3','', 'Subdivide', 'armature.subdivide', {}),
    ('EDIT_ARMATURE','Q4','', 'Symmetrize', 'armature.symmetrize', {}),
    ('POSE','Q1','', 'Copy Pose', 'pose.copy', {}),
    ('POSE','Q1','', 'Paste Pose', 'pose.paste', {}),
    ('POSE','Q2','', 'Hide Selected', 'pose.hide', {'unselected':False}),
    ('POSE','Q2','', 'Reveal All', 'pose.reveal', {}),
    ('POSE','Q3','', 'Insert Keyframe', 'anim.keyframe_insert_menu', {}),
    ('POSE','Q4','', 'Clear Transforms', 'pose.transforms_clear', {}),
    ('SCULPT','Q1','', 'Mask All', 'paint.mask_flood_fill', {'mode':'VALUE','value':1.0}),
    ('SCULPT','Q1','', 'Clear Mask', 'paint.mask_flood_fill', {'mode':'VALUE','value':0.0}),
    ('SCULPT','Q2','', 'Toggle X-Ray', 'SPECIAL:XRAY', {}),
    ('SCULPT','Q3','', 'Voxel Remesh', 'object.voxel_remesh', {}),
    ('SCULPT','Q4','', 'Search Sculpt Commands', 'wm.search_menu', {}),
]


# Autodesk Track View-inspired categories: Keys, Visibility/Navigation,
# Transform/Editing and Playback. The same preset is shared across all 3 editors.
# The editor-specific operation prefix and Blender poll determine availability.
ANIMATION_PRESETS = [
    ('ANIMATION','Q1','', 'Select Keys', '>',''),
    ('ANIMATION','Q1','Select Keys', 'Select All (Dope Sheet)', 'action.select_all', {'action':'SELECT'}),
    ('ANIMATION','Q1','Select Keys', 'Invert Selection (Dope Sheet)', 'action.select_all', {'action':'INVERT'}),
    ('ANIMATION','Q1','Select Keys', 'Select All (Graph Editor)', 'graph.select_all', {'action':'SELECT'}),
    ('ANIMATION','Q1','Select Keys', 'Invert Selection (Graph Editor)', 'graph.select_all', {'action':'INVERT'}),
    ('ANIMATION','Q1','', 'Duplicate Keys (Dope Sheet)', 'action.duplicate_move', {}),
    ('ANIMATION','Q1','', 'Duplicate Keys (Graph Editor)', 'graph.duplicate_move', {}),
    ('ANIMATION','Q1','', 'Delete Selected Keys (Dope Sheet)', 'action.delete', {}),
    ('ANIMATION','Q1','', 'Delete Selected Keys (Graph Editor)', 'graph.delete', {}),
    ('ANIMATION','Q2','', 'View / Navigation', '>',''),
    ('ANIMATION','Q2','View / Navigation', 'Frame All (Dope Sheet)', 'action.view_all', {}),
    ('ANIMATION','Q2','View / Navigation', 'Frame Selected (Dope Sheet)', 'action.view_selected', {}),
    ('ANIMATION','Q2','View / Navigation', 'Frame All (Graph Editor)', 'graph.view_all', {}),
    ('ANIMATION','Q2','View / Navigation', 'Frame Selected (Graph Editor)', 'graph.view_selected', {}),
    ('ANIMATION','Q2','', 'Markers', '>',''),
    ('ANIMATION','Q2','Markers', 'Add Marker', 'marker.add', {}),
    ('ANIMATION','Q2','Markers', 'Rename Marker', 'marker.rename', {}),
    ('ANIMATION','Q3','', 'Transform Keys', '>',''),
    ('ANIMATION','Q3','Transform Keys', 'Move Keys', 'transform.transform', {'mode':'TIME_TRANSLATE'}),
    ('ANIMATION','Q3','Transform Keys', 'Scale Keys', 'transform.transform', {'mode':'TIME_SCALE'}),
    ('ANIMATION','Q3','', 'Key Interpolation', '>',''),
    ('ANIMATION','Q3','Key Interpolation', 'Bezier (Dope Sheet)', 'action.interpolation_type', {'type':'BEZIER'}),
    ('ANIMATION','Q3','Key Interpolation', 'Linear (Dope Sheet)', 'action.interpolation_type', {'type':'LINEAR'}),
    ('ANIMATION','Q3','Key Interpolation', 'Constant (Dope Sheet)', 'action.interpolation_type', {'type':'CONSTANT'}),
    ('ANIMATION','Q3','Key Interpolation', 'Bezier (Graph Editor)', 'graph.interpolation_type', {'type':'BEZIER'}),
    ('ANIMATION','Q3','Key Interpolation', 'Linear (Graph Editor)', 'graph.interpolation_type', {'type':'LINEAR'}),
    ('ANIMATION','Q3','Key Interpolation', 'Constant (Graph Editor)', 'graph.interpolation_type', {'type':'CONSTANT'}),
    ('ANIMATION','Q4','', 'Playback / Time', '>',''),
    ('ANIMATION','Q4','Playback / Time', 'Play / Pause', 'screen.animation_play', {}),
    ('ANIMATION','Q4','Playback / Time', 'First Frame', 'screen.frame_jump', {'end':False}),
    ('ANIMATION','Q4','Playback / Time', 'Last Frame', 'screen.frame_jump', {'end':True}),
    ('ANIMATION','Q4','Playback / Time', 'Previous Keyframe', 'screen.keyframe_jump', {'next':False}),
    ('ANIMATION','Q4','Playback / Time', 'Next Keyframe', 'screen.keyframe_jump', {'next':True}),
    ('ANIMATION','Q4','', 'Markers / Timing', '>',''),
    ('ANIMATION','Q4','Markers / Timing', 'Add Marker', 'marker.add', {}),
    ('ANIMATION','Q4','Markers / Timing', 'Jump to Marker', 'screen.marker_jump', {'next':True}),
]



def prefs():
    return bpy.context.preferences.addons[ADDON].preferences


def config_path():
    directory = bpy.utils.user_resource('CONFIG', path='max_quad_menu', create=True)
    return os.path.join(directory, 'menus.json')


def uuid_str():
    return uuid.uuid4().hex


class MAXQUAD_PG_item(PropertyGroup):
    uid: StringProperty(name='ID')
    parent: StringProperty(name='Parent ID', default='')
    mode: EnumProperty(name='Mode', items=MODES, default='OBJECT')
    quad: EnumProperty(name='Quadrant', items=QUADS, default='Q1')
    kind: EnumProperty(name='Type', items=KINDS, default='OP')
    label: StringProperty(name='Label', default='New Command')
    operator: StringProperty(name='Operator ID', description='e.g. mesh.bevel, transform.translate, or SPECIAL:XRAY')
    kwargs: StringProperty(name='Properties JSON', default='{}', description='JSON object of operator keyword parameters')
    invoke: BoolProperty(name='Interactive / Invoke', default=True)
    show_parameters: BoolProperty(name='Show Parameters Near Command (F9)', default=True, description='When an operator finishes immediately and supports redo properties, show Blender Adjust Last Operation near the clicked menu entry')
    enabled: BoolProperty(name='Enabled', default=True)
    page: StringProperty(name='Page', default='Default')
    shortcut_key: EnumProperty(name='Shortcut Key', items=COMMAND_KEYS, default='NONE')
    shortcut_ctrl: BoolProperty(name='Ctrl', default=False)
    shortcut_shift: BoolProperty(name='Shift', default=False)
    shortcut_alt: BoolProperty(name='Alt', default=False)
    shortcut_oskey: BoolProperty(name='OS Key', default=False)


class MAXQUAD_AP_preferences(AddonPreferences):
    bl_idname = ADDON
    items: CollectionProperty(type=MAXQUAD_PG_item)
    active_index: IntProperty(default=0)
    active_page: StringProperty(name='Active Page', default='Default', update=lambda self,context: refresh_keymaps())
    pages_json: StringProperty(name='Pages', default='["Default"]')
    new_page_name: StringProperty(name='New Page Name', default='My Page')
    pick_command_text: StringProperty(name='Paste Python Command', default='', description='Paste the Blender Copy Python Command here, or use Pick Clipboard')
    shortcut: EnumProperty(name='Trigger key', items=KEYS, default='Q', update=lambda self, context: refresh_keymaps())
    ctrl: BoolProperty(name='Ctrl', default=True, update=lambda self, context: refresh_keymaps())
    shift: BoolProperty(name='Shift', default=True, update=lambda self, context: refresh_keymaps())
    alt: BoolProperty(name='Alt', default=False, update=lambda self, context: refresh_keymaps())
    oskey: BoolProperty(name='OS Key', default=False, update=lambda self, context: refresh_keymaps())
    font_size: IntProperty(name='Text size', default=12, min=9, max=24)
    item_height: IntProperty(name='Row height', default=23, min=17, max=40)
    panel_width: IntProperty(name='Minimum panel width', default=205, min=125, max=430)
    enable_animation_quad: BoolProperty(name='Enable Animation Editors Quad', default=True, update=lambda self, context: refresh_keymaps(), description='Show shared BMAX quad menu in Dope Sheet, Timeline and Graph Editor only')
    animation_right_click: BoolProperty(name='Use Right Click in Animation Editors', default=True, update=lambda self, context: refresh_keymaps(), description='Replaces native right-click context menus in those animation editors; disable to keep Blender original right click')
    animation_initialized: BoolProperty(default=False, options={'HIDDEN'})
    redo_popup_beside: BoolProperty(name='F9 Panel Beside Command', default=True, description='Place Blender native Adjust Last Operation beside the clicked BMAX menu, when supported')
    redo_popup_gap: IntProperty(name='F9 Panel Gap', default=18, min=0, max=100, description='Distance between BMAX menu edge and F9 panel cursor anchor')
    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        modifiers = [label for enabled, label in (
            (self.ctrl, 'Ctrl'), (self.shift, 'Shift'), (self.alt, 'Alt'), (self.oskey, 'OS Key')
        ) if enabled]
        shortcut_label = ' + '.join([*modifiers, KEY_LABELS[self.shortcut]])
        row.label(text='Trigger  ' + shortcut_label)
        row.operator('maxquad.shortcuts_record', text='Record Trigger', icon='EVENT_T').target_uid = ''
        layout.prop(self, 'font_size'); layout.prop(self, 'item_height'); layout.prop(self, 'panel_width')
        layout.operator('maxquad.save', icon='FILE_TICK')
        layout.operator('maxquad.reset', icon='LOOP_BACK')
        layout.operator('maxquad.apply_layout', icon='PRESET')
        layout.operator('maxquad.restore_defaults_safe', text='Restore Missing Built-in Defaults (Backup)', icon='FILE_REFRESH')
        layout.operator('maxquad.restore_mesh_tools', text='Restore Missing Mesh Tools (Backup)', icon='MOD_BEVEL')
        layout.separator()
        panel = layout.box()
        panel.label(text='Quad Menu Control Center', icon='PREFERENCES')
        panel.prop(self, 'active_page', text='Current Page')
        panel.prop(self, 'new_page_name', text='Page Name')
        row = panel.row(align=True)
        for action, label, icon in [('NEW','New Page','ADD'),('DUPLICATE','Duplicate','DUPLICATE'),('DELETE','Delete','REMOVE')]:
            op = row.operator('maxquad.page', text=label, icon=icon)
            op.action = action
        panel.label(text='Manage page/mode/quad commands below')
        panel.separator()
        panel.label(text='Animation Editors: Dope Sheet / Timeline / Graph Editor', icon='ACTION')
        panel.prop(self, 'enable_animation_quad')
        panel.prop(self, 'animation_right_click')
        panel.operator('maxquad.edit_animation', text='Edit Shared Animation Quad', icon='ACTION')
        editor = panel.box()
        editor.label(text='Command Editor / 指令編輯')
        draw_command_editor(editor, context, compact=True)
        row = panel.row(align=True)
        row.operator('maxquad.open_visual_editor', text='Open Drag-and-Drop Editor', icon='URL')
        row.operator('maxquad.export', text='Export JSON', icon='EXPORT')
        row = panel.row(align=True)
        row.operator('maxquad.import', text='Import Edited JSON', icon='IMPORT')
        row.operator('maxquad.save', text='Save', icon='FILE_TICK')
        panel.label(text='Visual editor opens locally in your web browser.')
        panel.label(text='After dragging, export JSON and import it here.')
        layout.label(text='Edit commands: 3D View > Sidebar > BMAX Quad')
        layout.label(text='JSON: ' + config_path())


class MAXQUAD_PG_ui(PropertyGroup):
    mode: EnumProperty(name='Mode', items=MODES, default='EDIT_MESH')
    quad: EnumProperty(name='Quadrant', items=QUADS, default='Q1')
    parent: StringProperty(name='Submenu ID', default='')


class MAXQUAD_OT_edit_animation(Operator):
    bl_idname = 'maxquad.edit_animation'
    bl_label = 'Edit Shared Animation Quad'
    bl_description = 'Switch the preferences editor to the shared Dope Sheet / Timeline / Graph configuration'
    def execute(self, context):
        ui = context.window_manager.maxquad_ui
        ui.mode = 'ANIMATION'
        ui.quad = 'Q1'
        ui.parent = ''
        prefs().active_index = next((i for i, it in enumerate(prefs().items) if it.mode == 'ANIMATION' and it.quad == 'Q1' and it.page == prefs().active_page), 0)
        return {'FINISHED'}


def item_to_dict(it):
    return {k: getattr(it,k) for k in ('uid','parent','mode','quad','kind','label','operator','kwargs','invoke','show_parameters','enabled','page','shortcut_key','shortcut_ctrl','shortcut_shift','shortcut_alt','shortcut_oskey')}


def populate(items, data):
    items.clear()
    for d in data:
        it = items.add()
        for k in ('uid','parent','mode','quad','kind','label','operator','kwargs','invoke','show_parameters','enabled','page','shortcut_key','shortcut_ctrl','shortcut_shift','shortcut_alt','shortcut_oskey'):
            if k in d:
                value = d[k]
                if k == 'shortcut_key' and isinstance(value, str):
                    value = DIGIT_KEYS.get(value, value)
                try: setattr(it,k,value)
                except (TypeError, ValueError): pass
        if not it.uid: it.uid = uuid_str()


def build_defaults():
    entries = []
    paths = {}
    for mode, quad, parent_label, label, operator, kwargs in PRESETS + ANIMATION_PRESETS:
        key = (mode,quad,parent_label)
        parent_uid = paths.get(key, '')
        if parent_label and not parent_uid:
            continue
        uid = uuid_str()
        is_sub = operator == '>'
        entries.append(dict(uid=uid,parent=parent_uid,mode=mode,quad=quad,
                            kind='SUB' if is_sub else 'OP',label=label,
                            operator='' if is_sub else operator,
                            kwargs=json.dumps(kwargs,ensure_ascii=False),
                            invoke=True,show_parameters=True,enabled=True,page='Default'))
        if is_sub: paths[(mode,quad,label)] = uid
    return entries


def save_json(path=None):
    p = prefs()
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {'format': 'BMAX Quad Menu', 'version': 1,
            'ui': {'font_size':p.font_size,'item_height':p.item_height,'panel_width':p.panel_width},
            'shortcut': {'key':p.shortcut,'ctrl':p.ctrl,'shift':p.shift,'alt':p.alt,
                         **({'oskey': True} if p.oskey else {})},
            'pages': json.loads(p.pages_json), 'active_page':p.active_page,
            'animation': {'enabled':p.enable_animation_quad, 'right_click':p.animation_right_click, 'initialized':p.animation_initialized},
            'items':[item_to_dict(it) for it in p.items]}
    with open(path,'w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2)


def load_json(path):
    with open(path,'r',encoding='utf-8') as f: data=json.load(f)
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):
        raise ValueError('Invalid BMAX Quad JSON (items must be a list)')
    for record in data['items']:
        if not isinstance(record,dict): raise ValueError('Invalid menu entry')
        if record.get('kind','OP') not in {'OP','SUB','SEP'}: raise ValueError('Invalid entry type')
        if record.get('mode','GLOBAL') not in {m[0] for m in MODES}: raise ValueError('Unknown mode')
        if record.get('quad','Q1') not in {'Q1','Q2','Q3','Q4'}: raise ValueError('Unknown quadrant')
        if record.get('kind') == 'OP':
            kwargs=record.get('kwargs','{}')
            if not isinstance(kwargs,str) or not isinstance(json.loads(kwargs),dict):
                raise ValueError('Operator properties must be JSON objects')
    p=prefs()
    populate(p.items,data['items'])
    animation_config = data.get('animation', {})
    if isinstance(animation_config, dict):
        p.enable_animation_quad = bool(animation_config.get('enabled', True))
        p.animation_right_click = bool(animation_config.get('right_click', True))
        p.animation_initialized = bool(animation_config.get('initialized', False))
    pages = data.get('pages', ['Default'])
    if not isinstance(pages,list) or not pages or any(not isinstance(n,str) or not n.strip() for n in pages):
        pages = ['Default']
    p.pages_json = json.dumps(list(dict.fromkeys(pages)), ensure_ascii=False)
    p.active_page = data.get('active_page','Default') if data.get('active_page','Default') in pages else pages[0]
    ui=data.get('ui',{})
    for k in ('font_size','item_height','panel_width'):
        if k in ui: setattr(p,k,ui[k])
    shortcut=data.get('shortcut',{})
    p.oskey = bool(shortcut.get('oskey', False))
    for k in ('key','ctrl','shift','alt'):
        target = 'shortcut' if k=='key' else k
        if k in shortcut:
            value = shortcut[k]
            if k == 'key':
                value = DIGIT_KEYS.get(value, value) if isinstance(value, str) else None
                if value not in KEYBOARD_IDS:
                    continue
            setattr(p,target,value)


def remove_legacy_default_delete():
    """Remove only the built-in Object/Q1/Delete entry from old saved menus.

    Do not delete renamed, non-default-page, or separately customized commands.
    """
    p = prefs()
    indices = [index for index, item in enumerate(p.items)
               if item.page == 'Default' and item.mode == 'OBJECT'
               and item.quad == 'Q1' and not item.parent
               and item.kind == 'OP' and item.label == 'Delete'
               and item.operator == 'object.delete']
    if not indices:
        return False
    for index in reversed(indices):
        p.items.remove(index)
    p.active_index = max(0, min(p.active_index, len(p.items) - 1))
    return True


class MAXQUAD_OT_save(Operator):
    bl_idname='maxquad.save'; bl_label='Save BMAX Quad Settings'; bl_options={'REGISTER'}
    def execute(self,context):
        try: save_json(); self.report({'INFO'},'BMAX Quad menu saved')
        except Exception as ex: self.report({'ERROR'},str(ex)); return {'CANCELLED'}
        return {'FINISHED'}


class MAXQUAD_OT_reset(Operator):
    bl_idname='maxquad.reset'; bl_label='Restore 3ds Max Style Defaults'; bl_options={'REGISTER'}
    def invoke(self,context,event): return context.window_manager.invoke_confirm(self,event)
    def execute(self,context):
        populate(prefs().items,build_defaults()); prefs().pages_json='["Default"]'; prefs().active_page='Default'; prefs().animation_initialized=True; save_json()
        self.report({'INFO'},'Default menu restored'); return {'FINISHED'}


class MAXQUAD_OT_apply_layout(Operator):
    bl_idname='maxquad.apply_layout'
    bl_label='Apply Autodesk-inspired Layout (backup first)'
    bl_description='Back up your current JSON, then replace default menu items with the new layout'
    bl_options={'REGISTER'}
    def invoke(self,context,event):
        return context.window_manager.invoke_confirm(self,event)
    def execute(self,context):
        try:
            # Capture unsaved in-memory modifications as well as existing presets.
            directory=os.path.dirname(config_path())
            os.makedirs(directory,exist_ok=True)
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup=os.path.join(directory,'menus_backup_'+stamp+'.json')
            save_json(backup)
            populate(prefs().items,build_defaults())
            prefs().animation_initialized=True
            prefs().pages_json='["Default"]'; prefs().active_page='Default'
            context.window_manager.maxquad_ui.parent=''
            prefs().active_index=0
            save_json()
            self.report({'INFO'}, 'Layout applied; previous configuration backed up')
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'},str(ex)); return {'CANCELLED'}


class MAXQUAD_OT_restore_mesh_tools(Operator):
    bl_idname = 'maxquad.restore_mesh_tools'
    bl_label = 'Restore Missing Mesh Modeling Tools'
    bl_description = ('Add missing Edit Mesh Q3 modeling groups and commands to the current page; '
                      'back up JSON first, without erasing existing commands')
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        p = prefs()
        page = p.active_page
        # Source of truth is PRESETS, not a manually maintained copy of operators.
        groups = [r for r in PRESETS if r[0] == 'EDIT_MESH' and r[1] == 'Q3']
        existing = [it for it in p.items if it.page == page and
                    it.mode == 'EDIT_MESH' and it.quad == 'Q3']
        pending = []
        mapping = {it.label: it.uid for it in existing
                   if it.kind == 'SUB' and not it.parent}
        for mode, quad, parent_label, label, command, kwargs in groups:
            if command == '>':
                if label in mapping:
                    continue
                uid = uuid_str()
                mapping[label] = uid
                pending.append(dict(uid=uid, parent='', mode=mode, quad=quad,
                                    page=page, kind='SUB', label=label,
                                    operator='', kwargs='{}', invoke=True,
                                    show_parameters=True, enabled=True))
                continue
            parent_uid = mapping.get(parent_label, '') if parent_label else ''
            if parent_label and not parent_uid:
                continue
            # Don't create duplicates if user has already configured the tool.
            if any(it.parent == parent_uid and it.operator == command and
                   it.label == label for it in existing):
                continue
            if any(it['parent'] == parent_uid and it['operator'] == command and
                   it['label'] == label for it in pending):
                continue
            pending.append(dict(uid=uuid_str(), parent=parent_uid, mode=mode,
                                quad=quad, page=page, kind='OP', label=label,
                                operator=command, kwargs=json.dumps(kwargs),
                                invoke=True, show_parameters=True, enabled=True))
        if not pending:
            self.report({'INFO'}, 'Mesh modeling tools already exist on this page')
            return {'FINISHED'}
        try:
            directory = os.path.dirname(config_path())
            os.makedirs(directory, exist_ok=True)
            backup = os.path.join(directory, 'menus_before_mesh_restore_' +
                                  datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
            save_json(backup)
            for data in pending:
                item = p.items.add()
                for key, value in data.items():
                    setattr(item, key, value)
            save_json()
            ui = context.window_manager.maxquad_ui
            ui.mode = 'EDIT_MESH'
            ui.quad = 'Q3'
            ui.parent = ''
            self.report({'INFO'}, 'Restored %d mesh items to %s; backup created' %
                        (len(pending), page))
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, 'Could not restore mesh tools: ' + str(ex))
            return {'CANCELLED'}


def default_missing_records(items, mode_filter=None):
    """Compute missing built-in commands without overwriting custom records.

    Existing entries win by mode/quad/parent-path/label; the matching hierarchy
    is reconstructed from PRESETS with stable IDs of existing submenu entries.
    """
    seen={(it.page,it.mode,it.quad,it.parent,it.label) for it in items}
    pending=[]
    for mode,quad,parent_label,label,operator,kwargs in PRESETS + ANIMATION_PRESETS:
        if mode_filter is not None and mode not in mode_filter:
            continue
        # There is deliberately no forced Delete, which users asked to remove.
        if mode=='OBJECT' and quad=='Q1' and label=='Delete':
            continue
        def locate_parent():
            if not parent_label: return ''
            for it in items:
                if (it.page=='Default' and it.mode==mode and it.quad==quad
                    and it.kind=='SUB' and it.label==parent_label):
                    return it.uid
            for it in pending:
                if (it['page']=='Default' and it['mode']==mode and
                    it['quad']==quad and it['kind']=='SUB' and
                    it['label']==parent_label):
                    return it['uid']
            return None
        parent_uid=locate_parent()
        if parent_uid is None: continue
        if ('Default',mode,quad,parent_uid,label) in seen:
            continue
        if any((it['mode']==mode and it['quad']==quad and
                it['parent']==parent_uid and it['label']==label) for it in pending):
            continue
        is_sub=operator=='>'
        record=dict(uid=uuid_str(),parent=parent_uid,mode=mode,quad=quad,
                    page='Default',kind='SUB' if is_sub else 'OP',label=label,
                    operator='' if is_sub else operator,
                    kwargs=json.dumps({} if is_sub else kwargs),
                    invoke=True,show_parameters=True,enabled=True)
        pending.append(record)
    return pending


class MAXQUAD_OT_restore_defaults_safe(Operator):
    bl_idname='maxquad.restore_defaults_safe'
    bl_label='Restore Missing Built-in Defaults (Backup)'
    bl_description='Backup JSON and add missing Default commands. Never delete or replace custom commands.'

    def invoke(self,context,event):
        return context.window_manager.invoke_confirm(self,event)

    def execute(self,context):
        p=prefs()
        pending=default_missing_records(p.items)
        if not pending:
            self.report({'INFO'},'All built-in commands already exist on Default page')
            return {'FINISHED'}
        try:
            backup=backup_settings('before_default_repair')
            for record in pending:
                it=p.items.add()
                for name,value in record.items(): setattr(it,name,value)
            save_json()
            refresh_keymaps()
            self.report({'INFO'},'Restored %d defaults; backup: %s' % (len(pending),backup))
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'},'Could not restore defaults: '+str(ex))
            return {'CANCELLED'}


def backup_settings(prefix):
    folder=os.path.dirname(config_path())
    os.makedirs(folder,exist_ok=True)
    path=os.path.join(folder,'menus_'+prefix+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
    # Preserve the raw on-disk file when present, not just the in-memory snapshot.
    if os.path.isfile(config_path()):
        import shutil
        shutil.copy2(config_path(),path+'.previous_on_disk')
    save_json(path)
    return path


class MAXQUAD_OT_export(Operator):
    bl_idname='maxquad.export'; bl_label='Export BMAX Quad JSON'
    filepath: StringProperty(subtype='FILE_PATH',default='max_quad_menus.json')
    filter_glob: StringProperty(default='*.json',options={'HIDDEN'})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self); return {'RUNNING_MODAL'}
    def execute(self,context):
        try: save_json(self.filepath)
        except Exception as ex: self.report({'ERROR'},str(ex)); return {'CANCELLED'}
        return {'FINISHED'}


class MAXQUAD_OT_import(Operator):
    bl_idname='maxquad.import'; bl_label='Import BMAX Quad JSON'
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.json',options={'HIDDEN'})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self); return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            os.makedirs(os.path.dirname(config_path()),exist_ok=True)
            backup=os.path.join(os.path.dirname(config_path()),'menus_before_import_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
            save_json(backup)
            load_json(self.filepath)
            initialize_animation_defaults()
            remove_legacy_default_delete()
            context.window_manager.maxquad_ui.parent=''
            prefs().active_index=0
            save_json()
        except Exception as ex: self.report({'ERROR'},str(ex)); return {'CANCELLED'}
        return {'FINISHED'}


class MAXQUAD_UL_items(UIList):
    def filter_items(self,context,data,propname):
        ui=context.window_manager.maxquad_ui
        items=getattr(data,propname)
        flags=[]
        for it in items:
            flags.append(self.bitflag_filter_item if (it.mode==ui.mode and it.quad==ui.quad and it.parent==ui.parent and it.page==prefs().active_page) else 0)
        return flags,[]
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        if item.kind=='SUB': ic='RIGHTARROW'
        elif item.kind=='SEP': ic='REMOVE'
        else: ic='PLAY'
        row=layout.row(align=True)
        row.prop(item,'enabled',text='')
        row.label(text=item.label or '(untitled)',icon=ic)


class MAXQUAD_OT_edit(Operator):
    bl_idname='maxquad.edit'; bl_label='Modify Quad Item'; bl_options={'REGISTER','UNDO'}
    action: EnumProperty(items=[('ADD','Add Command',''),('SUB','Add Submenu',''),('SEP','Add Separator',''),
                               ('REMOVE','Remove',''),('UP','Move Up',''),('DOWN','Move Down',''),
                               ('ENTER','Enter Submenu',''),('BACK','Parent Menu','')])
    def execute(self,context):
        ui=context.window_manager.maxquad_ui; p=prefs(); items=p.items
        if self.action=='BACK':
            current=next((i for i in items if i.uid==ui.parent),None)
            ui.parent=current.parent if current else ''
        elif self.action in {'ADD','SUB','SEP'}:
            it=items.add(); it.uid=uuid_str(); it.parent=ui.parent; it.mode=ui.mode; it.quad=ui.quad; it.page=p.active_page
            it.kind={'ADD':'OP','SUB':'SUB','SEP':'SEP'}[self.action]
            it.label={'ADD':'New Command','SUB':'New Submenu','SEP':'────────'}[self.action]
            p.active_index=len(items)-1
        else:
            n=p.active_index
            if not (0<=n<len(items)) or items[n].mode!=ui.mode or items[n].quad!=ui.quad or items[n].parent!=ui.parent or items[n].page!=p.active_page:
                self.report({'WARNING'},'Select an item from this menu'); return {'CANCELLED'}
            if self.action=='ENTER':
                if items[n].kind=='SUB': ui.parent=items[n].uid
            elif self.action=='REMOVE':
                to_remove={items[n].uid}
                changed=True
                while changed:
                    changed=False
                    for it in items:
                        if it.parent in to_remove and it.uid not in to_remove:
                            to_remove.add(it.uid); changed=True
                for j in range(len(items)-1,-1,-1):
                    if items[j].uid in to_remove: items.remove(j)
                p.active_index=max(0,min(n,len(items)-1))
            elif self.action in {'UP','DOWN'}:
                step=-1 if self.action=='UP' else 1
                j=n+step
                while 0<=j<len(items) and not (items[j].mode==ui.mode and items[j].quad==ui.quad and items[j].parent==ui.parent and items[j].page==p.active_page):
                    j+=step
                if 0<=j<len(items): items.move(n,j); p.active_index=j
        save_json(); return {'FINISHED'}


def parse_copied_python_operator(source):
    """Read Copy Python Command safely: never eval or execute the clipboard."""
    source = source.strip()
    if re.fullmatch(r'[A-Za-z_]\w*\.[A-Za-z_]\w*', source):
        return source, {}, None
    try:
        program = ast.parse(source, mode='exec')
    except SyntaxError as exc:
        raise ValueError('Clipboard is not a Blender Python command') from exc
    commands = []
    for node in ast.walk(program):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and
            isinstance(fn.value, ast.Attribute) and
            isinstance(fn.value.value, ast.Attribute) and
            isinstance(fn.value.value.value, ast.Name) and
            fn.value.value.value.id == 'bpy' and fn.value.value.attr == 'ops'):
            commands.append(node)
    if len(commands) != 1:
        raise ValueError('Right click a Blender button > Copy Python Command, then Pick')
    node = commands[0]
    if len(node.args) > 2:
        raise ValueError('Too many positional parameters')
    fn = node.func
    operator_id = fn.value.attr + '.' + fn.attr
    kwargs = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            raise ValueError('Expanded keyword arguments not supported')
        try:
            value = ast.literal_eval(keyword.value)
            json.dumps(value)
        except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
            raise ValueError('Property is not a literal: ' + keyword.arg) from exc
        kwargs[keyword.arg] = value
    invoke = None
    if node.args:
        try:
            call_mode = ast.literal_eval(node.args[0])
            if call_mode in {'INVOKE_DEFAULT', 'EXEC_DEFAULT'}:
                invoke = call_mode == 'INVOKE_DEFAULT'
        except (ValueError, SyntaxError, TypeError):
            pass
    return operator_id, kwargs, invoke


# Direct pick from Blender's UI right-click context menu. The menu's draw
# callback captures the button operator while that UI context is still valid.
# The click then writes only to the currently highlighted BMAX OP item.
def _bmax_current_target():
    try:
        p = prefs()
        ui = bpy.context.window_manager.maxquad_ui
        index = p.active_index
        if not (0 <= index < len(p.items)):
            return None
        it = p.items[index]
        if (it.kind != 'OP' or it.page != p.active_page or
                it.mode != ui.mode or it.quad != ui.quad or it.parent != ui.parent):
            return None
        return it
    except (AttributeError, KeyError, RuntimeError):
        return None


def _bmax_button_payload(context):
    button = getattr(context, 'button_operator', None)
    if button is None:
        return None
    try:
        rna = button.bl_rna
        identifier = rna.identifier
        if '_OT_' not in identifier:
            return None
        category, action = identifier.split('_OT_', 1)
        op_id = category.lower() + '.' + action.lower()
        category, action = op_id.split('.')
        # An operator button may come from another extension or Blender editor.
        # Verify its bpy.ops endpoint actually exists before exposing the entry.
        getattr(getattr(bpy.ops, category), action).get_rna_type()
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return None

    props = {}
    try:
        for prop in rna.properties:
            key = prop.identifier
            if key == 'rna_type' or prop.is_readonly or prop.type in {'POINTER', 'COLLECTION'}:
                continue
            # Only record explicitly supplied button properties. Unset/default
            # properties should be evaluated by Blender at invocation time.
            if hasattr(button, 'is_property_set') and not button.is_property_set(key):
                continue
            val = getattr(button, key)
            if prop.is_array:
                val = list(val)
            elif prop.type == 'ENUM' and getattr(prop, 'is_enum_flag', False):
                val = sorted(val)
            if isinstance(val, (bool, int, float, str, list, tuple)):
                json.dumps(val)
                props[key] = val
    except (AttributeError, TypeError, ValueError, RuntimeError):
        # ID is still useful even when Blender exposes an unusual RNA property.
        props = {}
    return op_id, props, getattr(rna, 'name', '') or op_id


class MAXQUAD_OT_pick_from_button(Operator):
    bl_idname = 'maxquad.pick_from_button'
    bl_label = 'Add BMAX Quad Menu'
    bl_description = 'Replace the selected BMAX command with this Blender button operator'
    bl_options = {'INTERNAL'}
    target_uid: StringProperty()
    operator_id: StringProperty()
    parameters: StringProperty(default='{}')
    button_label: StringProperty(default='')

    def execute(self, context):
        if not self.operator_id:
            def show_notice(menu, _context):
                menu.layout.label(text='This entry is a submenu, property, or unsupported button.')
                menu.layout.label(text='Open the submenu and right-click an actual command (e.g. Add Cube).')
            context.window_manager.popup_menu(show_notice, title='BMAX: No Operator ID', icon='INFO')
            return {'CANCELLED'}

        target = _bmax_current_target()
        if target is None or target.uid != self.target_uid:
            self.report({'WARNING'}, 'Select a New Command in BMAX Preferences before picking')
            return {'CANCELLED'}
        try:
            category, action = self.operator_id.split('.')
            if not category.isidentifier() or not action.isidentifier():
                raise ValueError('Invalid operator identifier')
            getattr(getattr(bpy.ops, category), action).get_rna_type()
            params = json.loads(self.parameters)
            if not isinstance(params, dict):
                raise ValueError('Invalid operator parameters')
            target.operator = self.operator_id
            target.kwargs = json.dumps(params, ensure_ascii=False)
            # Fill a new command's label automatically, preserve intentional names.
            if target.label.strip() in {'', 'New Command'}:
                target.label = self.button_label or self.operator_id
            save_json()
        except (AttributeError, ValueError, TypeError, RuntimeError, OSError) as ex:
            self.report({'ERROR'}, 'BMAX: ' + str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, 'BMAX Operator ID: ' + self.operator_id)
        return {'FINISHED'}


def bmax_button_context_menu(self, context):
    # Always show the BMAX entry for UI buttons, even if Blender does not
    # expose an operator or the user did not select a BMAX target first.
    # Otherwise users cannot tell whether registration worked at all.
    target = _bmax_current_target()
    payload = _bmax_button_payload(context)
    self.layout.separator()
    button = self.layout.operator('maxquad.pick_from_button', text='Add BMAX Quad Menu', icon='ADD')
    button.target_uid = target.uid if target else ''
    if payload is not None:
        operator_id, params, label = payload
        button.operator_id = operator_id
        button.parameters = json.dumps(params, ensure_ascii=False)
        button.button_label = label
    else:
        button.operator_id = ''
        button.parameters = '{}'
        button.button_label = ''


class MAXQUAD_OT_pick_operator(Operator):
    bl_idname = 'maxquad.pick_operator'
    bl_label = 'Pick Operator ID'
    bl_description = 'Read Copy Python Command from the clipboard or pasted text'
    target_uid: StringProperty()
    source: EnumProperty(items=[('CLIPBOARD','Clipboard','Read Blender clipboard'),
                               ('TEXT','Pasted Text','Read the pasted command field')], default='CLIPBOARD')

    def _notice(self, context, message, title='BMAX Pick', icon='INFO'):
        def draw_popup(menu, _context):
            col = menu.layout.column()
            for part in message.split('\n'):
                col.label(text=part[:110])
        context.window_manager.popup_menu(draw_popup, title=title, icon=icon)

    def execute(self, context):
        item = next((x for x in prefs().items if x.uid == self.target_uid), None)
        if item is None or item.kind != 'OP':
            self._notice(context, 'Select a valid Blender Operator menu item first.', 'BMAX Pick error', 'ERROR')
            return {'CANCELLED'}
        command = (context.window_manager.clipboard if self.source == 'CLIPBOARD'
                   else prefs().pick_command_text)
        if not command or not command.strip():
            self._notice(context,
                'No command found. Right-click a Blender operator button,\n'
                'choose Copy Python Command, then click Pick Clipboard.\n'
                'Or paste the command into the text field and choose Parse Pasted.',
                'BMAX Pick: empty input', 'ERROR')
            return {'CANCELLED'}
        try:
            op_id, parameters, invoke = parse_copied_python_operator(command)
            category, name = op_id.split('.')
            getattr(getattr(bpy.ops, category), name).get_rna_type()
            item.operator = op_id
            item.kwargs = json.dumps(parameters, ensure_ascii=False)
            if invoke is not None:
                item.invoke = invoke
            save_json()
        except Exception as exc:
            self._notice(context, 'Unable to identify an operator: ' + str(exc) + '\n'
                'Copied properties such as bpy.context.object.location are not operators.\n'
                'For example: bpy.ops.mesh.bevel() -> mesh.bevel.',
                'BMAX Pick: unsupported command', 'ERROR')
            self.report({'WARNING'}, 'BMAX Pick: ' + str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Operator ID updated: ' + op_id)
        self._notice(context, 'Operator ID: ' + op_id + '\n'
                     'Properties JSON and interactive settings updated.')
        return {'FINISHED'}


def can_show_last_operator_parameters(command, result):
    """Avoid F9 for interactive modal tools and commands with no RNA properties."""
    if not isinstance(result, set) or 'FINISHED' not in result or command.startswith('SPECIAL:'):
        return False
    try:
        group, name = command.split('.')
        op = getattr(getattr(bpy.ops, group), name)
        return any(p.identifier != 'rna_type' and not p.is_readonly
                   for p in op.get_rna_type().properties)
    except (ValueError, AttributeError, RuntimeError):
        return False


class MAXQUAD_OT_page(Operator):
    bl_idname = 'maxquad.page'
    bl_label = 'Manage BMAX Quad Menu Page'
    action: EnumProperty(items=[('NEW','New',''),('DUPLICATE','Duplicate',''),('DELETE','Delete','')])
    def execute(self,context):
        p=prefs()
        names=json.loads(p.pages_json)
        name=p.new_page_name.strip()
        current=p.active_page
        if self.action in {'NEW','DUPLICATE'}:
            if not name or name in names:
                self.report({'WARNING'},'Enter a unique page name'); return {'CANCELLED'}
            if self.action=='DUPLICATE':
                originals=[item_to_dict(it) for it in p.items if it.page==current]
                uid_map={d['uid']: uuid_str() for d in originals}
                for d in originals:
                    d['parent']=uid_map.get(d['parent'], '')
                    d['uid']=uid_map[d['uid']]
                    d['page']=name
                    it=p.items.add()
                    for k,v in d.items(): setattr(it,k,v)
            names.append(name)
            p.active_page=name
        elif self.action=='DELETE':
            if current=='Default' or len(names)<2:
                self.report({'WARNING'},'Default page cannot be deleted'); return {'CANCELLED'}
            names.remove(current)
            for idx in reversed(range(len(p.items))):
                if p.items[idx].page==current: p.items.remove(idx)
            p.active_page='Default'
        p.pages_json=json.dumps(names,ensure_ascii=False)
        context.window_manager.maxquad_ui.parent=''
        p.active_index=0
        save_json()
        return {'FINISHED'}


class MAXQUAD_OT_open_visual_editor(Operator):
    bl_idname='maxquad.open_visual_editor'
    bl_label='Open Drag and Drop Menu Editor'
    def execute(self,context):
        try:
            save_json()
            template=os.path.join(os.path.dirname(__file__),'visual_editor.html')
            with open(template,'r',encoding='utf-8') as file:
                html=file.read()
            with open(config_path(),'r',encoding='utf-8') as file:
                data=json.load(file)
            payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
            html=html.replace('<script>', '<script>window.__MAXQUAD_PAYLOAD='+payload+';</script><script>', 1)
            out=os.path.join(os.path.dirname(config_path()),'maxquad_drag_editor.html')
            with open(out,'w',encoding='utf-8') as file:
                file.write(html)
            webbrowser.open(Path(out).resolve().as_uri())
            self.report({'INFO'}, 'Drag editor opened with current settings; export JSON then import it back')
        except Exception as ex:
            self.report({'ERROR'},str(ex)); return {'CANCELLED'}
        return {'FINISHED'}


def draw_command_editor(layout,context,compact=False):
    ui=context.window_manager.maxquad_ui
    p=prefs()
    layout.prop(ui,'mode',text='Mode')
    layout.prop(ui,'quad',text='Quadrant')
    row=layout.row(align=True)
    if ui.parent:
        parent=next((it for it in p.items if it.uid==ui.parent),None)
        row.label(text='In: '+(parent.label if parent else 'Unknown'))
        op=row.operator('maxquad.edit',text='Back',icon='BACK'); op.action='BACK'
    else:
        row.label(text='Root Menu')
    row=layout.row()
    row.template_list('MAXQUAD_UL_items','',p,'items',p,'active_index',rows=5 if compact else 8)
    column=row.column(align=True)
    for icon,act in [('ADD','ADD'),('DOWNARROW_HLT','SUB'),('REMOVE','REMOVE'),
                     ('TRIA_UP','UP'),('TRIA_DOWN','DOWN'),('RIGHTARROW','ENTER')]:
        op=column.operator('maxquad.edit',text='',icon=icon); op.action=act
    row=layout.row(align=True)
    op=row.operator('maxquad.edit',text='Separator');op.action='SEP'
    op=row.operator('maxquad.edit',text='Enter Submenu');op.action='ENTER'
    n=p.active_index
    if 0<=n<len(p.items):
        it=p.items[n]
        if it.mode==ui.mode and it.quad==ui.quad and it.parent==ui.parent and it.page==p.active_page:
            box=layout.box()
            box.prop(it,'label')
            box.prop(it,'kind')
            if it.kind=='OP':
                row = box.row(align=True)
                row.prop(it,'operator',text='Operator ID')
                picker = row.operator('maxquad.pick_operator', text='Pick Clipboard', icon='PASTEDOWN')
                picker.target_uid = it.uid
                picker.source = 'CLIPBOARD'
                box.label(text='Select this command, then right-click a Blender operator button')
                box.label(text='Choose Add BMAX Quad Menu to fill its ID automatically')
                paste_row = box.row(align=True)
                paste_row.prop(p, 'pick_command_text', text='Paste')
                paste = paste_row.operator('maxquad.pick_operator', text='Parse Pasted', icon='CHECKMARK')
                paste.target_uid = it.uid
                paste.source = 'TEXT'
                box.prop(it,'kwargs')
                box.prop(it,'invoke')
                sub=box.box()
                sub.label(text='Command Shortcut (current Page + Mode)')
                sub.prop(it, 'shortcut_key')
                line=sub.row(align=True)
                line.prop(it,'shortcut_ctrl'); line.prop(it,'shortcut_shift')
                line.prop(it,'shortcut_alt'); line.prop(it,'shortcut_oskey')
                line=sub.row(align=True)
                line.operator('maxquad.shortcuts_apply', text='Apply Shortcuts')
                op=line.operator('maxquad.shortcuts_record', text='Record Key')
                op.target_uid=it.uid
                if it.shortcut_key != 'NONE':
                    matches=shortcut_conflicts(it)
                    if matches:
                        sub.label(text='Conflicts: '+', '.join(matches[:3]), icon='ERROR')
            box.prop(it,'enabled')


class MAXQUAD_PT_editor(Panel):
    bl_label='BMAX Quad Menu Editor'; bl_idname='MAXQUAD_PT_editor'
    bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='BMAX Quad'
    def draw(self,context):
        layout=self.layout
        p=prefs()
        layout.operator('maxquad.show',text='Open Quad Menu',icon='MENU_PANEL')
        layout.prop(p,'active_page',text='Page')
        draw_command_editor(layout,context)
        row=layout.row(align=True)
        row.operator('maxquad.open_visual_editor',text='Drag Editor',icon='URL')
        row.operator('maxquad.save',text='Save',icon='FILE_TICK')
        row=layout.row(align=True)
        row.operator('maxquad.import',text='Import',icon='IMPORT')
        row.operator('maxquad.export',text='Export',icon='EXPORT')
        layout.operator('maxquad.apply_layout',text='Apply Autodesk-style Layout (Backup)',icon='PRESET')
        layout.operator('maxquad.restore_defaults_safe',text='Restore Missing Built-in Defaults (Backup)',icon='FILE_REFRESH')
        layout.operator('maxquad.restore_mesh_tools',text='Restore Missing Mesh Tools (Backup)',icon='MOD_BEVEL')


# Drawing: all coordinates are VIEW_3D window-region pixels, origin at bottom-left.
_shader = None

def fill_rect(x,y,w,h,color):
    global _shader
    if w<=0 or h<=0: return
    if _shader is None: _shader=gpu.shader.from_builtin('UNIFORM_COLOR')
    batch=batch_for_shader(_shader,'TRIS',{'pos':[(x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h)]})
    _shader.bind(); _shader.uniform_float('color',color); batch.draw(_shader)


def draw_text(s,x,y,size,color):
    blf.size(0,size)
    blf.color(0,*color)
    blf.position(0,x,y,0)
    blf.draw(0,s)


def get_mode(context):
    if context.area and context.area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR'}:
        return 'ANIMATION'
    mode=context.mode
    return mode if mode in {x[0] for x in MODES} else 'OTHER'


# These runtime entries are intentionally NOT written to menus.json. Users keep
# their custom layouts, while Q4 receives a context-sensitive Transform submenu.
TRANSFORM_GIZMOS = (
    ('Move  |  Gizmo', 'SPECIAL:GIZMO_MOVE'),
    ('Rotate  |  Gizmo', 'SPECIAL:GIZMO_ROTATE'),
    ('Scale  |  Gizmo', 'SPECIAL:GIZMO_SCALE'),
    ('All Transform  |  Gizmo', 'SPECIAL:GIZMO_ALL'),
)
TRANSFORM_ORIENTATIONS = (
    ('Global', 'SPECIAL:ORIENTATION_GLOBAL'),
    ('Local', 'SPECIAL:ORIENTATION_LOCAL'),
    ('Normal', 'SPECIAL:ORIENTATION_NORMAL'),
    ('Gimbal', 'SPECIAL:ORIENTATION_GIMBAL'),
    ('View', 'SPECIAL:ORIENTATION_VIEW'),
    ('Cursor', 'SPECIAL:ORIENTATION_CURSOR'),
    ('Parent', 'SPECIAL:ORIENTATION_PARENT'),
)
RUNTIME_TRANSFORM_PREFIX = 'maxquad-runtime-transform:'
RUNTIME_ORIENTATION_PREFIX = 'maxquad-runtime-orientation:'
RUNTIME_ADD_PREFIX = 'maxquad-runtime-add:'
# Curated built-in creation operators; the native Add menu below provides the
# complete, version-dependent set including third-party Add menu extensions.
ADD_CATALOG = (
    ('Mesh', (
        ('Plane', 'mesh.primitive_plane_add', {}),
        ('Cube', 'mesh.primitive_cube_add', {}),
        ('Circle', 'mesh.primitive_circle_add', {}),
        ('UV Sphere', 'mesh.primitive_uv_sphere_add', {}),
        ('Icosphere', 'mesh.primitive_ico_sphere_add', {}),
        ('Cylinder', 'mesh.primitive_cylinder_add', {}),
        ('Cone', 'mesh.primitive_cone_add', {}),
        ('Torus', 'mesh.primitive_torus_add', {}),
        ('Grid', 'mesh.primitive_grid_add', {}),
        ('Monkey', 'mesh.primitive_monkey_add', {}),
    )),
    ('Curve', (
        ('Bezier', 'curve.primitive_bezier_curve_add', {}),
        ('Circle', 'curve.primitive_bezier_circle_add', {}),
        ('NURBS Curve', 'curve.primitive_nurbs_curve_add', {}),
        ('NURBS Circle', 'curve.primitive_nurbs_circle_add', {}),
        ('Path', 'curve.primitive_nurbs_path_add', {}),
    )),
    ('Surface', (
        ('NURBS Curve', 'surface.primitive_nurbs_surface_curve_add', {}),
        ('NURBS Circle', 'surface.primitive_nurbs_surface_circle_add', {}),
        ('NURBS Surface', 'surface.primitive_nurbs_surface_surface_add', {}),
        ('NURBS Cylinder', 'surface.primitive_nurbs_surface_cylinder_add', {}),
        ('NURBS Sphere', 'surface.primitive_nurbs_surface_sphere_add', {}),
        ('NURBS Torus', 'surface.primitive_nurbs_surface_torus_add', {}),
    )),
    ('Metaball', (
        ('Ball', 'object.metaball_add', {'type': 'BALL'}),
        ('Capsule', 'object.metaball_add', {'type': 'CAPSULE'}),
        ('Plane', 'object.metaball_add', {'type': 'PLANE'}),
        ('Ellipsoid', 'object.metaball_add', {'type': 'ELLIPSOID'}),
        ('Cube', 'object.metaball_add', {'type': 'CUBE'}),
    )),
    ('Text', (('Text Object', 'object.text_add', {}),)),
    ('Point Cloud', (('Point Cloud', 'object.pointcloud_add', {}),)),
    ('Volume', (('Import OpenVDB', 'object.volume_import', {}),)),
    ('Grease Pencil', (
        ('Blank', 'object.grease_pencil_add', {'type': 'EMPTY'}),
        ('Stroke', 'object.grease_pencil_add', {'type': 'STROKE'}),
        ('Monkey', 'object.grease_pencil_add', {'type': 'MONKEY'}),
    )),
    ('Armature', (('Single Bone', 'object.armature_add', {}),)),
    ('Lattice', (('Lattice', 'object.add', {'type': 'LATTICE'}),)),
    ('Empty', (
        ('Plain Axes', 'object.empty_add', {'type': 'PLAIN_AXES'}),
        ('Arrows', 'object.empty_add', {'type': 'ARROWS'}),
        ('Circle', 'object.empty_add', {'type': 'CIRCLE'}),
        ('Cube', 'object.empty_add', {'type': 'CUBE'}),
        ('Sphere', 'object.empty_add', {'type': 'SPHERE'}),
    )),
    ('Image', (
        ('Reference Image', 'object.empty_image_add', {'background': False}),
        ('Background Image', 'object.empty_image_add', {'background': True}),
    )),
    ('Light', (
        ('Point', 'object.light_add', {'type': 'POINT'}),
        ('Sun', 'object.light_add', {'type': 'SUN'}),
        ('Spot', 'object.light_add', {'type': 'SPOT'}),
        ('Area', 'object.light_add', {'type': 'AREA'}),
    )),
    ('Light Probe', (
        ('Sphere', 'object.lightprobe_add', {'type': 'SPHERE'}),
        ('Plane', 'object.lightprobe_add', {'type': 'PLANE'}),
        ('Volume', 'object.lightprobe_add', {'type': 'VOLUME'}),
    )),
    ('Camera', (('Camera', 'object.camera_add', {}),)),
    ('Speaker', (('Speaker', 'object.speaker_add', {}),)),
    ('Force Field', (
        ('Force', 'object.effector_add', {'type': 'FORCE'}),
        ('Wind', 'object.effector_add', {'type': 'WIND'}),
        ('Vortex', 'object.effector_add', {'type': 'VORTEX'}),
        ('Magnetic', 'object.effector_add', {'type': 'MAGNET'}),
        ('Turbulence', 'object.effector_add', {'type': 'TURBULENCE'}),
    )),
    ('Collection Instance', (('Choose Collection...', 'object.collection_instance_add', {}),)),
)


def creation_operator_available(operator):
    try:
        group, name = operator.split('.', 1)
        fn = getattr(getattr(bpy.ops, group), name)
        return fn.poll()
    except (AttributeError, RuntimeError, ValueError, TypeError):
        return False


def empty_object_selection(context, mode):
    if mode != 'OBJECT':
        return False
    try:
        return not bool(context.selected_objects)
    except (AttributeError, RuntimeError):
        return False



# This menu is generated dynamically and never modifies user JSON presets.
RUNTIME_MODE_PREFIX = 'maxquad-runtime-mode:'
# Operator mode, label, object types. Also consult Blender's live enum to avoid
# presenting obsolete modes if a later Blender build removes one.
OBJECT_MODE_CATALOG = (
    ('OBJECT', 'Object Mode', None),
    ('EDIT', 'Edit Mode', {'MESH','CURVE','SURFACE','META','FONT','ARMATURE','LATTICE','GPENCIL','GREASEPENCIL','CURVES','POINTCLOUD'}),
    ('SCULPT', 'Sculpt Mode', {'MESH'}),
    ('VERTEX_PAINT', 'Vertex Paint', {'MESH'}),
    ('WEIGHT_PAINT', 'Weight Paint', {'MESH'}),
    ('TEXTURE_PAINT', 'Texture Paint', {'MESH'}),
    ('POSE', 'Pose Mode', {'ARMATURE'}),
    ('SCULPT_CURVES', 'Curves Sculpt', {'CURVES'}),
    ('PAINT_GREASE_PENCIL', 'Grease Pencil Draw', {'GREASEPENCIL'}),
    ('SCULPT_GREASE_PENCIL', 'Grease Pencil Sculpt', {'GREASEPENCIL'}),
    ('WEIGHT_GREASE_PENCIL', 'Grease Pencil Weight Paint', {'GREASEPENCIL'}),
    ('VERTEX_GREASE_PENCIL', 'Grease Pencil Vertex Paint', {'GREASEPENCIL'}),
)


def selectable_mode_items(context):
    ob = context.active_object
    if ob is None or not ob.select_get():
        return []
    try:
        available = {item.identifier for item in
                     bpy.ops.object.mode_set.get_rna_type().properties['mode'].enum_items}
    except (AttributeError, KeyError, RuntimeError):
        available = {m for m, _, _ in OBJECT_MODE_CATALOG}
    entries = []
    for mode_name, label, types in OBJECT_MODE_CATALOG:
        if mode_name not in available or (types is not None and ob.type not in types):
            continue
        entries.append((mode_name, label))
    return entries

TRANSFORM_MODES = {
    'OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE',
    'EDIT_ARMATURE', 'EDIT_LATTICE', 'POSE',
}


def can_transform(context, mode):
    if mode not in TRANSFORM_MODES or context.area is None or context.area.type != 'VIEW_3D':
        return False
    # The Blender operator poll also checks selected/active transformable data.
    try:
        return bpy.ops.transform.translate.poll() and bpy.ops.transform.rotate.poll() and bpy.ops.transform.resize.poll()
    except (AttributeError, RuntimeError, TypeError):
        return False


def runtime_item(uid, parent, mode, quad, kind, label, command=''):
    return SimpleNamespace(uid=uid, parent=parent, mode=mode, quad=quad,
                           kind=kind, label=label, operator=command,
                           kwargs='{}', invoke=False, enabled=True)


def animation_editor(context):
    if context is None or context.area is None:
        return ''
    if context.area.type == 'GRAPH_EDITOR':
        return 'GRAPH'
    if context.area.type == 'DOPESHEET_EDITOR':
        return 'TIMELINE' if context.area.ui_type == 'TIMELINE' else 'DOPESHEET'
    return ''


def animation_item_available(item, context):
    if item.kind == 'SEP':
        return True
    if item.kind == 'SUB':
        return True
    if item.kind != 'OP':
        return False
    editor = animation_editor(context)
    if not editor:
        return False
    command = item.operator
    if command.startswith('SPECIAL:'):
        return False
    prefix = command.split('.', 1)[0]
    if prefix == 'graph' and editor != 'GRAPH':
        return False
    if prefix == 'action' and editor != 'DOPESHEET':
        return False
    if editor == 'TIMELINE' and prefix not in {'screen', 'marker'}:
        return False
    try:
        group, action = command.split('.')
        op = getattr(getattr(bpy.ops, group), action)
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if region is None:
            return False
        with context.temp_override(area=context.area, region=region):
            return op.poll()
    except (ValueError, AttributeError, RuntimeError, TypeError):
        return False


def animation_filter_tree(items, mode, quad, context, visited=None):
    # Do not show unavailable operators nor submenus which have no usable children.
    visited = visited or set()
    results=[]
    for item in items:
        if item.kind == 'SUB':
            if item.uid not in visited and animation_filter_tree(
                [it for it in prefs().items if it.page == item.page and it.mode == mode
                 and it.quad == quad and it.parent == item.uid and it.enabled],
                mode, quad, context, visited | {item.uid}):
                results.append(item)
        elif animation_item_available(item, context):
            results.append(item)
    # Separators don't start or end visible groups; avoid consecutive separators.
    cleaned=[]
    for item in results:
        if item.kind == 'SEP' and (not cleaned or cleaned[-1].kind == 'SEP'):
            continue
        cleaned.append(item)
    if cleaned and cleaned[-1].kind == 'SEP':
        cleaned.pop()
    return cleaned


def children(mode, quad, parent='', context=None):
    if parent == RUNTIME_MODE_PREFIX + 'ROOT':
        if context is None:
            return []
        active_mode = getattr(context.active_object, 'mode', 'OBJECT')
        return [
            runtime_item(RUNTIME_MODE_PREFIX + mode_name, parent, mode, quad,
                         'OP', ('✓ ' if active_mode == mode_name else '') + label,
                         'SPECIAL:SET_MODE_' + mode_name)
            for mode_name, label in selectable_mode_items(context)
        ]


    # The full Add hierarchy is generated at run time, avoiding destructive
    # edits to the user's existing menus.json configuration.
    if parent == RUNTIME_ADD_PREFIX + 'ROOT':
        if context is None or not empty_object_selection(context, mode):
            return []
        result = []
        for n, (category, commands) in enumerate(ADD_CATALOG):
            if any(creation_operator_available(op) for _, op, _ in commands):
                result.append(runtime_item(RUNTIME_ADD_PREFIX + str(n), parent,
                                           mode, quad, 'SUB', category))
        result.append(runtime_item(RUNTIME_ADD_PREFIX + 'NATIVE', parent, mode,
                                   quad, 'OP', 'Blender Add Menu (All / Add-ons)',
                                   'SPECIAL:BLENDER_ADD_MENU'))
        return result
    if parent.startswith(RUNTIME_ADD_PREFIX):
        if context is None or not empty_object_selection(context, mode):
            return []
        try:
            n = int(parent[len(RUNTIME_ADD_PREFIX):])
            commands = ADD_CATALOG[n][1]
        except (ValueError, IndexError):
            return []
        result = []
        for i, (label, operator, kwargs) in enumerate(commands):
            if creation_operator_available(operator):
                item = runtime_item(parent + ':' + str(i), parent, mode,
                                    quad, 'OP', label, operator)
                item.kwargs = json.dumps(kwargs)
                item.invoke = True
                result.append(item)
        return result

    if parent.startswith(RUNTIME_TRANSFORM_PREFIX):
        if context is None or not can_transform(context, mode):
            return []
        items = [runtime_item(parent + ':tool:' + str(i), parent, mode, quad, 'OP', label, cmd)
                 for i, (label, cmd) in enumerate(TRANSFORM_GIZMOS)]
        items.append(runtime_item(RUNTIME_ORIENTATION_PREFIX + (parent.split(':', 1)[1] if ':' in parent else 'ROOT'),
                                  parent, mode, quad, 'SUB', 'Transform Orientations'))
        return items
    if parent.startswith(RUNTIME_ORIENTATION_PREFIX):
        if context is None or not can_transform(context, mode):
            return []
        return [runtime_item(parent + ':item:' + str(i), parent, mode, quad, 'OP', label, cmd)
                for i, (label, cmd) in enumerate(TRANSFORM_ORIENTATIONS)]

    p = prefs()
    # Pages can contain only a few customized modes. If no commands exist for
    # this page/mode/quadrant, inherit the Default page instead of losing mesh
    # modeling operations like Loop Cut and Bevel. This is read-only.
    source_page = p.active_page
    if parent and not parent.startswith('maxquad-runtime'):
        source_item = next((it for it in p.items if it.uid == parent), None)
        if source_item is not None:
            source_page = source_item.page
    entries = [it for it in p.items if it.enabled and it.page == source_page
               and it.mode == mode and it.quad == quad and it.parent == parent]
    if mode != 'ANIMATION' and not parent and source_page != 'Default':
        # Page overlays Default instead of replacing an entire quadrant when
        # only one custom command was added. Children follow the item's page.
        defaults=[it for it in p.items if it.enabled and it.page == 'Default'
                  and it.mode == mode and it.quad == quad and not it.parent]
        labels={it.label for it in entries}
        entries += [it for it in defaults if it.label not in labels]
    if mode == 'ANIMATION':
        # Share the same configuration; a custom page without animation entries
        # can inherit the Default page's animation list.
        if not entries and prefs().active_page != 'Default':
            entries = [it for it in prefs().items if it.enabled and it.page == 'Default'
                       and it.mode == 'ANIMATION' and it.quad == quad and it.parent == parent]
        return animation_filter_tree(entries, mode, quad, context)
    if not parent and not entries:
        entries = [it for it in prefs().items if it.enabled and it.page==prefs().active_page and it.mode == 'GLOBAL'
                   and it.quad == quad and it.parent == '']

    # No selected objects: dedicated Add menu in Q3, hiding unavailable mesh
    # editing commands. Other quadrants remain user-configurable.
    if quad == 'Q3' and not parent and context is not None and empty_object_selection(context, mode):
        return [runtime_item(RUNTIME_ADD_PREFIX + 'ROOT', '', mode, quad,
                             'SUB', 'Add')]

    # Q3: current object's available interaction modes, always reachable from
    # Object/Edit/Sculpt/Pose/Paint modes without rewriting saved presets.
    if quad == 'Q3' and not parent and context is not None:
        modes = selectable_mode_items(context)
        if modes:
            entries.insert(0, runtime_item(RUNTIME_MODE_PREFIX + 'ROOT', '', mode, quad,
                                           'SUB', 'Object Modes'))

    # Only the bottom-right quadrant (Q4) owns auto-injected Transform tools.
    if quad == 'Q4' and context is not None and can_transform(context, mode):
        runtime_id = RUNTIME_TRANSFORM_PREFIX + (parent or 'ROOT')
        entries.append(runtime_item(runtime_id, parent, mode, quad, 'SUB', 'Transform / Gizmo'))
    return entries


def hit(rect,x,y):
    return rect[0]<=x<=rect[0]+rect[2] and rect[1]<=y<=rect[1]+rect[3]


def submenu_horizontal_position(source, width, quad, viewport_width, gap=3, margin=3):
    """Prefer left for Q1/Q3, right for Q2/Q4; flip at editor edges."""
    left = source[0] - width - gap
    right = source[0] + source[2] + gap
    last_x = max(margin, viewport_width - width - margin)
    candidates = ((left, 'LEFT'), (right, 'RIGHT')) if quad in {'Q1','Q3'} else ((right,'RIGHT'), (left,'LEFT'))
    for x, side in candidates:
        if margin <= x <= last_x:
            return x, side
    # Insufficient room on either side: choose the side with more space,
    # clamp to the viewport, and keep hit tests in the same coordinates.
    best_x, best_side = max(candidates, key=lambda c: min(c[0],last_x)-max(c[0],margin) if margin <= c[0] <= last_x else -(abs(c[0]-max(margin,min(c[0],last_x)))))
    return max(margin,min(best_x,last_x)), best_side


PANEL_HEADER = 22
PANEL_MARGIN = 3


def submenu_vertical_position(row, height, viewport_height):
    # The first child row and its source row share the same top edge.
    desired = row[1] + row[3] + PANEL_HEADER - height
    highest = viewport_height - height - PANEL_MARGIN
    return min(highest, max(PANEL_MARGIN, desired))


def crosses_submenu_gap(x, y, source_row, child_panel, direction):
    # Connect the source row to the first child row, even when vertically
    # clamped. Leave any overlapping panels to their ordinary hit testing.
    sx, sy, sw, sh = source_row
    cx, cy, cw, ch = child_panel
    if direction == 'LEFT':
        start, end = sx, cx + cw - PANEL_MARGIN
        if not end <= x <= start or end == start:
            return False
    else:
        start, end = sx + sw, cx + PANEL_MARGIN
        if not start <= x <= end or end == start:
            return False
    progress = (x - start) / (end - start)
    child_top = cy + ch - PANEL_HEADER
    top = sy + sh + (child_top - sy - sh) * progress
    return top - sh - PANEL_MARGIN <= y <= top + PANEL_MARGIN


class MAXQUAD_OT_show(Operator):
    bl_idname='maxquad.show'; bl_label='Show BMAX Quad Menu'; bl_options={'REGISTER'}
    _handle=None

    @classmethod
    def poll(cls,context):
        if context.area is None:
            return False
        if context.area.type == 'VIEW_3D':
            return True
        return context.area.type in {'DOPESHEET_EDITOR','GRAPH_EDITOR'} and prefs().enable_animation_quad

    def invoke(self,context,event):
        self.mode=get_mode(context)
        self.space_class = (bpy.types.SpaceView3D if context.area.type == 'VIEW_3D' else
                            bpy.types.SpaceGraphEditor if context.area.type == 'GRAPH_EDITOR' else
                            bpy.types.SpaceDopeSheetEditor)
        self.initial_area = context.area
        view_region=next((r for r in context.area.regions if r.type=='WINDOW'),None)
        if view_region is None:
            self.report({'ERROR'},'3D viewport window region not available')
            return {'CANCELLED'}
        self.view_region=view_region
        self.mx=event.mouse_x-view_region.x; self.my=event.mouse_y-view_region.y
        self.origin=(self.mx,self.my) if context.region.type=='WINDOW' else (view_region.width//2,view_region.height//2)
        self.active_quad=None; self.hover_uid=''; self.sub_path=[]
        self.panels=[]; self.items_hit=[]
        self.recompute(context)
        self._handle=self.space_class.draw_handler_add(self.draw_overlay,(), 'WINDOW','POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def close(self,context):
        if self._handle is not None:
            self.space_class.draw_handler_remove(self._handle,'WINDOW'); self._handle=None
        if context.area: context.area.tag_redraw()

    def base_panel(self,context,quad,its):
        p=prefs(); width=max(p.panel_width, max((len(it.label)*p.font_size*0.65+35 for it in its),default=0))
        width=min(width,450)
        height=max(1,len(its))*p.item_height+PANEL_HEADER
        ox,oy=self.origin
        gap=7
        x=ox-width-gap if quad in ('Q1','Q3') else ox+gap
        y=oy+gap if quad in ('Q1','Q2') else oy-height-gap
        x=max(3,min(x,self.view_region.width-width-3))
        y=max(3,min(y,self.view_region.height-height-3))
        return (x,y,width,height)

    def recompute(self,context):
        p=prefs(); self.panels=[]; self.items_hit=[]
        for quad in ('Q1','Q2','Q3','Q4'):
            its=children(self.mode,quad,context=context)
            if not its: continue
            rect=self.base_panel(context,quad,its)
            self.add_panel(quad,its,rect,0)
        if self.active_quad and self.sub_path:
            for level,uid in enumerate(self.sub_path):
                parent_hit=next((it for it in self.items_hit if it['item'].uid==uid and it['level']==level and it['quad']==self.active_quad),None)
                if not parent_hit: break
                parent=parent_hit['item']; sub=children(self.mode,self.active_quad,parent.uid,context=context)
                if not sub: break
                width=max(p.panel_width,max((len(i.label)*p.font_size*.65+38 for i in sub),default=0))
                width=min(width,450); height=len(sub)*p.item_height+PANEL_HEADER
                source=parent_hit['panel']; row=parent_hit['rect']
                x, direction = submenu_horizontal_position(
                    source, width, self.active_quad, self.view_region.width)
                y = submenu_vertical_position(row, height, self.view_region.height)
                self.add_panel(self.active_quad,sub,(x,y,width,height),level+1,
                               direction=direction, source_row=row)

    def add_panel(self,quad,items,rect,level,direction=None,source_row=None):
        p=prefs(); x,y,w,h=rect
        self.panels.append({'quad':quad,'rect':rect,'level':level,'direction':direction,'source_row':source_row})
        for n,it in enumerate(items):
            row_y=y+h-PANEL_HEADER-(n+1)*p.item_height
            self.items_hit.append({'quad':quad,'level':level,'item':it,
                                   'rect':(x+3,row_y,w-6,p.item_height), 'panel':rect})

    def draw_overlay(self):
        if self._handle is None: return
        try:
            gpu.state.blend_set('ALPHA')
            p=prefs()
            for pn in self.panels:
                x,y,w,h=pn['rect']; quad=pn['quad']; level=pn['level']
                fill_rect(x-1,y-1,w+2,h+2,(.08,.08,.08,.95))
                fill_rect(x,y,w,h,(.19,.19,.19,.97))
                fill_rect(x,y+h-20,w,20,(.115,.115,.115,1))
                caption=('BMAX '+quad) if level==0 else 'SUBMENU'
                draw_text(caption,x+8,y+h-15,max(10,p.font_size-1),(.64,.72,.84,1))
                for entry in [e for e in self.items_hit if e['quad']==quad and e['level']==level]:
                    it=entry['item']; rx,ry,rw,rh=entry['rect']
                    if it.uid==self.hover_uid: fill_rect(rx,ry,rw,rh,(.27,.40,.62,1))
                    if it.kind=='SEP':
                        fill_rect(rx+6,ry+rh*.5,rw-12,1,(.39,.39,.39,1))
                        continue
                    side = 'LEFT' if quad in {'Q1','Q3'} else 'RIGHT'
                    if it.kind=='SUB' and len(self.sub_path)>level and self.sub_path[level]==it.uid:
                        child_panel = next((v for v in self.panels if v['quad']==quad and v['level']==level+1),None)
                        if child_panel is not None: side = child_panel.get('direction') or side
                    if it.kind=='SUB' and side=='LEFT':
                        draw_text('◀',rx+7,ry+(rh-p.font_size)*.5+2,p.font_size,(.76,.81,.88,1))
                    if it.kind=='SUB' and side=='RIGHT':
                        draw_text('▶',rx+rw-16,ry+(rh-p.font_size)*.5+2,p.font_size,(.76,.81,.88,1))
                    draw_text(it.label,rx+(25 if it.kind=='SUB' and side=='LEFT' else 8),
                              ry+(rh-p.font_size)*.5+2,p.font_size,(.89,.89,.89,1))
            fill_rect(self.origin[0]-2,self.origin[1]-2,4,4,(.60,.67,.78,1))
        except Exception:
            pass
        finally:
            gpu.state.blend_set('NONE')

    def in_submenu_gap(self, x, y, hovered_level=-1):
        return any(
            panel['level'] > hovered_level and panel['source_row'] is not None and crosses_submenu_gap(
                x, y, panel['source_row'], panel['rect'], panel['direction'])
            for panel in self.panels
        )

    def update_hover(self,context,x,y):
        # Draw order determines which panel receives hits when clamping
        # puts a submenu over another panel.
        panel = next((p for p in reversed(self.panels) if hit(p['rect'], x, y)), None)
        hovered = None
        if panel:
            hovered = next((entry for entry in self.items_hit
                            if entry['quad'] == panel['quad'] and entry['level'] == panel['level']
                            and hit(entry['rect'], x, y)), None)
        if self.in_submenu_gap(x, y, hovered['level'] if hovered else -1):
            return None
        if hovered is None:
            self.hover_uid = ''
            if panel is None and self.sub_path:
                self.sub_path = []
                self.recompute(context)
            return None

        item = hovered['item']
        path = self.sub_path[:hovered['level']]
        if item.kind == 'SUB':
            path.append(item.uid)
        self.hover_uid = item.uid
        if self.active_quad != hovered['quad'] or self.sub_path != path:
            self.active_quad = hovered['quad']
            self.sub_path = path
            self.recompute(context)
        return hovered

    def modal(self,context,event):
        if context.area is None or context.area != self.initial_area or context.area.type not in {'VIEW_3D','DOPESHEET_EDITOR','GRAPH_EDITOR'}:
            self.close(context); return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            self.close(context); return {'CANCELLED'}
        if event.type=='MOUSEMOVE':
            self.mx=event.mouse_x-self.view_region.x; self.my=event.mouse_y-self.view_region.y
            self.update_hover(context,self.mx,self.my)
            context.area.tag_redraw(); return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            x,y=event.mouse_x-self.view_region.x,event.mouse_y-self.view_region.y
            selection=self.update_hover(context,x,y)
            if selection is None:
                if self.in_submenu_gap(x, y):
                    return {'RUNNING_MODAL'}
                self.close(context); return {'CANCELLED'}
            item=selection['item']
            if item.kind=='SUB': context.area.tag_redraw(); return {'RUNNING_MODAL'}
            if item.kind=='SEP': return {'RUNNING_MODAL'}
            command=item.operator; kwargs=item.kwargs; invoke=item.invoke
            self.close(context)
            try:
                # Restore Blender's native operator workflow. In particular,
                # Bevel uses INVOKE_DEFAULT to allow dragging first; afterwards
                # Blender itself owns the lower-left Adjust Last Operation panel.
                # Do not warp the pointer or invoke screen.redo_last here.
                with context.temp_override(area=context.area, region=self.view_region):
                    run_command(bpy.context, command, kwargs, invoke)
            except Exception as ex:
                self.report({'WARNING'},'BMAX Quad: '+str(ex))
            return {'FINISHED'}
        # Do not block viewport navigation when other keys are pressed.
        return {'RUNNING_MODAL'}


def run_command(context,command,kwargs_str,invoke):
    if command.startswith('SPECIAL:'):
        special=command[8:]
        space=context.space_data
        if special.startswith('SMART_SELECT_'):
            action = 'SELECT' if special.endswith('_ALL') else 'INVERT'
            mode = get_mode(context)
            if mode == 'EDIT_MESH': op=bpy.ops.mesh.select_all
            elif mode == 'EDIT_CURVE': op=bpy.ops.curve.select_all
            elif mode == 'EDIT_ARMATURE': op=bpy.ops.armature.select_all
            elif mode == 'OBJECT': op=bpy.ops.object.select_all
            else: raise RuntimeError('Selection command unavailable in this mode')
            if not op.poll(): raise RuntimeError('Selection command unavailable')
            return op('EXEC_DEFAULT',action=action)
        if special.startswith('SET_MODE_'):
            mode_name = special[len('SET_MODE_'):]
            allowed = {m for m, _ in selectable_mode_items(context)}
            if mode_name not in allowed:
                raise RuntimeError('This object does not support mode: ' + mode_name)
            if context.active_object.mode == mode_name:
                return {'FINISHED'}
            if not bpy.ops.object.mode_set.poll():
                raise RuntimeError('Blender cannot switch modes in the current context')
            return bpy.ops.object.mode_set('EXEC_DEFAULT', mode=mode_name)
        if special=='BLENDER_ADD_MENU':
            # Native menu includes items registered by other installed add-ons.
            return bpy.ops.wm.call_menu('INVOKE_DEFAULT', name='VIEW3D_MT_add')
        if special.startswith('GIZMO_'):
            # Activate Blender's native transform tools so the handle remains
            # interactive after the Quad Menu overlay closes.
            mode=get_mode(context)
            if not can_transform(context, mode):
                raise RuntimeError('This mode or selection does not support transform gizmos')
            tool_ids={'GIZMO_MOVE':'builtin.move',
                      'GIZMO_ROTATE':'builtin.rotate',
                      'GIZMO_SCALE':'builtin.scale',
                      'GIZMO_ALL':'builtin.transform'}
            tool=tool_ids.get(special)
            if tool is None:
                raise ValueError('Unknown transform gizmo: '+special)
            space.show_gizmo=True
            space.show_gizmo_tool=True
            result=bpy.ops.wm.tool_set_by_id('EXEC_DEFAULT',name=tool,space_type='VIEW_3D')
            if 'CANCELLED' in result:
                raise RuntimeError('Tool unavailable in the current Blender mode: '+tool)
            return result
        if special.startswith('ORIENTATION_'):
            mode=get_mode(context)
            if not can_transform(context, mode):
                raise RuntimeError('Transform orientation is unavailable in the current mode')
            orient = special[12:]
            valid = {'GLOBAL','LOCAL','NORMAL','GIMBAL','VIEW','CURSOR','PARENT'}
            if orient not in valid:
                raise ValueError('Unknown transform orientation: '+orient)
            try:
                context.scene.transform_orientation_slots[0].type = orient
            except Exception:
                result = bpy.ops.transform.select_orientation('EXEC_DEFAULT', orientation=orient)
                if 'CANCELLED' in result:
                    raise RuntimeError('Could not set transform orientation: '+orient)
            return
        if special=='XRAY': space.shading.show_xray=not space.shading.show_xray
        elif special.startswith('SHADING_'):
            value=special[8:]
            if value not in {'SOLID','MATERIAL','RENDERED','WIREFRAME'}: raise ValueError('Invalid shading type')
            space.shading.type=value
        elif special.startswith('SELECT_'):
            mapping={'SELECT_VERT':(True,False,False),'SELECT_EDGE':(False,True,False),'SELECT_FACE':(False,False,True)}
            if special not in mapping: raise ValueError('Unknown selection mode')
            context.tool_settings.mesh_select_mode=mapping[special]
        elif special=='PROPERTIES_OBJECT':
            for area in context.screen.areas:
                if area.type=='PROPERTIES': area.spaces.active.context='OBJECT'; break
            else: raise ValueError('No Properties editor open')
        else: raise ValueError('Unknown special command: '+special)
        return
    parts=command.split('.')
    if len(parts)!=2 or not all(x.isidentifier() for x in parts):
        raise ValueError('Operator ID must be category.name')
    kwargs=json.loads(kwargs_str or '{}')
    if not isinstance(kwargs,dict): raise ValueError('Properties must be a JSON object')
    op=getattr(getattr(bpy.ops,parts[0]),parts[1])
    if not op.poll(): raise RuntimeError('Operator unavailable in this mode: '+command)
    return op('INVOKE_DEFAULT' if invoke else 'EXEC_DEFAULT',**kwargs)


MODE_KEYMAPS={
    'OBJECT':('Object Mode','EMPTY'),
    'EDIT_MESH':('Mesh','EMPTY'),
    'EDIT_CURVE':('Curve','EMPTY'),
    'EDIT_ARMATURE':('Armature','EMPTY'),
    'POSE':('Pose','EMPTY'),
    'SCULPT':('Sculpt','EMPTY'),
    'PAINT_VERTEX':('Vertex Paint','EMPTY'),
    'PAINT_WEIGHT':('Weight Paint','EMPTY'),
    'PAINT_TEXTURE':('Image Paint','EMPTY'),
    'ANIMATION':('Dopesheet','DOPESHEET_EDITOR'),
    'GLOBAL':('3D View','VIEW_3D'),
}


def shortcut_conflicts(item):
    """Best-effort inspect Blender and BMAX active keymaps; never overwrite."""
    if item.shortcut_key=='NONE': return []
    found=[]
    wm=bpy.context.window_manager
    configs=[wm.keyconfigs.user, wm.keyconfigs.addon, wm.keyconfigs.default]
    scopes={MODE_KEYMAPS.get(item.mode,('3D View','VIEW_3D'))[0], 'Window'}
    for config in configs:
        if config is None: continue
        for km in config.keymaps:
            if km.name not in scopes: continue
            for kmi in km.keymap_items:
                if not kmi.active or kmi.type!=item.shortcut_key: continue
                if (kmi.ctrl,kmi.shift,kmi.alt,kmi.oskey)!=(item.shortcut_ctrl,item.shortcut_shift,item.shortcut_alt,item.shortcut_oskey): continue
                # The item's own BMAX assignment is not a conflict.
                if kmi.idname=='maxquad.invoke_item' and getattr(kmi.properties,'uid','')==item.uid: continue
                name=kmi.idname
                if name not in found: found.append(name)
    return found


class MAXQUAD_OT_shortcuts_apply(Operator):
    bl_idname='maxquad.shortcuts_apply'
    bl_label='Apply BMAX Command Shortcuts'
    bl_description='Save current assignments and rebuild BMAX keymaps without changing other add-ons'
    def execute(self,context):
        try:
            save_json()
            refresh_keymaps()
            self.report({'INFO'},'BMAX shortcuts updated; existing Blender shortcuts were not removed')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class MAXQUAD_OT_shortcuts_record(Operator):
    bl_idname='maxquad.shortcuts_record'
    bl_label='Record BMAX Shortcut'
    bl_description='Press the desired key combination'
    target_uid: StringProperty(options={'SKIP_SAVE'})

    def invoke(self,context,event):
        self._uid=self.target_uid
        cancel_label = 'Esc' if self._uid else 'right-click'
        self.report({'INFO'}, f'Press shortcut combination; {cancel_label} cancels')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        cancel_key = 'ESC' if self._uid else 'RIGHTMOUSE'
        if event.type == cancel_key:
            self.report({'INFO'}, 'Shortcut recording cancelled')
            return {'CANCELLED'}
        allowed = COMMAND_IDS if self._uid else KEYBOARD_IDS
        if event.type not in allowed or event.type in MODIFIER_KEYS or event.is_repeat:
            return {'RUNNING_MODAL'}
        if not self._uid:
            p = prefs()
            p.ctrl = bool(event.ctrl)
            p.shift = bool(event.shift)
            p.alt = bool(event.alt)
            p.oskey = bool(event.oskey)
            p.shortcut = event.type
            save_json()
            self.report({'INFO'}, 'Trigger recorded: ' + KEY_LABELS[event.type])
            return {'FINISHED'}

        it=next((x for x in prefs().items if x.uid==self._uid),None)
        if it is None or it.kind!='OP': return {'CANCELLED'}
        it.shortcut_key=event.type
        it.shortcut_ctrl=bool(event.ctrl)
        it.shortcut_shift=bool(event.shift)
        it.shortcut_alt=bool(event.alt)
        it.shortcut_oskey=bool(event.oskey)
        save_json()
        refresh_keymaps()
        self.report({'INFO'},'Shortcut recorded for '+it.label)
        return {'FINISHED'}


class MAXQUAD_OT_invoke_item(Operator):
    bl_idname='maxquad.invoke_item'
    bl_label='Execute BMAX Shortcut Item'
    uid: StringProperty(options={'SKIP_SAVE'})
    def execute(self,context):
        p=prefs()
        it=next((x for x in p.items if x.uid==self.uid),None)
        if it is None or it.kind!='OP' or not it.enabled: return {'CANCELLED'}
        if it.page not in {p.active_page,'Default'}: return {'CANCELLED'}
        if it.mode not in {'GLOBAL',get_mode(context)}: return {'CANCELLED'}
        if context.area is None or context.area.type not in {'VIEW_3D','DOPESHEET_EDITOR','GRAPH_EDITOR'}:
            return {'CANCELLED'}
        # Do not register as UNDO/REGISTER: the native command must own redo.
        try:
            region=next((r for r in context.area.regions if r.type=='WINDOW'),None)
            if region is None: return {'CANCELLED'}
            with context.temp_override(area=context.area,region=region):
                result=run_command(bpy.context,it.operator,it.kwargs,it.invoke)
            return {'FINISHED'} if result is None or 'CANCELLED' not in result else {'CANCELLED'}
        except Exception as exc:
            self.report({'WARNING'},'BMAX shortcut: '+str(exc))
            return {'CANCELLED'}


_keymaps=[]

def remove_keymaps():
    for km,kmi in _keymaps:
        try: km.keymap_items.remove(kmi)
        except Exception: pass
    _keymaps.clear()


def refresh_keymaps():
    remove_keymaps()
    wm=bpy.context.window_manager
    if not wm: return
    kc=wm.keyconfigs.addon
    if not kc: return
    try:
        p=prefs()
        km=kc.keymaps.new(name='3D View',space_type='VIEW_3D')
        kmi=km.keymap_items.new('maxquad.show',p.shortcut,'PRESS',ctrl=p.ctrl,shift=p.shift,alt=p.alt,oskey=p.oskey)
        _keymaps.append((km,kmi))
        # Blender Timeline is a DOPESHEET_EDITOR subtype. Sharing its keymap
        # also covers the Dope Sheet and Action Editor.
        for km_name,space_type in ([('Dopesheet','DOPESHEET_EDITOR'),('Graph Editor','GRAPH_EDITOR')]
                                   if p.enable_animation_quad else []):
            km=kc.keymaps.new(name=km_name,space_type=space_type)
            item=km.keymap_items.new('maxquad.show',p.shortcut,'PRESS',ctrl=p.ctrl,shift=p.shift,alt=p.alt,oskey=p.oskey)
            _keymaps.append((km,item))
            if p.animation_right_click:
                item=km.keymap_items.new('maxquad.show','RIGHTMOUSE','PRESS')
                _keymaps.append((km,item))
        # Individual assignments from the active page, plus Default fallback.
        # Only register once per key/mode scope, keeping exact existing keys.
        seen=set()
        for it in p.items:
            if not it.enabled or it.kind!='OP' or it.shortcut_key=='NONE': continue
            if it.page not in {p.active_page,'Default'}: continue
            scopes=[]
            if it.mode=='ANIMATION':
                if p.enable_animation_quad:
                    scopes=[('Dopesheet','DOPESHEET_EDITOR'),('Graph Editor','GRAPH_EDITOR')]
            elif it.mode in MODE_KEYMAPS:
                scopes=[MODE_KEYMAPS[it.mode]]
            else: continue
            for name,spacetype in scopes:
                identity=(name,it.shortcut_key,it.shortcut_ctrl,it.shortcut_shift,it.shortcut_alt,it.shortcut_oskey)
                if identity in seen: continue
                seen.add(identity)
                km=kc.keymaps.new(name=name,space_type=spacetype)
                kmi=km.keymap_items.new('maxquad.invoke_item',it.shortcut_key,'PRESS',
                    ctrl=it.shortcut_ctrl,shift=it.shortcut_shift,
                    alt=it.shortcut_alt,oskey=it.shortcut_oskey)
                kmi.properties.uid=it.uid
                _keymaps.append((km,kmi))
    except (KeyError,ValueError,RuntimeError): pass


classes=(MAXQUAD_PG_item,MAXQUAD_AP_preferences,MAXQUAD_PG_ui,MAXQUAD_OT_edit_animation,MAXQUAD_OT_save,
         MAXQUAD_OT_reset,MAXQUAD_OT_apply_layout,MAXQUAD_OT_restore_mesh_tools,MAXQUAD_OT_restore_defaults_safe,MAXQUAD_OT_export,MAXQUAD_OT_import,
         MAXQUAD_UL_items,MAXQUAD_OT_edit,MAXQUAD_OT_shortcuts_apply,MAXQUAD_OT_shortcuts_record,MAXQUAD_OT_invoke_item,MAXQUAD_OT_pick_from_button,MAXQUAD_OT_pick_operator,MAXQUAD_OT_page,MAXQUAD_OT_open_visual_editor,MAXQUAD_PT_editor,MAXQUAD_OT_show)


def initialize_animation_defaults():
    p=prefs()
    if p.animation_initialized:
        return
    if not any(it.mode == 'ANIMATION' and it.page == 'Default' for it in p.items):
        # Backup old JSON before migration. New animation menu is on Default page.
        directory=os.path.dirname(config_path())
        os.makedirs(directory, exist_ok=True)
        backup=os.path.join(directory,'menus_before_animation_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
        save_json(backup)
        for entry in build_defaults():
            if entry['mode'] != 'ANIMATION':
                continue
            item=p.items.add()
            for key,value in entry.items():
                setattr(item,key,value)
    p.animation_initialized=True
    save_json()


def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.WindowManager.maxquad_ui=bpy.props.PointerProperty(type=MAXQUAD_PG_ui)
    p=prefs()
    if len(p.items)==0:
        path=config_path()
        if os.path.isfile(path):
            try: load_json(path)
            except Exception as ex: print('BMAX Quad config load failed:',ex); populate(p.items,build_defaults())
        else: populate(p.items,build_defaults())
    # Upgrade existing user menus without resetting custom pages/commands.
    if any(item.page == 'Default' and item.mode == 'OBJECT' and item.quad == 'Q1'
           and not item.parent and item.kind == 'OP' and item.label == 'Delete'
           and item.operator == 'object.delete' for item in p.items):
        try:
            backup = os.path.join(os.path.dirname(config_path()),
                                  'menus_before_0_0_8_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
            save_json(backup)
            if remove_legacy_default_delete():
                save_json()
        except OSError as exc:
            print('BMAX Quad: unable to save upgraded default menu:', exc)
    initialize_animation_defaults()
    refresh_keymaps()
    bpy.types.UI_MT_button_context_menu.append(bmax_button_context_menu)


def unregister():
    bpy.types.UI_MT_button_context_menu.remove(bmax_button_context_menu)
    remove_keymaps()
    del bpy.types.WindowManager.maxquad_ui
    for cls in reversed(classes): bpy.utils.unregister_class(cls)


if __name__=='__main__': register()
