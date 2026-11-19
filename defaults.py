"""Factory quad sets modelled on the 3ds Max quad menu system, using Blender operators.

3ds Max defaults (Help > Quad Menu / Additional Quad Menus):
  right-click               Default: transform (Q1 lower right), display (Q2 upper right),
                            tools 1 (Q3 upper left, context sensitive), tools 2 (Q4 lower left)
  Ctrl+right-click          Modeling
  Alt+right-click           Animation
  Shift+right-click         Snap
  Ctrl+Alt+right-click      Lighting | Render
  Ctrl+Shift(+Alt)+right    Custom (unassigned)
  V                         Viewports
  Track View right-click    Track View key quad
"""

import json
import uuid


# --------------------------------------------------------------------------
# Tiny DSL
# --------------------------------------------------------------------------
def O(label, op, kw=None, invoke=True, path='', value=None, caddy=False, types=(), req=()):
    return dict(kind='OP', label=label, operator=op, kwargs=kw or {}, invoke=invoke, path=path,
                value='' if value is None else json.dumps(value), caddy=caddy,
                object_types=list(types), require=list(req))


def T(label, tool, caddy=True, **k):
    """3ds Max 'Move/Rotate/Scale' activate a tool mode, not a one-shot transform."""
    return O(label, 'TOOL:' + tool, path='', caddy=caddy, **k)


def P(label, path, value=None, types=(), req=()):
    return dict(kind='PROP', label=label, path=path,
                value='' if value is None else json.dumps(value),
                object_types=list(types), require=list(req))


def S(label, children, types=(), req=()):
    return dict(kind='SUB', label=label, children=children,
                object_types=list(types), require=list(req))


def D(label, generator, types=(), req=()):
    return dict(kind='DYN', label=label, dynamic=generator,
                object_types=list(types), require=list(req))


SEP = dict(kind='SEP', label='')

MESH = ('MESH',)


# --------------------------------------------------------------------------
# Shared blocks
# --------------------------------------------------------------------------
def shading():
    return S('Viewport Shading', [
        P('Wireframe', 'space_data.shading.type', 'WIREFRAME'),
        P('Solid', 'space_data.shading.type', 'SOLID'),
        P('Material Preview', 'space_data.shading.type', 'MATERIAL'),
        P('Rendered', 'space_data.shading.type', 'RENDERED'),
    ])


def snap_menu():
    return S('Snap', [
        O('Selection to Cursor', 'view3d.snap_selected_to_cursor', {'use_offset': False}),
        O('Selection to Cursor (Keep Offset)', 'view3d.snap_selected_to_cursor', {'use_offset': True}),
        O('Selection to Active', 'view3d.snap_selected_to_active'),
        O('Selection to Grid', 'view3d.snap_selected_to_grid'),
        SEP,
        O('Cursor to Selected', 'view3d.snap_cursor_to_selected'),
        O('Cursor to Active', 'view3d.snap_cursor_to_active'),
        O('Cursor to World Origin', 'view3d.snap_cursor_to_center'),
    ])


def transform_tools():
    return [
        T('Move', 'builtin.move'),
        T('Rotate', 'builtin.rotate'),
        T('Scale', 'builtin.scale'),
        T('Transform (All)', 'builtin.transform'),
    ]


def orient_and_pivot():
    return [D('Transform Orientation', 'ORIENTATIONS'), D('Pivot Point', 'PIVOTS')]


