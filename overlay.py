"""The quad menu itself: a modal operator that draws a 3ds Max style quad menu.

Coordinates are window pixels. The menu may span several WINDOW regions of one area
(Quad View), each region draws its part with its own offset.
"""

import math
import os
import time

import blf
import bpy
import gpu
from bpy.props import StringProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader

from . import actions
from .model import prefs, QUAD_IDS

# (set_id, mode, quad) -> (root_uid, entry)   "Use last executed item" (3ds Max)
LAST = {}

FADE_ORDER = ('BR', 'TR', 'TL', 'BL')     # Max: counter-clockwise from Quad 1
LEFT_QUADS = {'TL', 'BL'}
TOP_QUADS = {'TL', 'TR'}

_shader = None
_font = {'path': None, 'id': 0}


def font_id():
    path = prefs().font_path
    if path != _font['path']:
        _font['path'] = path
        _font['id'] = 0
        if path:
            real = bpy.path.abspath(path)
            if os.path.isfile(real):
                fid = blf.load(real)
                if fid != -1:
                    _font['id'] = fid
    return _font['id']


# --------------------------------------------------------------------------
# Primitive drawing (offset = region origin in window space)
# --------------------------------------------------------------------------
def _sh():
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    return _shader


def tris(points, color):
    sh = _sh()
    batch = batch_for_shader(sh, 'TRIS', {'pos': points})
    sh.bind()
    sh.uniform_float('color', color)
    batch.draw(sh)


def rect(x, y, w, h, color):
    if w <= 0 or h <= 0 or color[3] <= 0:
        return
    tris([(x, y), (x + w, y), (x + w, y + h), (x, y), (x + w, y + h), (x, y + h)], color)


def outline(x, y, w, h, t, color):
    rect(x, y, w, t, color)
    rect(x, y + h - t, w, t, color)
    rect(x, y, t, h, color)
    rect(x + w - t, y, t, h, color)


def thick_line(a, b, t, color):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    ox, oy = -dy / n * t * 0.5, dx / n * t * 0.5
    p1, p2 = (a[0] + ox, a[1] + oy), (a[0] - ox, a[1] - oy)
    p3, p4 = (b[0] - ox, b[1] - oy), (b[0] + ox, b[1] + oy)
    tris([p1, p2, p3, p1, p3, p4], color)


def text(fid, s, x, y, size, color):
    blf.size(fid, size)
    blf.color(fid, *color)
    blf.position(fid, x, y, 0)
    blf.draw(fid, s)


def text_w(fid, s, size):
    blf.size(fid, size)
    return blf.dimensions(fid, s)[0]


def fit(fid, s, size, max_w):
    if text_w(fid, s, size) <= max_w:
        return s
    while s and text_w(fid, s + '…', size) > max_w:
        s = s[:-1]
    return s + '…'


def mul_alpha(c, a):
    return (c[0], c[1], c[2], c[3] * a)


def in_rect(r, x, y):
    return r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]


