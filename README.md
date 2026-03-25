[![PayPal Donate](screenshots/paypal.png)](https://www.paypal.com/donate/?hosted_button_id=MG5S4EPK6EUSL)
# Icon Builder
![Electron](https://img.shields.io/badge/Electron-28-47848F?logo=electron) ![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows) ![License](https://img.shields.io/badge/License-MIT-green)

Convert AI-generated images into Windows desktop icons and store them in a `.dll` file — no compiler, no external tools, pure Python.

Built for use with [ComfyUI](https://github.com/comfyanonymous/ComfyUI) but works with any image source.

---

## What it does

1. **Converts** PNG, WEBP, or JPG images into multi-resolution `.ico` files (8 sizes: 16–256px)
![Preview](screenshots/preview1.jpg) ![Preview](screenshots/preview2.png)
2. **Packages** all icons into a single `AiB_icon_library.dll` resource file
![Preview](screenshots/preview3.jpg)
3. **Applies** icons to any Windows folder or shortcut via desktop [fastest recommended], or command line
![Preview](screenshots/preview4.png)

The DLL is a standard Windows resource-only PE32+ binary — no C compiler required. It is built entirely in Python and is compatible with Windows' native **Change Icon** dialog, `LoadIcon()`, and all shell contexts.

---

## Requirements

- **Windows** (icon application requires Windows APIs)
- **Python 3.9+**
- **Pillow** — image processing
- **pywin32** — Windows shell integration (only needed for the `apply` command)

---

## Installation

Choose the option that matches your setup.

---

### Option A — System Python

If you have Python installed from [python.org](https://python.org):

**1. Check Python is installed:**
```
python --version
```
If this fails, download Python from https://python.org. During installation, check **"Add Python to PATH"**.

**2. Install dependencies:**
```
pip install pillow pywin32
```

**3. Edit `run.bat`** — open it in Notepad so it reads:
```bat
@echo off
cd /d "%~dp0"
python icon_tool.py build
pause
```

**4. Double-click `run.bat`** or run from a command prompt:
```
python icon_tool.py build
```

---

### Option B — ComfyUI portable (embedded Python)

ComfyUI's Windows portable release ships with its own Python inside `python_embeded\`. It does not use your system Python — you need to point the script at it directly.

**1. Find your ComfyUI Python path**, e.g.:
```
D:\ComfyUI_windows_portable\python_embeded\python.exe
```

**2. Install dependencies using that exact Python:**
```
D:\ComfyUI_windows_portable\python_embeded\python.exe -m pip install pillow pywin32
```
Replace the path with your actual ComfyUI location.

**3. Edit `run.bat`** — replace the python line with the full path:
```bat
@echo off
cd /d "%~dp0"
D:\ComfyUI_windows_portable\python_embeded\python.exe icon_tool.py build
pause
```

**4. Double-click `run.bat`** — done.

> You can also create a shortcut to `run.bat` and keep it anywhere.

---

### Quick comparison

| Setup | Edit run.bat? | Install command |
|---|---|---|
| System Python | Set to `python icon_tool.py build` | `pip install pillow pywin32` |
| ComfyUI portable | Replace python with full embedded path | `D:\...\python_embeded\python.exe -m pip install pillow pywin32` |

---

## Folder structure

```
IconTool/
    icon_tool.py              ← main script
    run.bat                   ← one-click build
    images/                    ← drop your source images here
        your_image.png
        another_image.webp
        something.jpg
    icons/                    ← created automatically
        your_icon.ico
        another_icon.ico
    AiB_icon_library.dll      ← created automatically
```

> **Tip:** You can also drop pre-made `.ico` files directly into the `icons/` folder — they will be picked up and packaged into the DLL on the next build without needing a source image.

---

## Usage

### Build — convert images to ICO and package into DLL

```bash
python icon_tool.py build
```

Converts every `.png`, `.webp`, `.jpg`, and `.jpeg` in the `input/` folder into multi-resolution `.ico` files, then packages **all** icons in the `icons/` folder (including any pre-existing ones) into `AiB_icon_library.dll`.

### List — show all icons stored in the DLL

```bash
python icon_tool.py list
```

### Apply — apply an icon to a folder or shortcut

```bash
python icon_tool.py apply
```

You will be prompted to enter an icon number and drag/paste a folder path or `.lnk` shortcut path.

- **Folders** — writes a `desktop.ini` instructing Windows Explorer to use the custom icon
- **Shortcuts (.lnk)** — updates the shortcut's icon location property directly

> After applying, right-click your desktop and choose **Refresh**, or press **F5** in Explorer.

### Clear cache — force Windows to reload all icons

```bash
python icon_tool.py clearcache
```

Briefly restarts Explorer to flush the Windows icon cache. Use this if icons appear stale or don't update after applying.

---

## Applying icons manually (no command line)

You can also apply icons from the Windows right-click menu without using the `apply` command:

1. Right-click the shortcut → **Properties**
2. Click **Change Icon**
3. Click **Browse** and navigate to `AiB_icon_library.dll`
4. Select your icon → **OK** → **Apply** → **OK**

This is the recommended method for applying icons to desktop shortcuts.

---

## Icon image guidelines

For sharp icons at all display sizes, generate your source images with these settings:

| Setting | Recommendation |
|---|---|
| Resolution | 1024×1024px, square |
| Background | Plain solid color or simple gradient — no scenes or environments |
| Subject | Centered, filling 70–80% of the canvas |
| Style | Bold shapes, high contrast, no fine detail or small text |
| Format | PNG with transparency (RGBA) preferred; WEBP and JPG also supported |

**ComfyUI prompt additions:**
```
plain black background, centered composition, close crop,
bold simple shapes, icon design, no background detail
```

Icons are displayed at 16–96px depending on context. Fine photographic detail will appear soft at small sizes — bold, simple, high-contrast images work best.

---

## ICO format details

Each `.ico` file produced contains 8 frames:

| Size | Format | Used for |
|---|---|---|
| 256×256 | BMP DIB | High-DPI displays, large icon view |
| 128×128 | BMP DIB | Large icon view |
| 96×96 | BMP DIB | Desktop icons (150% DPI) |
| 64×64 | BMP DIB | Desktop icons (125% DPI) |
| 48×48 | BMP DIB | Desktop icons (100% DPI) |
| 32×32 | BMP DIB | Taskbar, dialog boxes |
| 24×24 | BMP DIB | Taskbar (small) |
| 16×16 | BMP DIB | Explorer details view, menus |

All frames use BMP DIB format with a proper AND mask derived from the image's alpha channel, ensuring correct transparency rendering in all Windows shell contexts.

---

## DLL format details

`AiB_icon_library.dll` is a valid Windows PE32+ resource-only DLL containing:

- `RT_ICON` (type 3) — one entry per icon frame
- `RT_GROUP_ICON` (type 14) — one group entry per original icon

It is compatible with:
- Windows **Change Icon** dialog (right-click → Properties → Change Icon → Browse)
- `LoadLibraryEx` + `LoadIcon` / `LoadImage` (C/C++)
- `System.Drawing.Icon` (C# / .NET)
- `win32gui.LoadImage` (Python + pywin32)

Icons are stored largest-first (256px at index 0) so Windows always selects the highest quality frame available.

---

## Using the DLL in other tools

The DLL is a standard Windows resource file — not just useful for desktop icons. If you are a developer and want to use the icon library inside your own application, it works with any language that can load Windows resources.

<details>
<summary>🛠️ Developer reference — loading icons from the DLL in code</summary>

<br>

**C / C++**
```c
HMODULE dll  = LoadLibraryEx("AiB_icon_library.dll", NULL, LOAD_LIBRARY_AS_DATAFILE);
HICON   icon = LoadIcon(dll, MAKEINTRESOURCE(1));  // 1 = first icon
```

**C# / WPF**
```csharp
var icon = new System.Drawing.Icon("AiB_icon_library.dll", new Size(32, 32));
```

**Python (pywin32)**
```python
import win32api, win32con, win32gui
dll  = win32api.LoadLibraryEx("AiB_icon_library.dll", 0, win32con.LOAD_LIBRARY_AS_DATAFILE)
icon = win32gui.LoadImage(dll, 1, win32con.IMAGE_ICON, 32, 32, 0)
```

</details>

---

## Configuration

At the top of `icon_tool.py`:

```python
PNG_FOLDER  = "images"                 # folder containing your source images
ICON_FOLDER = "icons"                 # where .ico files are saved
DLL_PATH    = "AiB_icon_library.dll"  # output DLL path
```

Change these paths if you want to keep your images, ICOs, and DLL in separate locations.

---

## Troubleshooting

**Icon appears blurry on the desktop**
This is expected for photographic images at small sizes. Regenerate your source image with a plain background and bold, simple shapes. See [Icon image guidelines](#icon-image-guidelines).

**"The file contains no icons" in Change Icon dialog**
Delete the old `AiB_icon_library.dll`, delete the `__pycache__` folder, and run `python icon_tool.py build` again.

**Icon does not update after applying**
Right-click your desktop → **Refresh**, or press **F5** in Explorer. If still not updated, run `python icon_tool.py clearcache`, or open the shortcut's Properties → Change Icon → browse to the DLL and reselect the icon.

**`ModuleNotFoundError: No module named 'win32com'`**
Run `pip install pywin32`. The `apply` command requires pywin32 for shortcut manipulation.

---

## Dependencies

| Package | Purpose | Required for |
|---|---|---|
| `pillow` | Image resizing and format conversion | `build` command |
| `pywin32` | Windows shell API, shortcut editing | `apply` command only |

The `build` command runs on any Python 3.9+ with only Pillow installed. `pywin32` is only needed if you use `python icon_tool.py apply`. Manual application through the Windows right-click menu requires no additional dependencies.

---

## License

MIT

---
## *Built with 💜 by [Apolonia](https://github.com/ApoloniArt) & [Hans](https://github.com/hwprinz) to reclaim your time from the mundane.*

---
#### If any of my little apps, tools, nodes or scripts have helped save you time or brought you joy, feel free to shower me with copious amounts of gifts 🤭 here: [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=MG5S4EPK6EUSL) or hit the button at the top☝️ Any support at all is hugely appreciated, even a star or nice comment🙏