# --------------------------------------------------------------------------
# Default set (right-click)
# --------------------------------------------------------------------------
DEFAULT = {
    'GLOBAL': {
        'BR': transform_tools() + [
            SEP,
            T('Select', 'builtin.select_box', caddy=False),
            SEP,
            O('Undo', 'ed.undo'), O('Redo', 'ed.redo'),
            O('Repeat Last', 'screen.repeat_last'),
            O('Search Commands', 'wm.search_menu'),
        ] + orient_and_pivot(),
        'TR': [
            O('Isolate Selection', 'view3d.localview', req=('NOT_LOCAL_VIEW',)),
            O('End Isolate', 'view3d.localview', req=('LOCAL_VIEW',)),
            SEP,
            shading(),
            P('X-Ray', 'space_data.shading.show_xray'),
            P('Wireframe Overlay', 'space_data.overlay.show_wireframes'),
            SEP,
            O('Frame Selected', 'view3d.view_selected', {'use_all_regions': False}),
            O('Frame All', 'view3d.view_all', {'center': False}),
        ],
        'TL': [D('Object Modes', 'MODES')],
    },
    'OBJECT': {
        'BR': transform_tools() + [
            SEP,
            T('Select', 'builtin.select_box', caddy=False),
            O('Select Similar', 'object.select_grouped', req=('SELECTION',)),
            P('Affect Pivot Only', 'tool_settings.use_transform_data_origin'),
            O('Clone', 'object.duplicate_move', req=('SELECTION',)),
            O('Instance (Linked Clone)', 'object.duplicate_move_linked', req=('SELECTION',)),
            SEP,
            O('Object Properties', 'SPECIAL:OBJECT_PROPERTIES', req=('SELECTION',)),
            O('Rename', 'wm.call_panel', {'name': 'TOPBAR_PT_name', 'keep_open': False},
              req=('SELECTION',)),
            S('Convert To', [
                O('Mesh', 'object.convert', {'target': 'MESH'}, invoke=False),
                O('Curve', 'object.convert', {'target': 'CURVE'}, invoke=False),
                O('Grease Pencil', 'object.convert', {'target': 'GREASEPENCIL'}, invoke=False),
                O('Hair Curves', 'object.convert', {'target': 'CURVES'}, invoke=False),
            ], req=('SELECTION',)),
            S('Set Origin', [
                O('Origin to Geometry', 'object.origin_set', {'type': 'ORIGIN_GEOMETRY'}, invoke=False),
                O('Geometry to Origin', 'object.origin_set', {'type': 'GEOMETRY_ORIGIN'}, invoke=False),
                O('Origin to 3D Cursor', 'object.origin_set', {'type': 'ORIGIN_CURSOR'}, invoke=False),
                O('Origin to Center of Mass', 'object.origin_set', {'type': 'ORIGIN_CENTER_OF_MASS'}, invoke=False),
            ], req=('SELECTION',)),
            S('Reset XForm / Apply', [
                O('Location', 'object.transform_apply', {'location': True, 'rotation': False, 'scale': False}, invoke=False),
                O('Rotation', 'object.transform_apply', {'location': False, 'rotation': True, 'scale': False}, invoke=False),
                O('Scale', 'object.transform_apply', {'location': False, 'rotation': False, 'scale': True}, invoke=False),
                O('Rotation & Scale', 'object.transform_apply', {'location': False, 'rotation': True, 'scale': True}, invoke=False),
                O('All Transforms', 'object.transform_apply', {'location': True, 'rotation': True, 'scale': True}, invoke=False),
            ], req=('SELECTION',)),
            S('Link / Parent', [
                O('Set Parent To...', 'object.parent_set'),
                O('Clear Parent', 'object.parent_clear', {'type': 'CLEAR'}, invoke=False),
                O('Clear Parent (Keep Transform)', 'object.parent_clear', {'type': 'CLEAR_KEEP_TRANSFORM'}, invoke=False),
            ], req=('SELECTION',)),
        ] + orient_and_pivot(),
        'TR': [
            O('Isolate Selection', 'view3d.localview', req=('NOT_LOCAL_VIEW', 'SELECTION')),
            O('End Isolate', 'view3d.localview', req=('LOCAL_VIEW',)),
            SEP,
            O('Unfreeze All', 'SPECIAL:UNFREEZE_ALL'),
            O('Freeze Selection', 'SPECIAL:FREEZE_SELECTED', req=('SELECTION',)),
            D('Unhide by Name', 'HIDDEN'),
            O('Unhide All', 'object.hide_view_clear', invoke=False),
            O('Hide Unselected', 'object.hide_view_set', {'unselected': True}, invoke=False, req=('SELECTION',)),
            O('Hide Selection', 'object.hide_view_set', {'unselected': False}, invoke=False, req=('SELECTION',)),
            SEP,
            shading(),
            P('X-Ray', 'space_data.shading.show_xray'),
            P('Wireframe Overlay', 'space_data.overlay.show_wireframes'),
            S('Display As', [
                P('Bounds', 'selected_objects.display_type', 'BOUNDS'),
                P('Wire', 'selected_objects.display_type', 'WIRE'),
                P('Solid', 'selected_objects.display_type', 'SOLID'),
                P('Textured', 'selected_objects.display_type', 'TEXTURED'),
            ], req=('SELECTION',)),
            P('See-Through (In Front)', 'selected_objects.show_in_front', req=('SELECTION',)),
            SEP,
            O('Show Motion Paths', 'object.paths_calculate', req=('SELECTION',)),
            O('Clear Motion Paths', 'object.paths_clear', {'only_selected': False}, invoke=False),
        ],
        'TL': [
            D('Object Modes', 'MODES', req=('SELECTION',)),
            SEP,
            # Mesh
            O('Shade Smooth', 'object.shade_smooth', invoke=False, types=MESH),
            O('Shade Auto Smooth', 'object.shade_auto_smooth', invoke=False, caddy=True, types=MESH),
            O('Shade Flat', 'object.shade_flat', invoke=False, types=MESH),
            S('Add Modifier', [
                O('TurboSmooth (Subdivision)', 'object.modifier_add', {'type': 'SUBSURF'}, invoke=False),
                O('Symmetry (Mirror)', 'object.modifier_add', {'type': 'MIRROR'}, invoke=False),
                O('Chamfer (Bevel)', 'object.modifier_add', {'type': 'BEVEL'}, invoke=False),
                O('Shell (Solidify)', 'object.modifier_add', {'type': 'SOLIDIFY'}, invoke=False),
                O('Array', 'object.modifier_add', {'type': 'ARRAY'}, invoke=False),
                O('Boolean', 'object.modifier_add', {'type': 'BOOLEAN'}, invoke=False),
                O('Weighted Normal', 'object.modifier_add', {'type': 'WEIGHTED_NORMAL'}, invoke=False),
                O('Optimize (Decimate)', 'object.modifier_add', {'type': 'DECIMATE'}, invoke=False),
            ], types=('MESH', 'CURVE', 'FONT', 'SURFACE')),
            # Lights (3ds Max shows light tools in tools 1 when a light is selected)
            S('Light Type', [
                P('Point', 'active_object.data.type', 'POINT'),
                P('Sun', 'active_object.data.type', 'SUN'),
                P('Spot', 'active_object.data.type', 'SPOT'),
                P('Area', 'active_object.data.type', 'AREA'),
            ], types=('LIGHT',)),
            P('Cast Shadows', 'active_object.data.use_shadow', types=('LIGHT',)),
            # Cameras
            O('Set Active Camera', 'view3d.object_as_camera', types=('CAMERA',)),
            O('View Through Camera', 'view3d.view_camera', types=('CAMERA',)),
            O('Align Camera to View', 'view3d.camera_to_view', types=('CAMERA',)),
            P('Lock Camera to View', 'space_data.lock_camera', types=('CAMERA',)),
            S('Camera Type', [
                P('Perspective', 'active_object.data.type', 'PERSP'),
                P('Orthographic', 'active_object.data.type', 'ORTHO'),
                P('Panoramic', 'active_object.data.type', 'PANO'),
            ], types=('CAMERA',)),
            # Armatures
            S('Bone Display', [
                P('Octahedral', 'active_object.data.display_type', 'OCTAHEDRAL'),
                P('Stick', 'active_object.data.display_type', 'STICK'),
                P('B-Bone', 'active_object.data.display_type', 'BBONE'),
                P('Envelope', 'active_object.data.display_type', 'ENVELOPE'),
                P('Wire', 'active_object.data.display_type', 'WIRE'),
            ], types=('ARMATURE',)),
            # Empties
            S('Helper Display', [
                P('Plain Axes', 'active_object.empty_display_type', 'PLAIN_AXES'),
                P('Arrows', 'active_object.empty_display_type', 'ARROWS'),
                P('Cube', 'active_object.empty_display_type', 'CUBE'),
                P('Sphere', 'active_object.empty_display_type', 'SPHERE'),
                P('Circle', 'active_object.empty_display_type', 'CIRCLE'),
            ], types=('EMPTY',)),
        ],
        'BL': [
            D('Create', 'ADD'),
            O('Attach (Join)', 'object.join', req=('SELECTION',)),
            S('Mirror', [
                O('Mirror X', 'transform.mirror', {'constraint_axis': (True, False, False), 'orient_type': 'GLOBAL'}, invoke=False),
                O('Mirror Y', 'transform.mirror', {'constraint_axis': (False, True, False), 'orient_type': 'GLOBAL'}, invoke=False),
                O('Mirror Z', 'transform.mirror', {'constraint_axis': (False, False, True), 'orient_type': 'GLOBAL'}, invoke=False),
            ], req=('SELECTION',)),
            snap_menu(),
        ],
    },
    'EDIT_MESH': {
        'BR': transform_tools() + [
            SEP,
            T('Select', 'builtin.select_box', caddy=False),
            O('Select Similar', 'mesh.select_similar'),
            O('Clone', 'mesh.duplicate_move'),
            S('Make Planar', [
                O('Make Planar', 'mesh.face_make_planar', invoke=False, caddy=True),
                O('Flatten X', 'transform.resize', {'value': (0, 1, 1)}, invoke=False),
                O('Flatten Y', 'transform.resize', {'value': (1, 0, 1)}, invoke=False),
                O('Flatten Z', 'transform.resize', {'value': (1, 1, 0)}, invoke=False),
            ]),
            S('Slide', [
                O('Edge Slide', 'transform.edge_slide'),
                O('Vertex Slide', 'transform.vert_slide'),
                O('Push / Pull (Shrink-Fatten)', 'transform.shrink_fatten'),
            ]),
            snap_menu(),
        ] + orient_and_pivot(),
        'TR': [
            O('Hide Selection', 'mesh.hide', {'unselected': False}, invoke=False),
            O('Hide Unselected', 'mesh.hide', {'unselected': True}, invoke=False),
            O('Unhide All', 'mesh.reveal', invoke=False),
            SEP,
            shading(),
            P('X-Ray', 'space_data.shading.show_xray'),
            P('Wireframe Overlay', 'space_data.overlay.show_wireframes'),
            P('Face Orientation', 'space_data.overlay.show_face_orientation'),
            P('Statistics', 'space_data.overlay.show_stats'),
            S('Normals', [
                O('Recalculate Outside', 'mesh.normals_make_consistent', {'inside': False}, invoke=False),
                O('Recalculate Inside', 'mesh.normals_make_consistent', {'inside': True}, invoke=False),
                O('Flip', 'mesh.flip_normals', invoke=False),
                P('Display Face Normals', 'space_data.overlay.show_face_normals'),
            ]),
        ],
        # tools 1 = sub-object levels (Editable Poly)
        'TL': [
            O('Top-level', 'SPECIAL:MODE:OBJECT'),
            O('Vertex', 'mesh.select_mode', {'type': 'VERT'}, invoke=False,
              path='tool_settings.mesh_select_mode[0]'),
            O('Edge', 'mesh.select_mode', {'type': 'EDGE'}, invoke=False,
              path='tool_settings.mesh_select_mode[1]'),
            O('Polygon', 'mesh.select_mode', {'type': 'FACE'}, invoke=False,
              path='tool_settings.mesh_select_mode[2]'),
            O('Element', 'mesh.select_linked', invoke=False),
            SEP,
            S('Selection', [
                O('Select All', 'mesh.select_all', {'action': 'SELECT'}, invoke=False),
                O('Select None', 'mesh.select_all', {'action': 'DESELECT'}, invoke=False),
                O('Invert', 'mesh.select_all', {'action': 'INVERT'}, invoke=False),
                SEP,
                O('Grow', 'mesh.select_more', invoke=False),
                O('Shrink', 'mesh.select_less', invoke=False),
                O('Loop', 'mesh.select_edge_loop_multi', {}, invoke=False),
                O('Ring', 'mesh.select_edge_ring_multi', {}, invoke=False),
                O('Border (Region to Loop)', 'mesh.region_to_loop', invoke=False),
            ]),
            D('Object Modes', 'MODES'),
        ],
        # tools 2 = editing commands; level specific like Editable Poly
        'BL': [
            O('Create Face', 'mesh.edge_face_add', invoke=False),
            O('Cut', 'mesh.knife_tool'),
            O('Quickslice', 'mesh.bisect'),
            O('Swift Loop (Loop Cut)', 'mesh.loopcut_slide'),
            O('Repeat Last', 'screen.repeat_last'),
            SEP,
            # vertex level
            O('Weld (Merge by Distance)', 'mesh.remove_doubles', invoke=False, caddy=True, req=('VERT',)),
            O('Target Weld (Merge at Last)', 'mesh.merge', {'type': 'LAST'}, invoke=False, req=('VERT',)),
            O('Collapse (Merge at Center)', 'mesh.merge', {'type': 'CENTER'}, invoke=False, req=('VERT',)),
            O('Connect', 'mesh.vert_connect_path', invoke=False, req=('VERT',)),
            O('Chamfer', 'mesh.bevel', {'affect': 'VERTICES'}, caddy=True, req=('VERT',)),
            O('Break (Rip)', 'mesh.rip_move', req=('VERT',)),
            O('Extrude', 'mesh.extrude_vertices_move', req=('VERT',)),
            O('Remove (Dissolve)', 'mesh.dissolve_verts', invoke=False, req=('VERT',)),
            # edge level
            O('Connect', 'mesh.subdivide', {'number_cuts': 1}, invoke=False, caddy=True, req=('EDGE',)),
            O('Chamfer', 'mesh.bevel', {'affect': 'EDGES'}, caddy=True, req=('EDGE',)),
            O('Bridge', 'mesh.bridge_edge_loops', invoke=False, caddy=True, req=('EDGE',)),
            O('Extrude', 'mesh.extrude_edges_move', req=('EDGE',)),
            O('Split', 'mesh.edge_split', invoke=False, req=('EDGE',)),
            O('Turn (Rotate Edge)', 'mesh.edge_rotate', invoke=False, req=('EDGE',)),
            O('Remove (Dissolve)', 'mesh.dissolve_edges', invoke=False, req=('EDGE',)),
            S('Edge Properties', [
                O('Mark Seam', 'mesh.mark_seam', {'clear': False}, invoke=False),
                O('Clear Seam', 'mesh.mark_seam', {'clear': True}, invoke=False),
                O('Mark Sharp', 'mesh.mark_sharp', {'clear': False}, invoke=False),
                O('Clear Sharp', 'mesh.mark_sharp', {'clear': True}, invoke=False),
            ], req=('EDGE',)),
            # polygon level
            O('Extrude', 'mesh.extrude_region_move', req=('FACE',)),
            O('Extrude Along Normals', 'mesh.extrude_region_shrink_fatten', req=('FACE',)),
            O('Inset', 'mesh.inset', caddy=True, req=('FACE',)),
            O('Bridge', 'mesh.bridge_edge_loops', invoke=False, caddy=True, req=('FACE',)),
            O('Flip', 'mesh.flip_normals', invoke=False, req=('FACE',)),
            O('Detach', 'mesh.separate', {'type': 'SELECTED'}, invoke=False, req=('FACE',)),
            O('Poke', 'mesh.poke', invoke=False, caddy=True, req=('FACE',)),
            O('Triangulate', 'mesh.quads_convert_to_tris', invoke=False, caddy=True, req=('FACE',)),
            O('Tris to Quads', 'mesh.tris_convert_to_quads', invoke=False, caddy=True, req=('FACE',)),
            O('Remove (Dissolve)', 'mesh.dissolve_faces', invoke=False, req=('FACE',)),
            SEP,
            O('Symmetrize', 'mesh.symmetrize', invoke=False, caddy=True),
            O('Relax (Smooth Vertices)', 'mesh.vertices_smooth', invoke=False, caddy=True),
        ],
    },
    'EDIT_CURVE': {
        'BR': transform_tools() + orient_and_pivot(),
        'TR': [
            O('Hide Selection', 'curve.hide', {'unselected': False}, invoke=False),
            O('Hide Unselected', 'curve.hide', {'unselected': True}, invoke=False),
            O('Unhide All', 'curve.reveal', invoke=False),
            SEP, shading(), P('X-Ray', 'space_data.shading.show_xray'),
        ],
        'TL': [
            O('Top-level', 'SPECIAL:MODE:OBJECT'),
            O('Select All', 'curve.select_all', {'action': 'SELECT'}, invoke=False),
            O('Select None', 'curve.select_all', {'action': 'DESELECT'}, invoke=False),
            O('Invert', 'curve.select_all', {'action': 'INVERT'}, invoke=False),
            D('Object Modes', 'MODES'),
        ],
        'BL': [
            O('Extrude', 'curve.extrude_move'),
            O('Refine (Subdivide)', 'curve.subdivide', invoke=False, caddy=True),
            O('Connect (Make Segment)', 'curve.make_segment', invoke=False),
            O('Toggle Cyclic', 'curve.cyclic_toggle', invoke=False),
            O('Reverse (Switch Direction)', 'curve.switch_direction', invoke=False),
            S('Handle Type', [
                O('Automatic', 'curve.handle_type_set', {'type': 'AUTOMATIC'}, invoke=False),
                O('Vector (Corner)', 'curve.handle_type_set', {'type': 'VECTOR'}, invoke=False),
                O('Aligned (Bezier)', 'curve.handle_type_set', {'type': 'ALIGNED'}, invoke=False),
                O('Free (Bezier Corner)', 'curve.handle_type_set', {'type': 'FREE_ALIGN'}, invoke=False),
            ]),
        ],
    },
    'EDIT_ARMATURE': {
        'BR': transform_tools() + orient_and_pivot(),
        'TR': [
            O('Hide Selection', 'armature.hide', {'unselected': False}, invoke=False),
            O('Hide Unselected', 'armature.hide', {'unselected': True}, invoke=False),
            O('Unhide All', 'armature.reveal', invoke=False),
            SEP, P('X-Ray', 'space_data.shading.show_xray'),
        ],
        'TL': [
            O('Top-level', 'SPECIAL:MODE:OBJECT'),
            O('Select All', 'armature.select_all', {'action': 'SELECT'}, invoke=False),
            O('Select Mirror', 'armature.select_mirror', invoke=False),
            D('Object Modes', 'MODES'),
        ],
        'BL': [
            O('Extrude Bone', 'armature.extrude_move'),
            O('Subdivide', 'armature.subdivide', invoke=False, caddy=True),
            O('Fill Between Joints', 'armature.fill', invoke=False),
            O('Symmetrize', 'armature.symmetrize', invoke=False),
            S('Parent', [
                O('Make Parent...', 'armature.parent_set'),
                O('Clear Parent...', 'armature.parent_clear'),
            ]),
            S('Bone Roll', [
                O('Recalculate Roll...', 'armature.calculate_roll'),
                O('Clear Roll', 'armature.roll_clear', invoke=False),
            ]),
        ],
    },
    'POSE': {
        'BR': transform_tools() + orient_and_pivot(),
        'TR': [
            O('Hide Selection', 'pose.hide', {'unselected': False}, invoke=False),
            O('Hide Unselected', 'pose.hide', {'unselected': True}, invoke=False),
            O('Unhide All', 'pose.reveal', invoke=False),
            SEP, P('X-Ray', 'space_data.shading.show_xray'),
            P('Bones In Front', 'active_object.show_in_front'),
        ],
        'TL': [
            O('Select All', 'pose.select_all', {'action': 'SELECT'}, invoke=False),
            O('Select Mirror', 'pose.select_mirror', invoke=False),
            D('Object Modes', 'MODES'),
        ],
        'BL': [
            O('Copy Pose', 'pose.copy', invoke=False),
            O('Paste Pose', 'pose.paste', {'flipped': False}, invoke=False),
            O('Paste Pose Flipped', 'pose.paste', {'flipped': True}, invoke=False),
            SEP,
            O('Assume Rest Pose (Clear All)', 'pose.transforms_clear', invoke=False),
            O('Clear User Transforms', 'pose.user_transforms_clear', invoke=False),
            O('Set as Rest Pose (Apply)', 'pose.armature_apply', invoke=False),
            SEP,
            O('Set Key', 'anim.keyframe_insert'),
        ],
    },
    'SCULPT': {
        'TL': [
            D('Object Modes', 'MODES'),
            S('Mask', [
                O('Mask All', 'paint.mask_flood_fill', {'mode': 'VALUE', 'value': 1.0}, invoke=False),
                O('Clear Mask', 'paint.mask_flood_fill', {'mode': 'VALUE', 'value': 0.0}, invoke=False),
                O('Invert Mask', 'paint.mask_flood_fill', {'mode': 'INVERT'}, invoke=False),
            ]),
        ],
        'TR': [P('X-Ray', 'space_data.shading.show_xray'), shading(),
               P('Wireframe Overlay', 'space_data.overlay.show_wireframes')],
        'BL': [
            O('Voxel Remesh', 'object.voxel_remesh', invoke=False),
            O('Quadriflow Remesh...', 'object.quadriflow_remesh'),
            O('Dynamic Topology', 'sculpt.dynamic_topology_toggle', invoke=False),
        ],
        'BR': [O('Search Commands', 'wm.search_menu'), O('Undo', 'ed.undo'), O('Redo', 'ed.redo')],
    },
    # Track View: right-click in Dope Sheet / Timeline / Graph Editor
    'ANIMATION': {
        'TL': [
            S('Select Keys', [
                O('Select All', 'action.select_all', {'action': 'SELECT'}, invoke=False),
                O('Invert Selection', 'action.select_all', {'action': 'INVERT'}, invoke=False),
                O('Select All', 'graph.select_all', {'action': 'SELECT'}, invoke=False),
                O('Invert Selection', 'graph.select_all', {'action': 'INVERT'}, invoke=False),
            ]),
            O('Copy Keys', 'action.copy', invoke=False),
            O('Paste Keys', 'action.paste'),
            O('Copy Keys', 'graph.copy', invoke=False),
            O('Paste Keys', 'graph.paste'),
            O('Duplicate Keys', 'action.duplicate_move'),
            O('Duplicate Keys', 'graph.duplicate_move'),
            O('Delete Keys', 'action.delete', invoke=False),
            O('Delete Keys', 'graph.delete', invoke=False),
        ],
        'TR': [
            O('Frame All', 'action.view_all'),
            O('Frame Selected', 'action.view_selected'),
            O('Frame All', 'graph.view_all'),
            O('Frame Selected', 'graph.view_selected'),
            SEP,
            O('Add Marker', 'marker.add', invoke=False),
            O('Rename Marker', 'marker.rename'),
        ],
        'BL': [
            O('Move Keys', 'transform.transform', {'mode': 'TIME_TRANSLATE'}),
            O('Scale Keys', 'transform.transform', {'mode': 'TIME_SCALE'}),
            O('Reduce Keys (Clean)', 'graph.clean', caddy=True),
            O('Reduce Keys (Clean)', 'action.clean', caddy=True),
            S('Key Tangents', [
                O('Bezier', 'action.interpolation_type', {'type': 'BEZIER'}, invoke=False),
                O('Linear', 'action.interpolation_type', {'type': 'LINEAR'}, invoke=False),
                O('Step (Constant)', 'action.interpolation_type', {'type': 'CONSTANT'}, invoke=False),
                O('Bezier', 'graph.interpolation_type', {'type': 'BEZIER'}, invoke=False),
                O('Linear', 'graph.interpolation_type', {'type': 'LINEAR'}, invoke=False),
                O('Step (Constant)', 'graph.interpolation_type', {'type': 'CONSTANT'}, invoke=False),
                O('Auto Clamped', 'graph.handle_type', {'type': 'AUTO_CLAMPED'}, invoke=False),
            ]),
        ],
        'BR': [
            O('Play / Pause', 'screen.animation_play'),
            O('Go to Start', 'screen.frame_jump', {'end': False}, invoke=False),
            O('Go to End', 'screen.frame_jump', {'end': True}, invoke=False),
            O('Previous Key', 'screen.keyframe_jump', {'next': False}, invoke=False),
            O('Next Key', 'screen.keyframe_jump', {'next': True}, invoke=False),
            O('Jump to Next Marker', 'screen.marker_jump', {'next': True}, invoke=False),
        ],
    },
}


