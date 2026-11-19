# SPDX-License-Identifier: GPL-3.0-or-later
"""BMAX Quad Menu - a 3ds Max style quad menu for Blender.

Right-click quad sets (Default / Ctrl Modeling / Alt Animation / Shift Snap /
Ctrl+Alt Lighting|Render / Custom / V Viewports / Track View), context-sensitive
tools quads, last-executed repeat, settings boxes, hotkey display, and the
3ds Max Advanced Quad Menu Options (colors, fonts, positioning, fade)."""

bl_info = {
    "name": "BMAX Quad Menu",
    "author": "BMAX Quad Menu contributors",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "Right-click in 3D Viewport / Track View; Preferences > Add-ons > BMAX Quad Menu",
    "description": "3ds Max style quad menus with quad sets, context tools and full customization",
    "category": "Interface",
}

import os

import bpy

from . import model, actions, defaults, keymaps, overlay, ui  # noqa: F401

_classes = model.classes + overlay.classes + ui.classes


def _initial_load():
    p = model.prefs()
    path = model.config_path()
    if os.path.isfile(path):
        try:
            model.load_config(path)
            return
        except Exception as exc:
            print('BMAX Quad: could not read %s (%s); using factory sets' % (path, exc))
            try:
                os.replace(path, path + '.broken')
            except OSError:
                pass
    model.load_factory()
    legacy = model.legacy_config_path()
    if os.path.isfile(legacy):
        try:
            n_sets, n_items = model.append_legacy(legacy)
            print('BMAX Quad: imported v0.0.18 menus (%d sets, %d items)' % (n_sets, n_items))
        except Exception as exc:
            print('BMAX Quad: v0.0.18 import skipped:', exc)
    model.save_config()


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bmaxquad_ui = bpy.props.PointerProperty(type=model.BMAXQUAD_PG_ui)
    _initial_load()
    keymaps.refresh()
    bpy.types.UI_MT_button_context_menu.append(ui.button_context_menu)


def unregister():
    try:
        bpy.types.UI_MT_button_context_menu.remove(ui.button_context_menu)
    except (ValueError, AttributeError):
        pass
    keymaps.unregister_keymaps()
    if model._state.get('save_pending'):
        try:
            bpy.app.timers.unregister(model._deferred_save)
        except ValueError:
            pass
        model._deferred_save()
    del bpy.types.WindowManager.bmaxquad_ui
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