def in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = sign(p, a, b), sign(p, b, c), sign(p, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


class Row:
    __slots__ = ('entry', 'rect')

    def __init__(self, entry, r):
        self.entry = entry
        self.rect = r


class Panel:
    __slots__ = ('quad', 'level', 'rect', 'rows', 'title', 'side', 'owner')

    def __init__(self, quad, level, r, side, owner=None):
        self.quad = quad
        self.level = level
        self.rect = r
        self.rows = []
        self.title = None
        self.side = side      # 'LEFT' or 'RIGHT': where submenus open / arrows point
        self.owner = owner    # entry that opened this submenu


# --------------------------------------------------------------------------
class BMAXQUAD_OT_show(Operator):
    bl_idname = 'bmaxquad.show'
    bl_label = 'BMAX Quad Menu'
    bl_description = 'Open a 3ds Max style quad menu'
    set_id: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        area = context.area
        return area is not None and area.type in {'VIEW_3D', 'DOPESHEET_EDITOR', 'GRAPH_EDITOR'}

    # ---------------------------------------------------------------- setup
    def invoke(self, context, event):
        p = prefs()
        qset = next((s for s in p.sets if s.uid == self.set_id), None)
        if qset is None:
            qset = next((s for s in p.sets if s.enabled), None)
        if qset is None:
            return {'PASS_THROUGH'}
        self.qset_id = qset.uid
        self.titles = {q: getattr(qset, 'title_' + q) for q in QUAD_IDS}
        self.show_all = qset.show_all
        self.mode = actions.current_mode(context)

        self.window = context.window
        self.area = context.area
        regions = [r for r in self.area.regions if r.type == 'WINDOW']
        if not regions:
            return {'CANCELLED'}
        self.region_ptrs = {r.as_pointer() for r in regions}
        mx, my = event.mouse_x, event.mouse_y
        reg = context.region
        if reg is None or reg.type != 'WINDOW':
            reg = next((r for r in regions if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height),
                       None)
            if reg is None:
                reg = regions[0]
                mx, my = reg.x + reg.width // 2, reg.y + reg.height // 2
        self.region = reg
        self.bounds = (min(r.x for r in regions), min(r.y for r in regions),
                       max(r.x + r.width for r in regions), max(r.y + r.height for r in regions))

        self.resolver = actions.Resolver(context, self.qset_id, self.mode)
        roots = {q: self.resolver.root(q) for q in QUAD_IDS}
        roots = {q: v for q, v in roots.items() if v}
        if not roots:
            # Nothing to show: let Blender's own binding (e.g. the context menu) run.
            return {'PASS_THROUGH'}
        self.roots = roots

        self.metrics()
        self.click = (mx, my)
        self.origin = (mx, my)
        self.repositioned = False
        self.layout_roots()
        if p.reposition:
            self.reposition()

        self.trigger = event.type
        self.mouse = (event.mouse_x, event.mouse_y)
        self.prev = self.mouse
        self.open = []          # list of Panel (level 1..n) for the active quad
        self.hover = None       # (panel, row) or ('TITLE', quad)
        self.hover_gear = False
        self.pending = None     # (panel, row_or_None, start_time, delay)
        self.armed = None       # left button pressed on an item, runs on release
        self.active_quad = p.starting_quad if p.starting_quad in roots else next(iter(roots))
        self.t0 = time.perf_counter()
        self.fade = p.animation == 'FADE'
        self.space = {'VIEW_3D': bpy.types.SpaceView3D,
                      'GRAPH_EDITOR': bpy.types.SpaceGraphEditor,
                      'DOPESHEET_EDITOR': bpy.types.SpaceDopeSheetEditor}[self.area.type]
        self._handle = self.space.draw_handler_add(self.draw_px, (), 'WINDOW', 'POST_PIXEL')
        self._timer = context.window_manager.event_timer_add(0.02, window=self.window)
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def metrics(self):
        p = prefs()
        s = bpy.context.preferences.system.ui_scale or 1.0
        self.s = s
        self.fid = font_id()
        self.fs = p.menu_font_size * s
        self.tfs = p.title_font_size * s
        self.row_h = round(self.fs * 1.25 + 2 * p.vertical_margin * s)
        self.sep_h = round(7 * s)
        self.title_h = round(self.tfs * 1.25 + 6 * s)
        self.pad = round(6 * s)
        self.check_w = round(self.fs * 1.1)
        self.arrow_w = round(self.fs * 0.9)
        self.gear_w = round(self.row_h * 0.9)
        self.sc_gap = round(14 * s)
        self.gap = round(2 * s)
        self.min_w = round(p.min_width * s)
        self.max_w = round(520 * s)
        self.mirror = p.mirror_quads
        self.has_caddy = any(e.caddy for es in self.roots.values() for e in es)

    def entry_width(self, e):
        if e.kind == 'SEP':
            return 0
        w = self.pad * 2 + self.check_w + text_w(self.fid, e.label, self.fs)
        if e.shortcut:
            w += self.sc_gap + text_w(self.fid, e.shortcut, self.fs * 0.9)
        if e.kind in ('SUB', 'DYN'):
            w += self.arrow_w + self.pad
        if e.caddy:
            w += self.gear_w + self.pad
        return w

    def panel_width(self, entries, title=''):
        w = max([self.entry_width(e) for e in entries] + [self.min_w])
        if title:
            w = max(w, text_w(self.fid, title, self.tfs) + self.pad * 2)
        return min(int(w), self.max_w)

    def rows_height(self, entries):
        return sum(self.sep_h if e.kind == 'SEP' else self.row_h for e in entries)

    # --------------------------------------------------------------- layout
    def layout_roots(self):
        ox, oy = self.origin
        widths = {q: self.panel_width(es, self.titles[q]) for q, es in self.roots.items()}
        if prefs().uniform_width and widths:
            m = max(widths.values())
            widths = {q: m for q in widths}
        self.panels = {}
        for q, entries in self.roots.items():
            w = widths[q]
            h = self.title_h + self.rows_height(entries)
            x = ox - self.gap - w if q in LEFT_QUADS else ox + self.gap
            y = oy + self.gap if q in TOP_QUADS else oy - self.gap - h
            pnl = Panel(q, 0, (x, y, w, h), 'LEFT' if q in LEFT_QUADS else 'RIGHT')
            if q in TOP_QUADS:     # title next to the cursor, rows above it
                pnl.title = (x, y, w, self.title_h)
                cy = y + h
            else:
                pnl.title = (x, y + h - self.title_h, w, self.title_h)
                cy = y + h - self.title_h
            for e in entries:
                rh = self.sep_h if e.kind == 'SEP' else self.row_h
                cy -= rh
                pnl.rows.append(Row(e, (x + 1, cy, w - 2, rh)))
            self.panels[q] = pnl

    def reposition(self):
        """3ds Max 'Reposition Quad When Off Screen' + 'Move Cursor When Repositioned'."""
        if not self.panels:
            return
        m = round(4 * self.s)
        x0 = min(pn.rect[0] for pn in self.panels.values())
        y0 = min(pn.rect[1] for pn in self.panels.values())
        x1 = max(pn.rect[0] + pn.rect[2] for pn in self.panels.values())
        y1 = max(pn.rect[1] + pn.rect[3] for pn in self.panels.values())
        bx0, by0, bx1, by1 = self.bounds
        dx = dy = 0
        if x0 < bx0 + m:
            dx = bx0 + m - x0
        elif x1 > bx1 - m:
            dx = bx1 - m - x1
        if y0 < by0 + m:
            dy = by0 + m - y0
        elif y1 > by1 - m:
            dy = by1 - m - y1
        if dx or dy:
            self.origin = (self.origin[0] + dx, self.origin[1] + dy)
            self.layout_roots()
            self.repositioned = True
            if prefs().move_cursor:
                try:
                    self.window.cursor_warp(int(self.origin[0]), int(self.origin[1]))
                except (AttributeError, RuntimeError):
                    pass

    def open_submenu(self, parent_panel, row):
        e = row.entry
        kids = self.resolver.children(e)
        if not kids:
            return
        level = parent_panel.level + 1
        self.open = self.open[:level - 1]
        w = self.panel_width(kids)
        h = self.rows_height(kids) + self.pad
        px, py, pw, ph = parent_panel.rect
        bx0, by0, bx1, by1 = self.bounds
        side = parent_panel.side
        left_x, right_x = px - w + 1, px + pw - 1
        if side == 'LEFT' and left_x < bx0:
            side = 'RIGHT'
        elif side == 'RIGHT' and right_x + w > bx1:
            side = 'LEFT'
        x = left_x if side == 'LEFT' else right_x
        x = max(bx0, min(x, bx1 - w))
        top = row.rect[1] + row.rect[3] + self.pad // 2
        y = max(by0, min(top - h, by1 - h))
        pnl = Panel(parent_panel.quad, level, (x, y, w, h), side, owner=e)
        cy = y + h - self.pad // 2
        for k in kids:
            rh = self.sep_h if k.kind == 'SEP' else self.row_h
            cy -= rh
            pnl.rows.append(Row(k, (x + 1, cy, w - 2, rh)))
        self.open.append(pnl)

    def all_panels(self):
        return list(self.panels.values()) + self.open

    # ------------------------------------------------------------ hit tests
    def hit(self, x, y):
        for pnl in reversed(self.open):
            if in_rect(pnl.rect, x, y):
                for row in pnl.rows:
                    if in_rect(row.rect, x, y):
                        return pnl, row
                return pnl, None
        for q, pnl in self.panels.items():
            if pnl.title and in_rect(pnl.title, x, y):
                return 'TITLE', q
            if not self.show_all and q != self.active_quad:
                continue
            if in_rect(pnl.rect, x, y):
                for row in pnl.rows:
                    if in_rect(row.rect, x, y):
                        return pnl, row
                return pnl, None
        return None

    def gear_rect(self, pnl, row):
        x, y, w, h = row.rect
        if pnl.level == 0 and pnl.quad in LEFT_QUADS:
            return (x + self.pad // 2, y, self.gear_w, h)
        return (x + w - self.pad // 2 - self.gear_w, y, self.gear_w, h)

    def aiming(self, cur):
        """Pointer travelling toward the open submenu (safe triangle)."""
        if not self.open:
            return False
        sub = self.open[-1]
        sx, sy, sw, sh = sub.rect
        edge = sx if sub.side == 'RIGHT' else sx + sw
        return in_triangle(cur, self.prev, (edge, sy - 4), (edge, sy + sh + 4)) and cur != self.prev

    # --------------------------------------------------------------- modal
    def modal(self, context, event):
        try:
            self.area.type
        except ReferenceError:
            return self.finish(context, cancelled=True)
        p = prefs()
        t = event.type
        if t == 'TIMER':
            self.tick()
            return {'RUNNING_MODAL'}
        if t in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self.on_move((event.mouse_x, event.mouse_y))
            return {'RUNNING_MODAL'}
        if t == 'ESC' and event.value == 'PRESS':
            return self.finish(context, cancelled=True)
        if t in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
                 'NDOF_MOTION', 'MOUSEROTATE', 'MOUSESMARTZOOM'}:
            self.finish(context, cancelled=True)
            return {'CANCELLED', 'PASS_THROUGH'}
        if t == self.trigger and event.value == 'RELEASE':
            # 3ds Max: hold the button, move onto an item, release to execute.
            moved = math.hypot(event.mouse_x - self.click[0], event.mouse_y - self.click[1])
            if p.release_to_execute and moved > 10 * self.s:
                h = self.hit(event.mouse_x, event.mouse_y)
                if h and h[0] != 'TITLE' and h[1] is not None:
                    e = h[1].entry
                    if e.kind in ('OP', 'PROP') and e.available:
                        return self.run_item(context, h[0], e)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and event.value == 'PRESS':
            # Arm on press, run on release: a modal tool started from the menu (Loop Cut,
            # Knife...) must not receive the stray release of the click that chose it.
            h = self.hit(event.mouse_x, event.mouse_y)
            self.armed = None
            if h is None:
                return self.finish(context, cancelled=True)
            if h[0] == 'TITLE':
                self.armed = ('TITLE', h[1])
                return {'RUNNING_MODAL'}
            pnl, row = h
            if row is None or row.entry.kind == 'SEP':
                return {'RUNNING_MODAL'}
            e = row.entry
            if e.kind in ('SUB', 'DYN'):
                if e.available:
                    self.open_submenu(pnl, row)
                    self.pending = None
                    self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if e.available:
                caddy = e.caddy and in_rect(self.gear_rect(pnl, row), event.mouse_x, event.mouse_y)
                self.armed = (pnl, row, caddy)
            return {'RUNNING_MODAL'}
        if t == 'LEFTMOUSE' and event.value == 'RELEASE' and self.armed is not None:
            armed, self.armed = self.armed, None
            h = self.hit(event.mouse_x, event.mouse_y)
            if armed[0] == 'TITLE':
                if h != ('TITLE', armed[1]):
                    return {'RUNNING_MODAL'}
                last = LAST.get((self.qset_id, self.mode, armed[1]))
                if p.use_last_executed and last is not None:
                    return self.run_item(context, self.panels.get(armed[1]), last[1], root_uid=last[0])
                self.active_quad = armed[1]
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            pnl, row, caddy = armed
            if h is None or h[0] == 'TITLE' or h[1] is not row:
                return {'RUNNING_MODAL'}   # dragged off the item: cancel this click
            return self.run_item(context, pnl, row.entry, caddy=caddy)
        if t == 'RIGHTMOUSE' and event.value == 'PRESS' and self.trigger != 'RIGHTMOUSE':
            return self.finish(context, cancelled=True)
        if t == 'RIGHTMOUSE' and event.value == 'PRESS':
            # Max: right-click anywhere closes the quad menu.
            return self.finish(context, cancelled=True)
        return {'RUNNING_MODAL'}

    def tick(self):
        redraw = False
        if self.fade:
            p = prefs()
            dur = (len(FADE_ORDER) - 1) * p.fade_pause / 1000.0 + p.fade_steps * 0.016
            if time.perf_counter() - self.t0 <= dur + 0.05:
                redraw = True
            else:
                self.fade = False
                redraw = True
        if self.pending is not None:
            pnl, row, start, delay = self.pending
            if time.perf_counter() - start >= delay:
                self.pending = None
                self.apply_hover(pnl, row)
                redraw = True
        if redraw:
            self.area.tag_redraw()

    def apply_hover(self, pnl, row):
        if row is not None and row.entry.kind in ('SUB', 'DYN') and row.entry.available:
            self.open_submenu(pnl, row)
        else:
            self.open = self.open[:pnl.level]

    def on_move(self, cur):
        p = prefs()
        h = self.hit(*cur)
        old = (self.hover, self.hover_gear)
        self.hover_gear = False
        if h is None:
            self.hover = None
        elif h[0] == 'TITLE':
            self.hover = h
            if not self.show_all and self.active_quad != h[1]:
                self.active_quad = h[1]
                self.open = []
        else:
            pnl, row = h
            self.hover = (pnl, row) if row is not None else None
            if pnl.level == 0 and pnl.quad != self.active_quad:
                self.active_quad = pnl.quad
            if row is not None and row.entry.kind != 'SEP':
                e = row.entry
                if e.caddy:
                    self.hover_gear = in_rect(self.gear_rect(pnl, row), *cur)
                child_open = len(self.open) > pnl.level and self.open[pnl.level].owner is e
                needs_change = (e.kind in ('SUB', 'DYN') and not child_open) or \
                               (e.kind not in ('SUB', 'DYN') and len(self.open) > pnl.level)
                if needs_change:
                    delay = p.submenu_pause / 1000.0
                    if len(self.open) > pnl.level and self.aiming(cur):
                        delay += 0.35
                    if delay <= 0:
                        self.pending = None
                        self.apply_hover(pnl, row)
                    elif self.pending is None or self.pending[1] is not row:
                        self.pending = (pnl, row, time.perf_counter(), delay)
                else:
                    self.pending = None
        self.prev = cur
        if (self.hover, self.hover_gear) != old:
            self.area.tag_redraw()

    # ------------------------------------------------------------- finish
    def remove_handlers(self, context):
        if getattr(self, '_handle', None) is not None:
            self.space.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        if getattr(self, '_timer', None) is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def finish(self, context, cancelled=True):
        self.remove_handlers(context)
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def run_item(self, context, pnl, e, caddy=False, root_uid=None):
        quad = pnl.quad if pnl is not None else self.active_quad
        if root_uid is None:
            root_uid = self.open[0].owner.uid if (pnl is not None and pnl.level > 0 and self.open) else e.uid
        LAST[(self.qset_id, self.mode, quad)] = (root_uid, e)
        self.remove_handlers(context)
        p = prefs()
        interactive = (e.kind == 'OP' and e.invoke and not caddy
                       and not e.operator.startswith(('TOOL:', 'SPECIAL:')))
        # Interactive tools start where the menu was opened: Loop Cut previews/slides the
        # edge ring you right-clicked, Knife starts there, Extrude drags from there.
        if (interactive and p.start_at_click) or \
                (self.repositioned and p.move_cursor and p.return_cursor):
            try:
                self.window.cursor_warp(int(self.click[0]), int(self.click[1]))
            except (AttributeError, RuntimeError):
                pass
        try:
            with context.temp_override(window=self.window, area=self.area, region=self.region):
                actions.run_entry(bpy.context, e, caddy=caddy)
        except Exception as exc:
            self.report({'WARNING'}, 'BMAX Quad: %s' % exc)
            return {'CANCELLED'}
        return {'FINISHED'}

    # ---------------------------------------------------------------- draw
    def quad_alpha(self, quad):
        if not self.fade:
            return 1.0
        p = prefs()
        i = FADE_ORDER.index(quad)
        el = time.perf_counter() - self.t0 - i * p.fade_pause / 1000.0
        return max(0.0, min(1.0, el / max(0.001, p.fade_steps * 0.016)))

    def colors(self, quad):
        p = prefs()
        if p.lock_colors:
            return p.col_title_active, p.col_highlight
        return getattr(p, 'col_title_active_' + quad), getattr(p, 'col_highlight_' + quad)

    def draw_px(self):
        if getattr(self, '_handle', None) is None:
            return
        region = bpy.context.region
        if region is None or region.as_pointer() not in self.region_ptrs:
            return
        try:
            gpu.state.blend_set('ALPHA')
            self.draw_all(region.x, region.y)
        except Exception as exc:  # never break viewport drawing
            print('BMAX Quad draw error:', exc)
        finally:
            gpu.state.blend_set('NONE')

    def draw_all(self, rx, ry):
        p = prefs()
        op = p.opacity
        last_roots = {q: v[0] for (sid, mode, q), v in LAST.items()
                      if sid == self.qset_id and mode == self.mode}
        open_owners = {pn.owner.uid for pn in self.open if pn.owner is not None}
        for q, pnl in self.panels.items():
            a = op * self.quad_alpha(q)
            if a <= 0:
                continue
            full = self.show_all or q == self.active_quad
            self.draw_panel(pnl, rx, ry, a, full, last_roots.get(q), open_owners)
        for pnl in self.open:
            self.draw_panel(pnl, rx, ry, op, True, None, open_owners)
        # cursor origin marker
        ox, oy = self.origin
        rect(ox - rx - 2 * self.s, oy - ry - 2 * self.s, 4 * self.s, 4 * self.s,
             mul_alpha(p.col_title_active, op))

    def draw_panel(self, pnl, rx, ry, a, full, last_uid, open_owners):
        p = prefs()
        title_active, highlight = self.colors(pnl.quad)
        x, y, w, h = pnl.rect
        x -= rx
        y -= ry
        t = max(1, round(self.s))
        if full:
            rect(x - t, y - t, w + 2 * t, h + 2 * t, mul_alpha(p.col_border, a))
            rect(x, y, w, h, mul_alpha(p.col_background, a))
        if pnl.title:
            tx, ty, tw, th = pnl.title
            tx -= rx
            ty -= ry
            if not full:
                rect(tx - t, ty - t, tw + 2 * t, th + 2 * t, mul_alpha(p.col_border, a))
            is_active = pnl.quad == self.active_quad
            hov = self.hover is not None and self.hover[0] == 'TITLE' and self.hover[1] == pnl.quad
            col = title_active if (is_active or hov) else p.col_title
            rect(tx, ty, tw, th, mul_alpha(col, a))
            label = self.titles.get(pnl.quad, '')
            lw = text_w(self.fid, label, self.tfs)
            # 3ds Max: the quad title sits next to the cursor corner
            lx = tx + tw - self.pad - lw if pnl.quad in LEFT_QUADS else tx + self.pad
            text(self.fid, label, lx, ty + (th - self.tfs * 0.75) / 2, self.tfs,
                 mul_alpha(p.col_title_text, a))
        if not full:
            return
        hover_row = self.hover[1] if (self.hover and self.hover[0] is pnl) else None
        for row in pnl.rows:
            self.draw_row(pnl, row, rx, ry, a, row is hover_row, last_uid, open_owners, highlight)

    def draw_row(self, pnl, row, rx, ry, a, hovered, last_uid, open_owners, highlight):
        p = prefs()
        e = row.entry
        x, y, w, h = row.rect
        x -= rx
        y -= ry
        if e.kind == 'SEP':
            rect(x + self.pad, y + h / 2, w - 2 * self.pad, max(1, round(self.s)),
                 mul_alpha(p.col_border, a * 0.9))
            return
        if hovered and e.available:
            rect(x, y, w, h, mul_alpha(highlight, a))
        elif e.uid in open_owners:
            rect(x, y, w, h, mul_alpha(highlight, a * 0.6))
        elif last_uid and e.uid == last_uid:
            rect(x, y, w, h, mul_alpha(p.col_last, a))
        col = p.col_text if e.available else p.col_disabled
        col = mul_alpha(col, a)
        mirror_left = pnl.level == 0 and pnl.quad in LEFT_QUADS
        arrow_left = pnl.side == 'LEFT'
        ty = y + (h - self.fs * 0.72) / 2

        # slots from both edges
        left, right = x + self.pad, x + w - self.pad
        if e.caddy:
            gx, gy, gw, gh = self.gear_rect(pnl, row)
            gx -= rx
            gy -= ry
            size = min(gw, gh) * 0.55
            cx, cy = gx + gw / 2, gy + gh / 2
            box_col = p.col_text if (hovered and self.hover_gear) else p.col_shortcut
            outline(cx - size / 2, cy - size / 2, size, size, max(1, round(self.s)), mul_alpha(box_col, a))
            if hovered and self.hover_gear:
                rect(cx - size / 4, cy - size / 4, size / 2, size / 2, mul_alpha(box_col, a))
            if mirror_left:
                left = gx + gw + self.pad // 2
            else:
                right = gx - self.pad // 2
        if e.kind in ('SUB', 'DYN'):
            aw = self.arrow_w * 0.45
            cy = y + h / 2
            if arrow_left:
                ax = left + aw * 0.2
                tris([(ax, cy), (ax + aw, cy + aw), (ax + aw, cy - aw)], col)
                left += self.arrow_w
            else:
                ax = right - aw * 0.2
                tris([(ax, cy), (ax - aw, cy + aw), (ax - aw, cy - aw)], col)
                right -= self.arrow_w
        # check mark area
        if mirror_left and self.mirror:
            check_x = right - self.check_w
            right -= self.check_w
        else:
            check_x = left
            left += self.check_w
        if e.checked:
            cs = self.check_w * 0.55
            bx, by = check_x + (self.check_w - cs) / 2, y + h / 2
            lt = max(1.5, 1.6 * self.s)
            thick_line((bx, by), (bx + cs * 0.38, by - cs * 0.4), lt, col)
            thick_line((bx + cs * 0.38, by - cs * 0.4), (bx + cs, by + cs * 0.5), lt, col)
        # shortcut
        sc_w = 0
        if e.shortcut:
            sfs = self.fs * 0.9
            sc_w = text_w(self.fid, e.shortcut, sfs)
            sc_col = mul_alpha(p.col_shortcut, a)
            if mirror_left and self.mirror:
                text(self.fid, e.shortcut, left, ty, sfs, sc_col)
                left += sc_w + self.sc_gap
            else:
                text(self.fid, e.shortcut, right - sc_w, ty, sfs, sc_col)
                right -= sc_w + self.sc_gap
        label = fit(self.fid, e.label, self.fs, max(10, right - left))
        if mirror_left and self.mirror:
            text(self.fid, label, right - text_w(self.fid, label, self.fs), ty, self.fs, col)
        else:
            text(self.fid, label, left, ty, self.fs, col)


class BMAXQUAD_OT_invoke_item(Operator):
    """Run a single quad item through its own shortcut."""
    bl_idname = 'bmaxquad.invoke_item'
    bl_label = 'Run BMAX Quad Item'
    bl_options = {'INTERNAL'}
    uid: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        it = next((x for x in prefs().items if x.uid == self.uid), None)
        if it is None or not it.enabled or it.kind not in {'OP', 'PROP'}:
            return {'PASS_THROUGH'}
        mode = actions.current_mode(context)
        if it.mode not in {'GLOBAL', mode}:
            return {'PASS_THROUGH'}
        e = actions.ns(uid=it.uid, kind=it.kind, label=it.label, operator=it.operator,
                       kwargs=it.kwargs, invoke=it.invoke, path=it.path, value=it.value)
        try:
            region = context.region
            if region is None or region.type != 'WINDOW':
                region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
            with context.temp_override(area=context.area, region=region):
                actions.run_entry(bpy.context, e)
        except Exception as exc:
            self.report({'WARNING'}, 'BMAX shortcut: %s' % exc)
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (BMAXQUAD_OT_show, BMAXQUAD_OT_invoke_item)