# --------------------------------------------------------------------------
# Ctrl+right-click: Modeling
# --------------------------------------------------------------------------
MODELING = {
    'GLOBAL': {'TL': [D('Object Modes', 'MODES')]},
    'OBJECT': {
        'TL': [
            O('Plane', 'mesh.primitive_plane_add'),
            O('Box', 'mesh.primitive_cube_add'),
            O('Sphere', 'mesh.primitive_uv_sphere_add'),
            O('GeoSphere', 'mesh.primitive_ico_sphere_add'),
            O('Cylinder', 'mesh.primitive_cylinder_add'),
            O('Cone', 'mesh.primitive_cone_add'),
            O('Torus', 'mesh.primitive_torus_add'),
            O('Circle', 'mesh.primitive_circle_add'),
            O('Grid', 'mesh.primitive_grid_add'),
            SEP,
            D('More Objects', 'ADD'),
        ],
        'TR': [
            O('Edit Poly (Edit Mode)', 'SPECIAL:MODE:EDIT', types=MESH),
            D('Object Modes', 'MODES', req=('SELECTION',)),
            SEP,
            O('Shade Smooth', 'object.shade_smooth', invoke=False, types=MESH),
            O('Shade Flat', 'object.shade_flat', invoke=False, types=MESH),
        ],
        'BL': [
            S('Add Modifier', [
                O('TurboSmooth (Subdivision)', 'object.modifier_add', {'type': 'SUBSURF'}, invoke=False),
                O('Symmetry (Mirror)', 'object.modifier_add', {'type': 'MIRROR'}, invoke=False),
                O('Chamfer (Bevel)', 'object.modifier_add', {'type': 'BEVEL'}, invoke=False),
                O('Shell (Solidify)', 'object.modifier_add', {'type': 'SOLIDIFY'}, invoke=False),
                O('Array', 'object.modifier_add', {'type': 'ARRAY'}, invoke=False),
                O('Boolean', 'object.modifier_add', {'type': 'BOOLEAN'}, invoke=False),
                O('Weighted Normal', 'object.modifier_add', {'type': 'WEIGHTED_NORMAL'}, invoke=False),
            ], req=('SELECTION',)),
            O('Convert to Editable Mesh', 'object.convert', {'target': 'MESH'}, invoke=False, req=('SELECTION',)),
            O('Collapse Stack (Apply All)', 'object.convert', {'target': 'MESH'}, invoke=False, types=MESH),
        ],
        'BR': [
            O('Attach (Join)', 'object.join', req=('SELECTION',)),
            O('Clone', 'object.duplicate_move', req=('SELECTION',)),
            S('Mirror', [
                O('Mirror X', 'transform.mirror', {'constraint_axis': (True, False, False), 'orient_type': 'GLOBAL'}, invoke=False),
                O('Mirror Y', 'transform.mirror', {'constraint_axis': (False, True, False), 'orient_type': 'GLOBAL'}, invoke=False),
                O('Mirror Z', 'transform.mirror', {'constraint_axis': (False, False, True), 'orient_type': 'GLOBAL'}, invoke=False),
            ], req=('SELECTION',)),
            snap_menu(),
        ],
    },
    'EDIT_MESH': {
        'TL': [
            O('Top-level', 'SPECIAL:MODE:OBJECT'),
            O('Vertex', 'mesh.select_mode', {'type': 'VERT'}, invoke=False, path='tool_settings.mesh_select_mode[0]'),
            O('Edge', 'mesh.select_mode', {'type': 'EDGE'}, invoke=False, path='tool_settings.mesh_select_mode[1]'),
            O('Polygon', 'mesh.select_mode', {'type': 'FACE'}, invoke=False, path='tool_settings.mesh_select_mode[2]'),
            SEP,
            O('Grow', 'mesh.select_more', invoke=False),
            O('Shrink', 'mesh.select_less', invoke=False),
            O('Loop', 'mesh.select_edge_loop_multi', {}, invoke=False),
            O('Ring', 'mesh.select_edge_ring_multi', {}, invoke=False),
        ],
        'TR': [
            O('Extrude', 'mesh.extrude_region_move'),
            O('Inset', 'mesh.inset', caddy=True),
            O('Chamfer', 'mesh.bevel', {'affect': 'EDGES'}, caddy=True),
            O('Bridge', 'mesh.bridge_edge_loops', invoke=False, caddy=True),
            O('Swift Loop (Loop Cut)', 'mesh.loopcut_slide'),
            O('Cut', 'mesh.knife_tool'),
            O('Cap / Fill', 'mesh.fill_grid', invoke=False, caddy=True),
            S('Merge', [
                O('At Center', 'mesh.merge', {'type': 'CENTER'}, invoke=False),
                O('At Cursor', 'mesh.merge', {'type': 'CURSOR'}, invoke=False),
                O('Collapse', 'mesh.merge', {'type': 'COLLAPSE'}, invoke=False),
                O('At Last', 'mesh.merge', {'type': 'LAST'}, invoke=False),
                O('By Distance', 'mesh.remove_doubles', invoke=False, caddy=True),
            ]),
        ],
        'BL': [
            O('Smooth Groups: Smooth', 'mesh.faces_shade_smooth', invoke=False),
            O('Smooth Groups: Flat', 'mesh.faces_shade_flat', invoke=False),
            O('Mark Sharp', 'mesh.mark_sharp', {'clear': False}, invoke=False),
            O('Mark Seam', 'mesh.mark_seam', {'clear': False}, invoke=False),
            O('Unwrap UVW', 'wm.call_menu', {'name': 'VIEW3D_MT_uv_map'}),
        ],
        'BR': [
            O('Symmetrize', 'mesh.symmetrize', invoke=False, caddy=True),
            O('Subdivide', 'mesh.subdivide', invoke=False, caddy=True),
            O('Relax', 'mesh.vertices_smooth', invoke=False, caddy=True),
            O('Triangulate', 'mesh.quads_convert_to_tris', invoke=False, caddy=True),
            snap_menu(),
        ],
    },
}


