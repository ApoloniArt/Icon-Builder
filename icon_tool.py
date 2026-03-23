"""
icon_tool.py  —  One script to rule them all
============================================
WHAT IT DOES:
  1. Converts any PNG, WEBP, JPG/JPEG images into proper Windows .ico files (all sizes)
  2. Stores all icons in a single icon_library.dll (no compiler needed)
  3. Applies any icon to any folder or shortcut on your Windows desktop

REQUIREMENTS (install once):
  pip install pillow pywin32

USAGE:
  python icon_tool.py build          # convert PNGs → .ico → .dll
  python icon_tool.py apply          # pick an icon, pick a folder/shortcut, done
  python icon_tool.py list           # show all icons stored in the dll
  python icon_tool.py clearcache     # force Windows to reload icon cache
"""

import sys, os, struct, io, ctypes, glob

# ──────────────────────────────────────────────
# CONFIG — change these if needed
# ──────────────────────────────────────────────
PNG_FOLDER  = "input"                 # folder containing your ComfyUI PNG exports
ICON_FOLDER = "icons"             # where .ico files are saved (created automatically)
DLL_PATH    = "AiB_icon_library.dll"  # your icon store (created automatically)
ICO_SIZES   = [16, 24, 32, 48, 64, 128, 256]


# ══════════════════════════════════════════════
# STEP 1 — PNG → ICO  (multi-resolution)
# ══════════════════════════════════════════════

