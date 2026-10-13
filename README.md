# FFmpeg as used in TeamSpeak 6
This repository provides a **Conan 2** recipe that builds a **shared FFmpeg 8.x** (or a selected commit) focused on **hardware-accelerated encoding/decoding** for **Windows**, **Linux**, and **macOS**.  
The default configuration mirrors the FFmpeg shared library shipped with the [TeamSpeak 6 Client](https://teamspeak.com/en/) and enables **LGPL v3** components via `--enable-version3`.  
The package exposes the FFmpeg libraries `avcodec`, `avformat`, `avfilter`, `avutil`, `swscale`, `swresample` and a header-only `headers` component. It also ships the headers (and, where applicable, static libraries/runtime libraries) of `libvpl` (Win/Linux), `libva` (Linux only) and `libvdpau` (Linux only).

> [!NOTE]
> **Client compatibility:** The [TeamSpeak 6 Client](https://teamspeak.com/en/) in a specific beta release is guaranteed to work with a FFmpeg build from this repository with the same version tag (e.g. v6.0.0-beta3). In general, the Client is compatible with **FFmpeg 7.1+** (earlier versions \< 7.1 **may** work but are not guaranteed). The versions in the `conandata.yml` represent public beta releases, however, not every beta release may contain an update of FFmpeg. So _v6.0.0-beta3_ could be valid for _v6.0.0-beta5_ as well. When updated, a new entry will appear in `conandata.yml` reflecting the changed sources.
>
> FFmpeg version per entry: `v6.0.0-beta3` → 8.0 (`n8.0`); `v6.0.0-beta4`, `v6.0.0-beta5` and `latest` → 8.1 (`n8.1`).


## 🧩 Capabilities & Compatibility
- **Conan:** **Conan 2.x** only (`conan >= 2, < 3`; verified with 2.30). Conan 1.x is **not** supported by this recipe anymore.
- **Platforms:** **Windows** (native or cross-building from Linux via mingw-w64), **Linux**, **macOS**.
- **Default output:** A **shared** library equivalent to our Client Bundle, compiled with `--enable-version3` (LGPL v3).
- **Codecs:** AV1, VP8, VP9 and (default, `with_h264`) H.264 — hardware encoders/decoders and parsers only; `--disable-everything` is the baseline.

- **Hardware acceleration (enabled by default):**  
  - [**AMD AMF**](https://github.com/GPUOpen-LibrariesAndSDKs/AMF) (Win/Linux)
  - [**Intel QSV (oneVPL)**](https://github.com/intel/libvpl) (Win/Linux)  
  - [**NVIDIA NVENC/CUVID**](https://github.com/FFmpeg/nv-codec-headers) (Win/Linux)  
  - [**VAAPI**](https://github.com/intel/libva) (Linux)  
  - [**VDPAU**](https://gitlab.freedesktop.org/vdpau/libvdpau) (Linux)  
  - **VideoToolbox** (macOS)  
  - [**Vulkan**](https://github.com/KhronosGroup/Vulkan-Headers) (Linux) is supported but **not** included by default.
  - **V4L2** (Linux) is supported but **not** included by default.

- The exact versions of the mentioned dependencies can be looked up in the `conandata.yml`. It also includes the specific repository URLs that are used to fetch the third-party sources.

- **Provenance:** The recipe is **loosely based** on the Conan Center FFmpeg recipe, but **trimmed and tuned for HW-accelerated paths**. Software encoders/decoders remain in the layout for potential future private builds.

> [!NOTE]
> On macOS targets, **AMF/QSV/NVENC are automatically disabled** (the options do not exist there). **VideoToolbox** is the default hardware path on macOS. ⚠️

> [!NOTE]
> **Cross-building** (e.g. Linux ➜ Windows with mingw-w64, x86_64 only): the Linux-only options (`with_vaapi`, `with_vdpau`, `with_vulkan`, `with_libdrm`, `with_v4l`) **and `with_nvenc`** are removed. AMF and QSV remain available.
>
> The recipe currently treats **any Windows host profile** like a native MSYS2 build: the `tools.microsoft.bash:path` / `tools.microsoft.bash:subsystem=msys2` `[conf]` entries must be set (the path's grandparent directory must exist), and `tools.gnu:pkg_config=<path to pkg-config>` must be set, otherwise the recipe tries to run `pacman`.


## 🧭 Using local vs. remote sources
You have the choice of pulling in sources from the internet or using a pre-bundled source package. For that, adjust `conandata.yml` to control where the FFmpeg sources are pulled from. **Order of preference:** **Local ➜ Commit ➜ Tag** (first valid entry wins; a `local` entry whose directory does not exist is skipped and the next one is tried).

The key in `conandata.yml` → `sources` **must match the package version** you pass to `conan create --version=...` (`latest`, `v6.0.0-beta3`, `v6.0.0-beta4`, `v6.0.0-beta5`). The recipe has no fixed version, so a missing/unknown version fails the build.

- Use git checkouts to clone the dependencies in the exact version that we did to build FFmpeg alongside our Client
  - **This is the default**, sources will be pulled from third party and a working internet connection (and `git`) is required
- Use the exact sources used by us for a specific beta release
  - Download the `ffmpeg_bundled_source.tar.gz` from the [Releases Page](/../../releases) and the specific version you are interested in
  - Unpack anywhere and note down the **absolute** path
  - Adjust the `conandata.yml`➜`local_root` of the specific version you want to build (e.g. v6.0.0-beta3) to point to the unpacked root of the `ffmpeg_bundled_source.tar.gz`
    - `amf/`, `ffmpeg/`, etc. should reside in the `local_root` directory
- Download the sources in specific versions yourself
  - Exactly like the steps above, except that you checkout/clone all the required dependencies into their respective subdirectory `amf/`, `ffmpeg/`, etc. yourself
  - Again, adjust `conandata.yml` like before and let the `local_root` point to the parent directory

> [!IMPORTANT]
> Use an **absolute** `local_root`. The recipe resolves it while Conan runs `source()` inside its cache folder, so relative paths (including the default `.`) do **not** point into your checkout. `conandata.yml` is exported with the recipe, so edit it **before** running `conan create`.

Alternatively, you can freely edit the `conandata.yml` to fit your needs, keep in mind that the priority preference is respected **Local ➜ Commit ➜ Tag**.
You can freely remove `local`, `commit` or `tag` as long as one valid entry is present. Otherwise, the build will fail.
```yaml
sources:
  "v6.0.0-beta5":
    "local_root": "/abs/path/to/ffmpeg_bundled_source"   # parent of ffmpeg/, amf/, ...
    "ffmpeg":
      "local": "ffmpeg"         # takes precedence if <local_root>/ffmpeg exists
      "commit": "140fd653aed8cad774f991ba083e2d01e86420c7"
      "tag": "n8.1"
```

## 🛠️ Prerequisites
The build is managed via Conan, thus you have to have a valid Conan 2 environment available with tools to compile. That means:
 - Python 3
 - Conan 2.x (`pip install "conan>=2,<3"`)
 - Git
 - Some compiler of choice (e.g. msvc, clang, gcc)

are a hard requirement for all platforms. `nasm` (and `libdrm` on Linux) are pulled in automatically as Conan build requirements from [Conan Center](https://conan.io/center) (default remote); pass `--build=missing` if no binaries are available for your platform.

### 🪟 Windows (native builds)
 - MSYS2
 - Visual Studio Build Tools (C++ workload)

Install **MSYS2** system-wide (e.g., `C:\msys64`). We **intentionally** use the **system MSYS2** instead of the Conan Center package due to incompatibilities.

**Add to your Conan Profile `[conf]` (required — the recipe aborts with an error if either is missing or if the subsystem is not `msys2`; this also applies to Linux ➜ Windows cross-builds):**
```ini
[conf]
tools.microsoft.bash:path=C:\\msys64\\usr\\bin\\bash.exe
tools.microsoft.bash:subsystem=msys2
```

> [!NOTE]
> `make` and `pkg-config` are installed automatically via **pacman** (`pacman -S --noconfirm pkg-config make`). To use your own `pkg-config` instead, set `tools.gnu:pkg_config=<path>` in the profile `[conf]`.

### 🐧 Linux

To build **libvpl**, **libva**, and **libvdpau** from source:

```
autoconf autotools-dev cmake pkg-config meson libdrm-dev automake libtool make
```

For **V4L2** support:

```
libv4l-dev libv4l-0
```

> [!NOTE]
> The recipe does **not** install these packages itself (the corresponding `apt` calls are disabled); install them upfront.

> [!NOTE]
> When cross-building to Windows, the recipe requests a **mingw-w64** toolchain via the system package manager. Conan 2 only does this if you allow it explicitly:
> `-c tools.system.package_manager:mode=install -c tools.system.package_manager:sudo=True`
> (otherwise install `mingw-w64 gcc-mingw-w64 g++-mingw-w64` etc. manually).

### 🍎 macOS

Install Xcode CLI tools (or Xcode).


## 🏗️ Build: quick start

### 1) Configure & Select Conan Profile
- Create a new profile, or edit an existing one: `conan profile detect --name mynewprofile` (add `--force` to overwrite), which is saved under `~/.conan2/profiles/mynewprofile` (`%USERPROFILE%\.conan2\profiles\` on Windows; override the location with `CONAN_HOME`).
- Take the example profiles from below and adjust as needed for your local environment
- More info in the [Conan Documentation](https://docs.conan.io/2/reference/config_files/profiles.html)


|Linux|Windows|Mac|
|---|---|---|
|<pre># Example only<br>[settings]<br>arch=x86_64<br>os=Linux<br>compiler=clang<br>compiler.version=20<br>compiler.libcxx=libc++<br>compiler.cppstd=20<br>build_type=Release<br>[buildenv]<br>LINK=clang++<br></pre>|<pre># Example only<br>[settings]<br>arch=x86_64<br>os=Windows<br>compiler=msvc<br>compiler.version=193<br>compiler.cppstd=20<br>compiler.runtime=static<br>compiler.runtime_type=Release<br>build_type=Release<br>[conf]<br>tools.microsoft.bash:path=C:\\msys64\\usr\\bin\\bash.exe<br>tools.microsoft.bash:subsystem=msys2</pre>|<pre># Example only<br>[settings]<br>arch=armv8<br>os=Macos<br>os.version=11.0<br>compiler=apple-clang<br>compiler.version=15<br>compiler.cppstd=20<br>compiler.libcxx=libc++<br>build_type=Release</pre>|

> [!NOTE]
> Conan 2 differences vs. Conan 1 profiles: `compiler=msvc` (+ `compiler.version=193` for VS 2022) replaces `Visual Studio`/`17`, and `compiler.runtime=static` + `compiler.runtime_type` replace `compiler.runtime=MT`/`MTd`. `compiler.runtime` is not a valid setting for clang on Linux.

### 2) Create the package

```bash
conan create . --name=ffmpeg --version=latest -pr:h=mynewprofile -pr:b=mynewprofile --build=missing
```

- `--version` selects the entry in `conandata.yml` (e.g. `--version=v6.0.0-beta5`).
- `-pr:h` is the *host* profile (target platform), `-pr:b` the *build* profile (machine running the build). `-pr=<name>` sets both. They differ when cross-building.
- `--user`/`--channel` are optional in Conan 2 (e.g. `--user=local --channel=local` ➜ `ffmpeg/latest@local/local`).
- Options: `-o ffmpeg/*:with_vulkan=True` (Conan 1's `-o ffmpeg:with_vulkan=True` form is not valid anymore).

Example: debug symbols for a Release build:
```bash
conan create . --name=ffmpeg --version=latest -pr=mynewprofile -o ffmpeg/*:with_symbols=True
```

### 3) Consume the package

- Link against the usual FFmpeg components in your application (or use with the [TeamSpeak 6 Client](https://teamspeak.com/en/)).
  - To use in the [TeamSpeak 6 Client](https://teamspeak.com/en/), copy the contents of the package's `lib/` (and `bin/` on Win) folder to your TeamSpeak installation path. Backup existing libraries if anything goes wrong.
  - Find the package folder:
    ```bash
    conan list "ffmpeg/latest:*"                         # shows the <package_id>
    conan cache path ffmpeg/latest:<package_id>          # package folder
    ```
    or copy it out directly: `conan install --requires=ffmpeg/latest -pr=mynewprofile --deployer=direct_deploy --deployer-folder=out`
    (Conan 2 cache folders are hashed, e.g. `~/.conan2/p/ffmpe<hash>/p/`).
- In your own Conan project: `self.requires("ffmpeg/latest")` and use `CMakeDeps` (`find_package(ffmpeg)` ➜ `ffmpeg::avcodec`, `ffmpeg::avformat`, …) or `PkgConfigDeps` (`libavcodec`, …). The header-only component `ffmpeg::headers` (`libffmpeg_headers`) exposes include dirs only, e.g. for consumers that `dlopen` FFmpeg at runtime.
- Headers are available under the package's `include/` directory; link via flags like `-lavcodec` as needed.
- We also ship **AMF/NVENC/VPL headers** (`include/AMF`, `include/ffnvcodec`, `include/vpl`) so you can use low-level APIs if required. On Linux with VAAPI enabled, the libva headers (`include/va`) are shipped as well. The `libvpl` static libraries are packaged in `lib/` but are **not** part of the Conan component libs; link them manually if needed.
- Licenses of FFmpeg are packaged under `licenses/`.

> [!NOTE]
> The produced `.lib`/`.dll`/`.dylib`/`.so` live under the package's `lib/` and `bin/` (Windows DLLs and PDBs) directories.
> On macOS the dylibs use `@rpath` install names, so consumers resolve them via their own `LC_RPATH`/`@loader_path`.

> [!NOTE]
> On **Windows**, both **Debug** and **Release** **libvpl**/**libvpld** static libraries are packaged so consumers can link a configuration that matches their build type.

> [!NOTE]
> The `package_id` ignores `build_type` and `compiler`: Debug and Release builds (and different compilers) of the same version/options/OS/arch map to the **same** package. A later `conan create` replaces the earlier one, so build Debug and Release into separate user/channel pairs (or Conan homes) if you need both.

> [!WARNING]
> **Binaries are not stripped by default** (`with_strip=False`). Stripping remains a **consumer decision**. For distributable symbols use `with_symbols=True`: PDBs next to the DLLs on Windows (MSVC), dSYM bundles in `lib/` on macOS (the packaged dylibs are then stripped with `strip -S -x`; exported symbols are kept), `--enable-debug` on Linux. Do **not** combine `with_symbols=True` with `with_strip=True` (the options are mutually exclusive by design; the recipe does not currently reject the combination). 🧪

---

## 📦 Options

Options marked with a platform only exist on that platform; they are removed otherwise (and in cross-builds, see above).

| Option              | Default | Notes                                                                                                                                       |
| ------------------- | :-----: | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `with_amf`          |   True  | AMD AMF headers pulled automatically; **not available on macOS**.                                                                           |
| `with_qsv`          |   True  | Intel QSV via oneVPL; builds & packages **Debug + Release** `libvpl` on Windows; **not available on macOS**.                                |
| `with_nvenc`        |   True  | Enables NVENC/CUVID and ffnvcodec headers; **needs** `with_vdpau=True` on Linux (NVDEC hw decoding); **not available on macOS and in cross-builds**. |
| `with_vaapi`        |   True  | Linux/FreeBSD (native) only; libva is built from source (autotools); runtime `.so` files and `va` headers are copied to assist systems without preinstalled libva. |
| `with_vdpau`        |   True  | Linux/FreeBSD (native) only; `libvdpau` is built from source (meson).                                                                       |
| `with_libdrm`       |   True  | Linux/FreeBSD (native) only; `--enable-libdrm`, `libdrm` is pulled as Conan build requirement.                                              |
| `with_v4l`          |  False  | Linux/FreeBSD (native) only; enables `libv4l2` / `v4l2m2m` (requires `libv4l-dev`, `libv4l-0`).                                             |
| `with_vulkan`       |  False  | Linux/FreeBSD (native) only; downloads Vulkan headers when enabled.                                                                         |
| `with_videotoolbox` |   True  | Apple targets only; default HW path on macOS.                                                                                               |
| `with_appkit`       |   True  | macOS only; `--enable-appkit`.                                                                                                              |
| `with_avfoundation` |   True  | Apple targets only; `--enable-avfoundation`.                                                                                                |
| `with_coreimage`    |   True  | Apple targets only; `--enable-coreimage`.                                                                                                   |
| `with_audiotoolbox` |  False  | Apple targets only; `--enable-audiotoolbox`.                                                                                                |
| `with_h264`         |   True  | Enables H.264 parsers and HW bindings.                                                                                                      |
| `with_asm`          |   True  | Assembler support; NASM (Conan build requirement) required; not available on Apple armv8.                                                   |
| `fPIC`              |   True  | Position independent code (`--enable-pic`); not available on Windows.                                                                       |
| `with_strip`        |  False  | `--enable-stripping`; default keeps symbols, stripping is left to the consumer. Mutually exclusive with `with_symbols`.                     |
| `with_symbols`      |  False  | Keep debug info in Release builds: PDBs (Windows/MSVC), dSYMs (macOS), `--enable-debug` (Linux). Mutually exclusive with `with_strip`.       |

Usage: `-o ffmpeg/*:<option>=<value>`, e.g. `-o ffmpeg/*:with_h264=False`.


## 🧯 Troubleshooting

* **MSYS2 not detected on Windows:** Ensure your profile contains the required `[conf]` entries (`tools.microsoft.bash:path`, `tools.microsoft.bash:subsystem=msys2`) pointing to your system MSYS2.
* **NVENC on Linux:** Keep `-o ffmpeg/*:with_vdpau=True` (default) whenever `with_nvenc` is enabled; NVDEC hw decoding depends on it. The recipe does not currently stop you from disabling it.
* **`with_symbols` / `with_strip`:** Enable only one of them; the recipe does not currently reject both.
* **Cross-building to Windows fails in `generate()`:** Set the MSYS2 `[conf]` entries (see above) and `tools.gnu:pkg_config`.
* **Unknown/missing version in `conandata.yml`:** `--version` must be one of the keys under `sources:` (`latest`, `v6.0.0-beta3`, …).
* **Local sources ignored:** `local_root` must be absolute and the component sub folders (`ffmpeg/`, `amf/`, …) must exist there; otherwise the recipe silently falls back to commit/tag (see build log: `Skipping local version ...`).
* **Missing Linux build tools:** Install the packages listed in **Linux** prerequisites above.
* **Cross-building to Windows can't install mingw-w64:** Pass `-c tools.system.package_manager:mode=install -c tools.system.package_manager:sudo=True` or install the packages manually.beta5-rc5
* **Option syntax errors (`-o ffmpeg:...`):** Use the Conan 2 pattern form `-o ffmpeg/*:...`.
* **Linking QSV on Windows:** Link against the **libvpl** variant that matches your consumer build type (**Debug/Release**).


## License
The files in this repository (not the release assets) are licensed under MIT, which can be found in the LICENSE file.
All components used in the build are licensed under their own terms that can be reviewed in the source package of releases in the specific sub folder of the respective component.
Thus, the resulting binaries/libraries are each licensed under the terms of the originating source. For example, without any changes, the resulting FFmpeg libraries are licensed under LGPL v3.0.