# --------------------------------------------------------------------------
# Alt+right-click: Animation
# --------------------------------------------------------------------------
def orientations_flat():
    return [P(n, 'scene.transform_orientation_slots[0].type', v) for n, v in (
        ('View', 'VIEW'), ('Global (World)', 'GLOBAL'), ('Local', 'LOCAL'), ('Normal', 'NORMAL'),
        ('Gimbal', 'GIMBAL'), ('Parent', 'PARENT'), ('Cursor', 'CURSOR'))]


ANIMATION = {
    'GLOBAL': {
        'TL': orientations_flat() + [SEP, D('Pivot Point', 'PIVOTS')],
        'TR': [
            O('Clear Location', 'object.location_clear', invoke=False),
            O('Clear Rotation', 'object.rotation_clear', invoke=False),
            O('Clear Scale', 'object.scale_clear', invoke=False),
            SEP,
            O('Show Motion Paths', 'object.paths_calculate'),
            O('Clear Motion Paths', 'object.paths_clear', {'only_selected': False}, invoke=False),
        ],
        'BL': [
            O('Set Key', 'anim.keyframe_insert'),
            O('Set Key (Choose Channels)...', 'anim.keyframe_insert_menu'),
            O('Delete Key', 'anim.keyframe_delete_v3d'),
            O('Delete Selected Animation', 'anim.keyframe_clear_v3d'),
            SEP,
            P('Auto Key', 'scene.tool_settings.use_keyframe_insert_auto'),
        ],
        'BR': [
            O('Play / Pause', 'screen.animation_play'),
            O('Play Reverse', 'screen.animation_play', {'reverse': True}),
            O('Go to Start', 'screen.frame_jump', {'end': False}, invoke=False),
            O('Go to End', 'screen.frame_jump', {'end': True}, invoke=False),
            O('Previous Key', 'screen.keyframe_jump', {'next': False}, invoke=False),
            O('Next Key', 'screen.keyframe_jump', {'next': True}, invoke=False),
            O('Previous Frame', 'screen.frame_offset', {'delta': -1}, invoke=False),
            O('Next Frame', 'screen.frame_offset', {'delta': 1}, invoke=False),
        ],
    },
    'POSE': {
        'TR': [
            O('Copy Pose', 'pose.copy', invoke=False),
            O('Paste Pose', 'pose.paste', {'flipped': False}, invoke=False),
            O('Paste Pose Flipped', 'pose.paste', {'flipped': True}, invoke=False),
            SEP,
            O('Assume Skin Pose (Clear All)', 'pose.transforms_clear', invoke=False),
            O('Set Skin Pose (Apply as Rest)', 'pose.armature_apply', invoke=False),
            O('Clear User Transforms', 'pose.user_transforms_clear', invoke=False),
            SEP,
            O('Show Motion Paths', 'pose.paths_calculate'),
            O('Clear Motion Paths', 'pose.paths_clear', {'only_selected': False}, invoke=False),
        ],
    },
}