def _make_bmp_dib(img: 'Image') -> bytes:
    """
    Convert an RGBA PIL image to BMP DIB format for use in .ico files.
    Uses a proper AND mask derived from the alpha channel so transparency
    renders correctly in the Windows shell at all icon sizes.
    """
    w, h  = img.size
    img   = img.convert('RGBA')

    # XOR mask: BGRA pixels, rows stored bottom-up
    xor_rows = []
    for row_y in range(h - 1, -1, -1):
        row = b''
        for x in range(w):
            r, g, b, a = img.getpixel((x, row_y))
            row += bytes([b, g, r, a])
        xor_rows.append(row)
    xor_mask = b''.join(xor_rows)

    # AND mask: 1bpp, 1=transparent 0=opaque, rows bottom-up, 4-byte aligned
    and_row_bytes = ((w + 31) // 32) * 4
    and_mask      = bytearray()
    for row_y in range(h - 1, -1, -1):
        row = bytearray(and_row_bytes)
        for x in range(w):
            if img.getpixel((x, row_y))[3] < 128:   # transparent
                row[x // 8] |= (0x80 >> (x % 8))
        and_mask.extend(row)

    # BITMAPINFOHEADER — height is doubled to account for AND mask
    bi = struct.pack('<IiiHHIIiiII',
        40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)

    return bi + xor_mask + bytes(and_mask)


def png_to_ico(png_path: str, ico_path: str):
    """
    Convert a PNG to a proper multi-resolution .ico file.
    All sizes stored as BMP DIB for maximum Windows shell compatibility.
    Includes 96px size for standard-DPI desktop icons.
    """
    from PIL import Image

    # Largest first — Windows uses index 0 for shortcuts, so 256px must be first
    ICO_SIZES_ALL = [256, 128, 96, 64, 48, 32, 24, 16]

    src    = Image.open(png_path).convert("RGBA")
    frames = [src.resize((s, s), Image.LANCZOS) for s in ICO_SIZES_ALL]
    bufs   = [_make_bmp_dib(img) for img in frames]

    n      = len(bufs)
    out    = io.BytesIO()
    out.write(struct.pack('<HHH', 0, 1, n))

    offset = 6 + n * 16
    for img, data in zip(frames, bufs):
        w = 0 if img.size[0] >= 256 else img.size[0]
        out.write(struct.pack('<BBBBHHII', w, w, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for data in bufs:
        out.write(data)

    with open(ico_path, 'wb') as f:
        f.write(out.getvalue())


# ══════════════════════════════════════════════
# STEP 2 — ICOs → DLL  (pure Python, no compiler)
# ══════════════════════════════════════════════

def _align(val: int, a: int) -> int:
    return (val + a - 1) & ~(a - 1)


def _build_rsrc(rt_icon: list, rt_group: list, rsrc_rva: int) -> bytes:
    """
    Build a Windows .rsrc section containing RT_ICON (type 3) and
    RT_GROUP_ICON (type 14) resource entries.

    rsrc_rva: the virtual address where this section will be loaded.
              IMAGE_RESOURCE_DATA_ENTRY.OffsetToData must be an absolute VA,
              i.e. rsrc_rva + offset_within_section.
    """
    RT_ICON       = 3
    RT_GROUP_ICON = 14
    LANG_NEUTRAL  = 0
    HIGH_BIT      = 0x80000000

    nf = len(rt_icon)
    ng = len(rt_group)

    def dir_sz(n_id: int) -> int:
        return 16 + n_id * 8

    # Calculate all directory offsets (all relative to start of rsrc blob)
    r3   = dir_sz(2);          r3s  = dir_sz(nf)
    fn   = r3 + r3s;           fns  = dir_sz(1)
    r14  = fn + nf * fns;      r14s = dir_sz(ng)
    gn   = r14 + r14s;         gns  = dir_sz(1)
    de   = gn + ng * gns;      des  = 16
    rd   = _align(de + (nf + ng) * des, 4)

    # Accumulate raw data, recording absolute VAs for each entry
    raw = bytearray()
    fo  = []
    go  = []

    for _, data in rt_icon:
        fo.append((rsrc_rva + rd + len(raw), len(data)))  # absolute VA
        raw += data
        pad = _align(len(raw), 4) - len(raw)
        if pad: raw += b'\x00' * pad

    for _, data in rt_group:
        go.append((rsrc_rva + rd + len(raw), len(data)))  # absolute VA
        raw += data
        pad = _align(len(raw), 4) - len(raw)
        if pad: raw += b'\x00' * pad

    buf = bytearray()

    def wdir(n_id: int, entries: list):
        # IMAGE_RESOURCE_DIRECTORY: Characteristics, TimeDateStamp, MajVer, MinVer,
        # NumberOfNamedEntries, NumberOfIdEntries  (16 bytes total)
        buf.extend(struct.pack('<IIHHHH', 0, 0, 0, 0, 0, n_id))
        for eid, child, is_dir in entries:
            buf.extend(struct.pack('<II', eid, child | (HIGH_BIT if is_dir else 0)))

    wdir(2, [(RT_ICON, r3, True), (RT_GROUP_ICON, r14, True)])
    wdir(nf, [(fid, fn + i * fns, True) for i, (fid, _) in enumerate(rt_icon)])
    for i in range(nf):
        wdir(1, [(LANG_NEUTRAL, de + i * des, False)])
    wdir(ng, [(gid, gn + i * gns, True) for i, (gid, _) in enumerate(rt_group)])
    for i in range(ng):
        wdir(1, [(LANG_NEUTRAL, de + (nf + i) * des, False)])

    while len(buf) < de: buf.append(0)
    for rva, sz in fo: buf.extend(struct.pack('<IIII', rva, sz, 0, 0))
    for rva, sz in go: buf.extend(struct.pack('<IIII', rva, sz, 0, 0))
    while len(buf) < rd: buf.append(0)
    buf.extend(raw)
    return bytes(buf)


def _build_pe(ico_payloads: list) -> bytes:
    """Minimal resource-only PE32+ DLL — no C compiler required."""
    FILE_ALIGN = 0x200
    SEC_ALIGN  = 0x1000
    IMAGE_BASE = 0x10000000

    # Parse each .ico into frames
    all_frames  = []
    icon_groups = []
    for ico_bytes in ico_payloads:
        count = struct.unpack_from('<H', ico_bytes, 4)[0]
        grp   = []
        for i in range(count):
            base                     = 6 + i * 16
            bw,bh,_,_,_,bc,size,off = struct.unpack_from('<BBBBHHIi', ico_bytes, base)
            w = 256 if bw == 0 else bw
            h = 256 if bh == 0 else bh
            bc = bc or 32
            all_frames.append((w, h, bc, ico_bytes[off: off + size]))
            grp.append(len(all_frames))
        icon_groups.append(grp)

    rt_icon  = [(i + 1, data) for i, (_, _, _, data) in enumerate(all_frames)]
    rt_group = []
    for gid, grp in enumerate(icon_groups, 1):
        hdr  = struct.pack('<HHH', 0, 1, len(grp))
        ents = b''
        for fi in grp:
            w, h, bc, data = all_frames[fi - 1]
            bw = 0 if w >= 256 else w
            bh = 0 if h >= 256 else h
            # GRPICONDIRENTRY: BBBB HH I H = 14 bytes (nID is WORD, not DWORD)
            ents += struct.pack('<BBBBHHIH', bw, bh, 0, 0, 1, bc, len(data), fi)
        rt_group.append((gid, hdr + ents))

    NUM_SEC  = 1
    OPT_SZ   = 112 + 16 * 8    # PE32+ optional header + 16 data directories

    hdr_sz    = _align(0x40 + 4 + 20 + OPT_SZ + NUM_SEC * 40, FILE_ALIGN)
    rsrc_rva  = _align(hdr_sz, SEC_ALIGN)

    rsrc     = _build_rsrc(rt_icon, rt_group, rsrc_rva)
    rsrc_pad = rsrc + b'\x00' * (_align(len(rsrc), FILE_ALIGN) - len(rsrc))

    rsrc_virt = _align(len(rsrc), SEC_ALIGN)
    img_sz    = rsrc_rva + rsrc_virt

    # DOS stub — e_lfanew at byte 0x3C must point to the PE signature
    dos = bytearray(0x40)
    dos[0] = 0x4D; dos[1] = 0x5A           # MZ
    struct.pack_into('<I', dos, 0x3C, 0x40) # e_lfanew = 0x40

    # COFF file header
    file_hdr = struct.pack('<HHIIIHH',
        0x8664, NUM_SEC, 0, 0, 0, OPT_SZ, 0x2022)

    # PE32+ optional header — exactly 29 fields, 112 bytes
    opt_hdr = struct.pack('<HBBIIIIIQIIHHHHHHIIIIHHQQQQII',
        0x20B, 0, 0,
        0, len(rsrc_pad), 0,
        0, 0,
        IMAGE_BASE,
        SEC_ALIGN, FILE_ALIGN,
        6, 0, 0, 0, 6, 0, 0,
        img_sz, hdr_sz, 0,
        2, 0x540,
        0x100000, 0x1000,
        0x100000, 0x1000,
        0, 16,
    )
    ddirs = bytearray(16 * 8)
    struct.pack_into('<II', ddirs, 2 * 8, rsrc_rva, len(rsrc))  # .rsrc data dir
    opt_hdr += bytes(ddirs)

    # Section header for .rsrc
    sec_hdr = struct.pack('<8sIIIIIIHHI',
        b'.rsrc\x00\x00\x00',
        rsrc_virt, rsrc_rva,
        len(rsrc_pad), hdr_sz,
        0, 0, 0, 0,
        0x40000040)

    headers = bytes(dos) + b'PE\x00\x00' + file_hdr + opt_hdr + sec_hdr
    headers = headers.ljust(hdr_sz, b'\x00')
    return headers + rsrc_pad


def build_dll(ico_files: list, dll_path: str):
    """Package a list of .ico files into a single resource-only DLL."""
    payloads = []
    for path in ico_files:
        with open(path, 'rb') as f:
            payloads.append(f.read())
    pe = _build_pe(payloads)
    with open(dll_path, 'wb') as f:
        f.write(pe)
    print(f"  ✓ Saved {dll_path}  ({len(ico_files)} icons, {len(pe)//1024} KB)")


# ══════════════════════════════════════════════
# STEP 3 — APPLY ICON TO FOLDER OR SHORTCUT
# ══════════════════════════════════════════════

def _count_icons_in_dll(dll_path: str) -> int:
    """Read the DLL's resource section and count RT_GROUP_ICON entries."""
    with open(dll_path, 'rb') as f:
        data = f.read()
    pe_off  = struct.unpack_from('<I', data, 0x3C)[0]
    n_sec   = struct.unpack_from('<H', data, pe_off + 6)[0]
    opt_sz  = struct.unpack_from('<H', data, pe_off + 20)[0]
    sec_off = pe_off + 24 + opt_sz
    for i in range(n_sec):
        s    = sec_off + i * 40
        name = data[s: s + 8].rstrip(b'\x00')
        if name == b'.rsrc':
            rsrc_rva  = struct.unpack_from('<I', data, s + 12)[0]
            rsrc_raw  = struct.unpack_from('<I', data, s + 20)[0]
            rsrc_vsz  = struct.unpack_from('<I', data, s + 16)[0]
            rsrc_data = data[rsrc_raw: rsrc_raw + rsrc_vsz]
            return _count_groups(rsrc_data)
    return 0


def _count_groups(rsrc: bytes) -> int:
    RT_GROUP_ICON = 14
    HIGH_BIT      = 0x80000000
    n_id = struct.unpack_from('<H', rsrc, 14)[0]
    for i in range(n_id):
        eid, child = struct.unpack_from('<II', rsrc, 16 + i * 8)
        if eid == RT_GROUP_ICON:
            child_off = child & ~HIGH_BIT
            return struct.unpack_from('<H', rsrc, child_off + 14)[0]
    return 0


def list_icons() -> list:
    if not os.path.exists(DLL_PATH):
        print(f"No DLL found. Run:  python icon_tool.py build")
        return []
    count = _count_icons_in_dll(DLL_PATH)
    if count == 0:
        print("No icons found in DLL.")
        return []
    print(f"\nIcons stored in {DLL_PATH}:")
    for i in range(1, count + 1):
        print(f"  [{i}]")
    return list(range(1, count + 1))


def apply_icon_to_folder(folder_path: str, icon_id: int):
    """Write a desktop.ini so Windows Explorer shows the chosen icon on a folder."""
    folder_path = os.path.abspath(folder_path)
    dll_abs     = os.path.abspath(DLL_PATH)
    ini_path    = os.path.join(folder_path, "desktop.ini")

    with open(ini_path, 'w') as f:
        f.write(
            "[.ShellClassInfo]\n"
            f"IconResource={dll_abs},{icon_id - 1}\n"
            "IconIndex=0\n"
        )

    ctypes.windll.kernel32.SetFileAttributesW(ini_path,    0x22)  # Hidden | System
    ctypes.windll.kernel32.SetFileAttributesW(folder_path, 0x01)  # ReadOnly
    ctypes.windll.shell32.SHChangeNotify(
        0x00002000, 0x0005,
        ctypes.c_wchar_p(folder_path), None)

    print(f"  ✓ Applied icon [{icon_id}] to folder: {folder_path}")
    print("    Press F5 in Explorer if the icon doesn't update immediately.")


def apply_icon_to_shortcut(lnk_path: str, icon_id: int):
    """Update a .lnk shortcut to display the chosen icon from the DLL."""
    try:
        import win32com.client
    except ImportError:
        print("ERROR: pywin32 not installed. Run:  pip install pywin32")
        return
    dll_abs  = os.path.abspath(DLL_PATH)
    lnk_abs  = os.path.abspath(lnk_path)
    shell    = win32com.client.Dispatch("WScript.Shell")
    sc       = shell.CreateShortcut(lnk_abs)
    # icon_id is 1-based; DLL group index is 0-based
    sc.IconLocation = f"{dll_abs},{icon_id - 1}"
    sc.save()

    # Notify the shell to redraw this specific shortcut
    ctypes.windll.shell32.SHChangeNotify(
        0x00000080,   # SHCNE_UPDATEITEM
        0x0005,       # SHCNF_PATH
        ctypes.c_wchar_p(lnk_abs), None)

    print(f"  ✓ Applied icon [{icon_id}] to shortcut: {lnk_path}")
    print("    Right-click desktop → Refresh, or press F5 in Explorer.")


# ══════════════════════════════════════════════
# CLI COMMANDS
# ══════════════════════════════════════════════

def cmd_build():
    try:
        from PIL import Image  # noqa
    except ImportError:
        print("ERROR: Pillow not installed. Run:  pip install pillow")
        return

    os.makedirs(ICON_FOLDER, exist_ok=True)

    # Collect all supported image formats from the input folder
    EXTS = ("*.png", "*.webp", "*.jpg", "*.jpeg")
    images = []
    for ext in EXTS:
        images.extend(glob.glob(os.path.join(PNG_FOLDER, ext)))
    images = sorted(set(
        p for p in images
        if os.path.abspath(os.path.dirname(p)) != os.path.abspath(ICON_FOLDER)
    ))

    if images:
        print(f"\nConverting {len(images)} image(s) → .ico ...")
        for p in images:
            name     = os.path.splitext(os.path.basename(p))[0]
            ico_path = os.path.join(ICON_FOLDER, name + ".ico")
            png_to_ico(p, ico_path)
            print(f"  ✓ {ico_path}")
    else:
        print(f"No images found in '{os.path.abspath(PNG_FOLDER)}' — skipping conversion.")

    # Package ALL .ico files currently in the icons folder (including pre-existing ones)
    ico_files = sorted(glob.glob(os.path.join(ICON_FOLDER, "*.ico")))

    if not ico_files:
        print(f"No .ico files found in '{os.path.abspath(ICON_FOLDER)}'. Nothing to build.")
        return

    print(f"\nPackaging {len(ico_files)} icon(s) into {DLL_PATH} ...")
    build_dll(ico_files, DLL_PATH)
    print("\nAll done!  Run  python icon_tool.py list  to verify.")


def cmd_list():
    list_icons()


def cmd_apply():
    ids = list_icons()
    if not ids:
        return

    try:
        icon_id = int(input("\nEnter icon number to use: "))
    except ValueError:
        print("Invalid number.")
        return

    target = input("Paste or drag the folder / shortcut (.lnk) path here: ").strip().strip('"')

    if not target:
        print("No path entered.")
    elif target.lower().endswith(".lnk"):
        apply_icon_to_shortcut(target, icon_id)
    elif os.path.isdir(target):
        apply_icon_to_folder(target, icon_id)
    else:
        print(f"Path not found or not a folder/.lnk:  {target}")


def cmd_clearcache():
    """
    Clear only the Windows icon/thumbnail cache database.
    Your existing desktop icons will reload automatically — nothing is reset.
    Explorer restarts briefly (a few seconds) then comes back.
    """
    import subprocess

    print("\nThis will briefly restart Explorer to clear the icon cache.")
    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    print("Clearing icon cache (Explorer will restart briefly)...")

    cmds = [
        # Stop Explorer
        'taskkill /f /im explorer.exe',
        # Delete only the icon cache files — NOT your shortcuts or settings
        r'del /f /q "%localappdata%\IconCache.db"',
        r'del /f /q "%localappdata%\Microsoft\Windows\Explorer\iconcache_*.db"',
        r'del /f /q "%localappdata%\Microsoft\Windows\Explorer\thumbcache_*.db"',
        # Restart Explorer — all your icons reload from the DLL files
        'start explorer.exe',
    ]
    for cmd in cmds:
        subprocess.run(cmd, shell=True, capture_output=True)

    print("  ✓ Done. Explorer is restarting.")
    print("  Your desktop icons will all reload from their source files.")
    print("  Any icon pointing to a valid DLL will show correctly.")


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "help"
    if   cmd == "build":      cmd_build()
    elif cmd == "list":       cmd_list()
    elif cmd == "apply":      cmd_apply()
    elif cmd == "clearcache": cmd_clearcache()
    else:
        print(__doc__)
