# Changelog / 版本紀錄

## v1.1.0 — 2026-11-19

**English**
- **Nothing is enabled by default.** No quad set is active after install, so Blender menus are never overridden. Configs saved by v1.0.0 load with every set switched off once.
- **Any shortcut can open a quad set.** This covers every Blender key, mouse button and NDOF button, with any Ctrl / Shift / Alt / OS combination. ⏺ Record sets the shortcut and switches the set on.
- **Interactive tools start at the click point.** Before running Loop Cut, Knife, Extrude and similar tools, the cursor returns to where the menu was opened. Loop Cut previews and slides on the edge you right-clicked. The option is in Advanced Options → Behavior.
- **Menu items run on mouse release.** A modal tool started from the menu no longer receives a stray release event.
- Old `menus.json` files from v0.0.x and v0.1 are imported as *Imported · page* sets, keeping their shortcuts, switched off.

**繁體中文**
- **預設不啟動任何 Quad Set**，不會蓋掉 Blender 選單。v1.0.0 存的設定載入時，所有 Set 會先關閉一次。
- **任何快捷鍵都能開啟 Quad Set**：所有 Blender 按鍵、滑鼠鍵、3D 滑鼠按鈕，可搭配 Ctrl／Shift／Alt／OS。⏺ Record 錄製後自動啟用。
- **互動工具從點擊位置開始**：執行 Loop Cut、Knife、Extrude 等工具前，游標會回到開選單的位置，Loop Cut 的預覽與 Slide 會出現在你右鍵點的那條邊。可在 Advanced Options → Behavior 關閉。
- **選單項目在放開滑鼠時才執行**，避免 modal 工具收到多出來的放開事件。
- v0.0.x 與 v0.1 的 `menus.json` 會匯入成「Imported · 頁名」，保留快捷鍵，但先關閉。

## v1.0.0 — 2026-11-19

**English**
- Complete rewrite in modules: model / defaults / actions / overlay / keymaps / ui. Packaged as an extension with `blender_manifest.toml`.
- Implements the 3ds Max quad menu behavior:
  - Quad numbering and titles.
  - Context-sensitive tools 1 / tools 2.
  - Quad sets.
  - Click a quad title to repeat the last command; last-used item highlighted.
  - Hold-move-release.
  - Settings box.
  - Advanced Quad Menu Options: colors, display, positioning, fonts, fade.
- Fixes from v0.0.x / v0.1:
  - Quad View support.
  - HiDPI scaling and CJK text width.
  - Check marks and hotkey hints.
  - Submenu delay that tolerates diagonal movement.
  - Viewport navigation passes through.
  - Settings stored in one JSON file.
  - Q3 is no longer replaced.
- In-Blender editor:
  - Right-click any button → Add to BMAX Quad.
  - Show When conditions.
  - Dynamic submenus.
  - Per-item shortcuts.

**繁體中文**
- 全部重寫並拆成模組：model / defaults / actions / overlay / keymaps / ui。以 Extension 格式打包（`blender_manifest.toml`）。
- 實作 3ds Max Quad Menu 的行為：
  - 象限編號與標題。
  - 依狀況變化的 tools 1 / tools 2。
  - Quad Set。
  - 點標題重複上次指令，上次用的項目保持高亮。
  - 按住、移動、放開即執行。
  - 設定框。
  - Advanced Quad Menu Options：顏色、顯示、定位、字型、淡入。
- 修正 v0.0.x / v0.1 的問題：
  - 支援四分割視圖。
  - HiDPI 縮放與中文寬度正確。
  - 勾選狀態與快捷鍵提示。
  - 子選單延遲，斜向移動不會被切掉。
  - 視圖導航照常運作。
  - 設定只存一份 JSON。
  - Q3 不再被覆蓋。
- Blender 內建編輯器：
  - 在任何按鈕右鍵 → Add to BMAX Quad。
  - Show When 顯示條件。
  - 動態子選單。
  - 單一項目快捷鍵。

## v0.1 and earlier / 舊版

Original single-file version. It is still available from the [v0.1 release](https://github.com/Aomay77/BMAX-Quad-Menu/releases/tag/v0.1).

最初的單一檔案版本，仍可從 [v0.1 release](https://github.com/Aomay77/BMAX-Quad-Menu/releases/tag/v0.1) 下載。