# --------------------------------------------------------------------------
# Shift+right-click: Snap (off by default, Blender uses Shift+RMB for the 3D cursor)
# --------------------------------------------------------------------------
def snap_el(label, flag):
    return P(label, 'tool_settings.snap_elements', flag)


SNAP = {
    'GLOBAL': {
        'TL': [
            snap_el('Grid Points', 'GRID'),
            snap_el('Increment', 'INCREMENT'),
            snap_el('Vertex', 'VERTEX'),
            snap_el('Edge', 'EDGE'),
            snap_el('Face (Project)', 'FACE_PROJECT'),
            snap_el('Face (Nearest)', 'FACE_NEAREST'),
            snap_el('Volume', 'VOLUME'),
            snap_el('Edge Center', 'EDGE_MIDPOINT'),
            snap_el('Perpendicular', 'EDGE_PERPENDICULAR'),
        ],
        'TR': [
            P('Snap Base: Closest', 'tool_settings.snap_target', 'CLOSEST'),
            P('Snap Base: Center', 'tool_settings.snap_target', 'CENTER'),
            P('Snap Base: Median', 'tool_settings.snap_target', 'MEDIAN'),
            P('Snap Base: Active', 'tool_settings.snap_target', 'ACTIVE'),
            SEP,
            P('Align Rotation to Target', 'tool_settings.use_snap_align_rotation'),
        ],
        'BL': [
            P('Affect Move', 'tool_settings.use_snap_translate'),
            P('Affect Rotate', 'tool_settings.use_snap_rotate'),
            P('Affect Scale', 'tool_settings.use_snap_scale'),
            SEP,
            P('Soft Selection (Edit)', 'tool_settings.use_proportional_edit'),
            P('Soft Selection (Objects)', 'tool_settings.use_proportional_edit_objects'),
        ],
        'BR': [
            P('Snaps Toggle', 'tool_settings.use_snap'),
            SEP,
            O('Selection to Cursor', 'view3d.snap_selected_to_cursor', {'use_offset': False}),
            O('Selection to Grid', 'view3d.snap_selected_to_grid'),
            O('Selection to Active', 'view3d.snap_selected_to_active'),
            O('Cursor to Selected', 'view3d.snap_cursor_to_selected'),
            O('Cursor to Active', 'view3d.snap_cursor_to_active'),
            O('Cursor to World Origin', 'view3d.snap_cursor_to_center'),
        ],
    },
}


