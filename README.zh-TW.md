# BMAX Quad Menu

**Blender 的 3ds Max 風格四象限選單** · [English](README.md)

![BMAX Quad Menu](docs/images/preview.webp)

BMAX Quad Menu 把 3ds Max 的 Quad Menu 帶進 Blender：

- 游標周圍四個象限。
- 多組 Quad Set，各自用不同快捷鍵開啟。
- 選單內容會跟著選取的物件和子物件層級改變。
- 完整的 Advanced Quad Menu Options。

所有指令都是 Blender 原生的 operator。

**[⬇ 下載 v1.1.0](https://github.com/Aomay77/BMAX-Quad-Menu/releases/latest)** · 需要 Blender 4.2 以上，以 Blender 5.3 開發與測試

> **安裝後預設不啟動任何選單。** 你自己啟用 Quad Set 並設定快捷鍵之前，Blender 的選單和快捷鍵都不會改變。

## 功能

**3ds Max 的版面**
- Quad 1 右下 **transform**、Quad 2 右上 **display**、Quad 3 左上 **tools 1**、Quad 4 左下 **tools 2**，標題列在游標旁會合。
- **tools 1 / tools 2 會跟著狀況改變：**
  - 選燈光：出現 Light Type、Cast Shadows。
  - 選攝影機：出現攝影機工具。
  - Edit Mesh：Vertex、Edge、Polygon 層級各自顯示對應的 Editable Poly 工具，例如 Weld、Chamfer、Bridge、Inset。
- **不能用的指令會隱藏**，整格沒有項目就不顯示（同 3ds Max）。也可以改成灰色顯示。

**Quad Set。** 每組各自有快捷鍵，預設全部關閉，並預先建議 3ds Max 的組合鍵：

| Quad Set | 建議快捷鍵 |
|---|---|
| Default（transform / display / tools 1 / tools 2） | 右鍵 |
| Modeling | Ctrl + 右鍵 |
| Animation | Alt + 右鍵 |
| Snap | Shift + 右鍵 |
| Lighting \| Render | Ctrl + Alt + 右鍵 |
| Custom ×2 | Ctrl + Shift（+ Alt）+ 右鍵 |
| Viewports | V |
| Track View | 在 Dope Sheet / Timeline / Graph Editor 按右鍵 |

**任何快捷鍵都能用。** 按 ⏺ **Record** 後直接按下組合鍵就會設定並啟用。可用的鍵包括：鍵盤按鍵、數字鍵盤、F1–F24、滑鼠右鍵／中鍵、側鍵 4–7、滾輪、3D 滑鼠按鈕，都可以搭配 Ctrl／Shift／Alt／OS。
- 用滑鼠側鍵、F13–F24 這類沒被佔用的鍵，就不會蓋掉任何東西。
- 設定頁會列出這個快捷鍵會蓋掉哪些 Blender 快捷鍵。

**操作**
- **點象限標題**：重複這個象限上次用的指令，上次用的項目會保持高亮。
- **按住、移動、放開**：按住觸發鍵，移到項目上放開就執行。
- **設定框（□）**：
  - 在指令旁：執行指令並打開 Blender 的 *Adjust Last Operation*。
  - 在 Move／Rotate／Scale 旁：開關側邊欄，可以輸入數值（類似 3ds Max 的 Transform Type-In）。
- **互動工具從點擊的位置開始**：Loop Cut 的預覽和 Slide 會出現在你右鍵點的那條邊，不會跑到選單項目的位置。Knife、Extrude 也一樣。
- **勾選狀態**：X-Ray、著色模式、子物件層級、Auto Key、Snap 等都會顯示 ✓。
- **快捷鍵提示**：指令在 Blender 裡有快捷鍵的話，會顯示在項目右側。
- **子選單**：稍微延遲才展開，斜著移向已開啟的子選單時不會被切掉。
- **中鍵、滾輪**：關閉選單並照常導航視圖。
- **四分割視圖（Ctrl+Alt+Q）**：選單可以橫跨四個視窗。

**Advanced Quad Menu Options**（與 3ds Max 相同分組）
- **Colors**：可每個象限不同色，或鎖定共用；Starting Quadrant。
- **Display**：Uniform Quad Width、Mirror Quads、Vertical Margins、Opacity。
- **Positioning**：超出畫面時自動移位、Move Cursor、Return Cursor。
- **Fonts**：標題與選單字級，可指定字型檔（顯示中文時好用）。
- **Animation**：Fade（Steps、Pause）。

## 安裝

1. 從 [Releases](https://github.com/Aomay77/BMAX-Quad-Menu/releases/latest) 下載 `BMAX_Quad_Menu_v1_1_0.zip`，不要解壓縮。
2. Blender → **Edit → Preferences → Add-ons → 右上 ▾ → Install from Disk** → 選 ZIP，啟用 **BMAX Quad Menu**。
3. 到 **Quad Sets** 頁籤選一組 → 按 **⏺ Record** → 按下你的快捷鍵，這組就會啟用。

**從 v0.0.x 或 v0.1 更新：**
- 請先停用並移除舊版。
- 第一次啟動時會自動匯入舊的 `menus.json`：每個 Page 變成一組「Imported · 頁名」，保留原本的快捷鍵，但先關閉。原檔案不會被改動。
- 之後也可以按 **Import old menus.json** 再匯入一次。

## 編輯選單

到 **Preferences → BMAX Quad Menu → Menu Editor**，或 3D View 側邊欄 → **BMAX Quad** 頁籤：

1. 選 **Quad Set** 和**模式**（Object、Edit Mesh…，或用 *Global* 當作後備），再點四格象限按鈕的其中一格。
2. 可以新增**指令**、**開關**、**子選單**、**動態子選單**、**分隔線**。也可以刪除、複製、排序、進入子選單，或移到其他象限。
3. **最快的加法**：在 Blender 任何按鈕上按右鍵 → **Add to BMAX Quad**。屬性按鈕（例如 X-Ray、Snap）會變成帶 ✓ 的開關。
4. **從剪貼簿加**：在按鈕上右鍵 → **Copy Python Command**，再到編輯器按 📋。內容只會解析，不會被執行。
5. **Show When** 可以限制項目只在特定物件類型、有選取、Isolate 中，或特定子物件層級時顯示。
6. 單一項目也可以設定自己的快捷鍵。

設定會自動存到 Blender 設定資料夾的 `bmax_quad_menu/bmax_quad.json`。在設定頁還可以：
- **Save As / Load**：備份或分享設定。
- **Restore Missing Defaults**：補回缺少的內建項目，不會修改或刪除你的項目。
- **Reset to 3ds Max Defaults**：會先備份再重設。

## 驗證狀態

v1.1.0 在 Blender 5.3 以 headless 方式完成自動測試，全部通過：
- 每個內建指令、參數、工具、屬性路徑都存在於 Blender 5.3。
- 內容切換與勾選狀態正確。
- Keymap 的註冊與移除正確。
- 存檔與讀檔一致，舊版 v0.0.x／v0.1 設定能正確遷移。
- 設定頁 UI 與編輯器正常。
- 選單繪製以離屏渲染驗證，上方截圖就是渲染結果。

以下需要實際使用後的回饋：
- 視窗中的滑鼠操作。
- 設定框的彈出視窗。
- 游標移位（Linux Wayland 可能不支援）。
- 與其他外掛的快捷鍵優先順序。

有問題請到 [Issues](https://github.com/Aomay77/BMAX-Quad-Menu/issues) 回報，並附上 System Console 的訊息或錄影。

版本紀錄見 [CHANGELOG.md](CHANGELOG.md)。

*3ds Max 是 Autodesk, Inc. 的商標。本專案與 Autodesk 無關，只是用 Blender 自己的 operator 重現 Quad Menu 的操作方式。*