# --------------------------------------------------------------------------
# Ctrl+Alt+right-click: Lighting | Render
# --------------------------------------------------------------------------
LIGHTING = {
    'GLOBAL': {
        'TL': [
            O('Render', 'render.render', {'use_viewport': True}),
            O('Render Animation', 'render.render', {'animation': True, 'use_viewport': True}),
            O('Viewport Render', 'render.opengl'),
            O('Show Render Window', 'render.view_show'),
            SEP,
            O('Create Camera From View', 'SPECIAL:CAMERA_FROM_VIEW'),
            O('Align Active Camera to View', 'view3d.camera_to_view'),
        ],
        'TR': [
            P('Wireframe', 'space_data.shading.type', 'WIREFRAME'),
            P('Solid', 'space_data.shading.type', 'SOLID'),
            P('Material Preview', 'space_data.shading.type', 'MATERIAL'),
            P('Rendered', 'space_data.shading.type', 'RENDERED'),
            SEP,
            P('Scene Lights', 'space_data.shading.use_scene_lights'),
            P('Scene World', 'space_data.shading.use_scene_world'),
        ],
        'BL': [
            O('Point Light', 'object.light_add', {'type': 'POINT'}),
            O('Sun Light', 'object.light_add', {'type': 'SUN'}),
            O('Spot Light', 'object.light_add', {'type': 'SPOT'}),
            O('Area Light', 'object.light_add', {'type': 'AREA'}),
        ],
        'BR': [
            P('Hide from Render', 'selected_objects.hide_render', req=('SELECTION',)),
            P('Visible to Camera', 'selected_objects.visible_camera', req=('SELECTION',)),
            P('Cast Shadows', 'selected_objects.visible_shadow', req=('SELECTION',)),
            P('Holdout', 'selected_objects.is_holdout', req=('SELECTION',)),
            P('Shadow Catcher', 'selected_objects.is_shadow_catcher', req=('SELECTION',)),
        ],
    },
}


# --------------------------------------------------------------------------
# V: Viewports
# --------------------------------------------------------------------------
def view(label, t):
    return O(label, 'view3d.view_axis', {'type': t}, invoke=False)


VIEWPORTS = {
    'GLOBAL': {
        'TL': [view('Top', 'TOP'), view('Bottom', 'BOTTOM'), view('Front', 'FRONT'), view('Back', 'BACK')],
        'TR': [view('Left', 'LEFT'), view('Right', 'RIGHT'),
               O('Camera', 'view3d.view_camera'),
               O('Perspective / Ortho', 'view3d.view_persportho', invoke=False)],
        'BL': [O('Toggle Quad View', 'screen.region_quadview'),
               O('Maximize Viewport', 'screen.screen_full_area'),
               O('Frame Selected', 'view3d.view_selected', {'use_all_regions': False}),
               O('Frame All', 'view3d.view_all', {'center': False})],
        'BR': [P('Wireframe', 'space_data.shading.type', 'WIREFRAME'),
               P('Solid', 'space_data.shading.type', 'SOLID'),
               P('Material Preview', 'space_data.shading.type', 'MATERIAL'),
               P('Rendered', 'space_data.shading.type', 'RENDERED')],
    },
}


SETS = [
    # uid, name, key, ctrl, shift, alt, enabled, in_anim, titles(TL, TR, BL, BR), content
    ('default', 'Default Viewport Quad', 'RIGHTMOUSE', False, False, False, True, True,
     ('tools 1', 'display', 'tools 2', 'transform'), DEFAULT),
    ('modeling', 'Modeling [Ctrl+RMB]', 'RIGHTMOUSE', True, False, False, True, False,
     ('create / levels', 'edit geometry', 'surface', 'tools'), MODELING),
    ('animation', 'Animation [Alt+RMB]', 'RIGHTMOUSE', False, False, True, True, False,
     ('coordinates', 'pose', 'keys', 'time'), ANIMATION),
    ('snap', 'Snap [Shift+RMB]', 'RIGHTMOUSE', False, True, False, False, False,
     ('snap to', 'snap base', 'snap options', 'snaps'), SNAP),
    ('lighting', 'Lighting | Render [Ctrl+Alt+RMB]', 'RIGHTMOUSE', True, False, True, True, False,
     ('render', 'shading', 'lights', 'object properties'), LIGHTING),
    ('custom1', 'Custom [Ctrl+Shift+RMB]', 'RIGHTMOUSE', True, True, False, True, False,
     ('quad 3', 'quad 2', 'quad 4', 'quad 1'), {}),
    ('custom2', 'Custom [Ctrl+Shift+Alt+RMB]', 'RIGHTMOUSE', True, True, True, True, False,
     ('quad 3', 'quad 2', 'quad 4', 'quad 1'), {}),
    ('viewports', 'Viewports [V]', 'V', False, False, False, False, False,
     ('views', 'views', 'viewport', 'shading'), VIEWPORTS),
]


def _uid():
    return uuid.uuid4().hex[:12]


def _flatten(nodes, set_id, mode, quad, parent, out):
    for node in nodes:
        rec = dict(node)
        children = rec.pop('children', None)
        rec.update(uid=_uid(), set_id=set_id, mode=mode, quad=quad, parent=parent, enabled=True)
        rec.setdefault('operator', '')
        rec.setdefault('kwargs', {})
        rec.setdefault('invoke', True)
        rec.setdefault('path', '')
        rec.setdefault('value', '')
        rec.setdefault('dynamic', 'ADD')
        rec.setdefault('object_types', [])
        rec.setdefault('require', [])
        rec.setdefault('caddy', False)
        out.append(rec)
        if children:
            _flatten(children, set_id, mode, quad, rec['uid'], out)


def build():
    sets, items = [], []
    for (sid, name, key, ctrl, shift, alt, enabled, in_anim, titles, content) in SETS:
        # Nothing is enabled by default: the user chooses which sets to turn on.
        sets.append(dict(uid=sid, name=name, enabled=False, key=key, ctrl=ctrl, shift=shift,
                         alt=alt, oskey=False, in_view3d=True, in_anim=in_anim, show_all=True,
                         title_TL=titles[0], title_TR=titles[1], title_BL=titles[2],
                         title_BR=titles[3]))
        for mode, quads in content.items():
            for quad, nodes in quads.items():
                _flatten(nodes, sid, mode, quad, '', items)
    return sets, items


def iter_operator_ids():
    """For validation: every operator id referenced by factory content."""
    _, items = build()
    for it in items:
        op = it.get('operator', '')
        if it['kind'] == 'OP' and op and ':' not in op:
            yield it['label'], op, it.get('kwargs', {})
