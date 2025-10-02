# FFmpeg as used in TeamSpeak 6
This repository provides a **Conan (1.x)** recipe that builds a **shared [FFmpeg](https://www.ffmpeg.org/) 8.0** (or a selected commit) focused on **hardware-accelerated encoding/decoding** for **Windows**, **Linux**, and **macOS**.  
The default configuration mirrors the FFmpeg shared library shipped with the [TeamSpeak 6 Client](https://teamspeak.com/en/) and enables **LGPL v3** components via `--enable-version3`. More information about FFmpeg and the licensing can be found  [here](https://www.ffmpeg.org/).
The package exposes the FFmpeg libraries: `avcodec`, `avformat`, `avfilter`, `avutil`, `swscale`, `swresample`, as well as `libvpl` (Win/Linux), `libva` (Linux only) and `libvdpau` (Linux only).

> [!NOTE]
> **Client compatibility:** The [TeamSpeak 6 Client](https://teamspeak.com/en/) in a specific beta release is guaranteed to work with a FFmpeg build from this repository with the same version tag (e.g. v6.0.0-beta3). In general, the Client is compatible with **FFmpeg 7.1+** (earlier versions \< 7.1 **may** work but are not guaranteed). The versions in the `conandata.yml` represent public beta releases, however, not every beta release may contain an update of FFmpeg. So _v6.0.0-beta3_ could be valid for _v6.0.0-beta5_ as well. With each client release, a [release](/../../releases) with the exact sources will be generated for offline building. When updated, a new entry will appear in `conandata.yml` reflecting the changed sources.


## 🧩 Capabilities & Compatibility
- **Conan:** **Conan \< 2** (1.x) only. (for now)
- **Platforms:** **Windows** (native or via cross building), **Linux**, **macOS**.
- **Default output:** A **shared** library equivalent to our Client Bundle, compiled with `--enable-version3` (LGPL v3).

- **Hardware acceleration (enabled by default):**  
  - [**AMD AMF**](https://github.com/GPUOpen-LibrariesAndSDKs/AMF) (Win/Linux)
  - [**Intel QSV (oneVPL)**](https://github.com/intel/libvpl) (Win/Linux)  
  - [**NVIDIA NVENC/CUVID**](https://github.com/FFmpeg/nv-codec-headers) (Win/Linux)  
  - [**VAAPI**](https://github.com/intel/libva) (Linux)  
  - [**VDPAU**](https://gitlab.freedesktop.org/vdpau/libvdpau) (Linux)  
  - [**Vulkan**](https://github.com/KhronosGroup/Vulkan-Headers) (Win/Linux) is supported but **not** included by default.
  - **VideoToolbox** (macOS)  
  - **V4L2** (Linux)  is supported but **not** included by default.
 
- The exact versions of the mentioned dependencies can be looked up in the `conandata.yml`. It also includes the specific repository URLs that are used to fetch the third-party sources.

- **Provenance:** The recipe is **loosely based** on the Conan Center FFmpeg recipe, but **trimmed and tuned for HW-accelerated paths**. Software encoders/decoders remain in the layout for potential future private builds.

<br/>

## 🧭 Using local vs. remote sources
You have the choice of pulling in sources from the internet or using a pre-bundled source package. For that, adjust `conandata.yml` to control where the FFmpeg sources are pulled from. **Order of preference:** **Local ➜ Commit ➜ Tag** (first valid entry wins).
- Use git checkouts to clone the dependencies in the exact version that we did to build FFmpeg alongside our Client
  - **This is the default**, sources will be pulled from third party and a working internet connection is required
- Use the exact sources used by us for a specifc beta release
  - Download the `ffmpeg_bundled_source.tar.gz` from the [Releases Page](/../../releases) and the specific version you are interested in
  - Unpack anywhere and note down the path
  - Adjust the `conandata.yml`➜`local_root` of a specific version you want to build (e.g. v6.0.0-beta3) to point to the unpacked root of the `ffmpeg_bundled_source.tar.gz`
    - `amf/`, `ffmpeg/`, etc. should reside in the `local_root` directory
- Download the sources in specific versions yourself
  - Exactly like the steps above, except that your checkout/clone all the required dependencies into their respective subdirectory `amf/`, `ffmpeg/`, etc. yourself
  - Again, adjust `conandata.yml`  like before and let the `local_root` point to the parent directory

Alternatively, you can freely edit the `conandata.yml` to fit your needs, keep in mind that the priority preference is respected **Local ➜ Commit ➜ Tag**.
You can freely remove `local`, `commit` or `tag` as long as one valid entry is present. Otherwise, the build will fail.
```yaml
sources:
  "v6.0.0-beta3":
    "ffmpeg":
      "local": "./src/ffmpeg"   # takes precedence if present
      "commit": "140fd653aed8cad774f991ba083e2d01e86420c7"
      "tag": "release/8.0"
```

<br/>

## 🛠️ Prerequisites
The build is managed via Conan, thus you have to have a valid Conan environment available with tools to compile.

Requirements for all Platforms:
 - [Python 3](https://www.python.org/downloads/)
   - e.g. (linux)
```bash
apt install python3 pip
```
 - Conan <2.0
```bash
pip install "conan<2.0"
``` 
 - Some compiler of choice (e.g. msvc, clang, gcc)
   - e.g. (linux)
```
apt install gcc
``` 
Optional, if you use remote sources:
 - [Git](https://git-scm.com/downloads) or e.g.
```bash
apt install git
```


<br/>

### <a id="windows-msys" />🪟 Windows (native builds)
 - [MSYS2](https://www.msys2.org/)
 - [Visual Studio Build Tools (and Visual Studio CMD)](https://visualstudio.microsoft.com/de/downloads/)

Install **MSYS2** system-wide (e.g., `C:\msys64`). We **intentionally** use the **system MSYS2** instead of the Conan Center package due to incompatibilities.

**Add to your Conan Profile `[conf]` (required):**
```ini
[conf]
tools.microsoft.bash:path=C:\\msys64\\usr\\bin\\bash.exe
tools.microsoft.bash:subsystem=msys2
```

> [!NOTE]
> `pkg-config` and `make` are installed automatically via **pacman** unless you override tool locations in the profile.

<br/>

### 🐧 Linux

To build **libvpl**, **libva**, and **libvdpau** from source:

```bash
apt install autoconf autotools-dev cmake pkg-config meson libdrm-dev automake libtool libx11-dev
```

For **V4L2** support:

```
apt install libv4l-dev libv4l-0
```

> [!NOTE]
> When cross-building to Windows, the recipe requests a **mingw-w64** toolchain via the system package manager.

<br/>

### 🍎 macOS

Install Xcode CLI tools (or Xcode).


<br/>

## 🏗️ Build: quick start

### 1) Configure & Select Conan Profile
- Use your existing profiles or create a new profile, which is saved under e.g. `~/.conan/profiles/mynewprofile`
```bash
conan profile new mynewprofile --detect
```
- Take the example profiles from below and adjust as needed for your local environment
- More info in the [Conan Documentation](https://docs.conan.io/1/reference/profiles.html#profiles)

> [!WARNING]
> On Windows native builds, the [MSYS2 conf section](#windows-msys) is strictly required!


|Linux|Windows|Mac|
|---|---|---|
|<pre># Example only<br>[settings]<br>arch=x86_64<br>os=Linux<br>compiler=clang<br>compiler.version=20<br>compiler.libcxx=libc++<br>compiler.cppstd=20<br>build_type=Release<br>compiler.runtime=static<br>[buildenv]<br>LINK=clang++<br></pre>|<pre># Example only<br>[settings]<br>arch=x86_64<br>os=Windows<br>compiler=Visual Studio<br>compiler.version=17<br>compiler.cppstd=20<br>build_type=Release<br>compiler.runtime=MT<br>[conf]<br>tools.microsoft.bash:path=C:\\msys64\\usr\\bin\\bash.exe<br>tools.microsoft.bash:subsystem=msys2</pre>|<pre># Example only<br>[settings]<br>arch=armv8<br>os=Macos<br>os.version=11.0<br>compiler=apple-clang<br>compiler.version=15<br>compiler.cppstd=20<br>compiler.libcxx=libc++<br>build_type=Release</pre>|

### 2) Create the package
Use `ffmpeg/<version>@local/local`, e.g. `ffmpeg/v6.0.0-beta3@local/local`, for specific version selection, otherwise stick to `latest`.
```bash
conan create . ffmpeg/latest@local/local -pr=mynewprofile --build missing
```

### 3) Consume the package
- When `conan create` succeeds, it prints the package folder, where the built libraries are placed, e.g.:
```txt
ffmpeg/latest@local/local: Package folder /root/.conan/data/ffmpeg/latest/local/local/package/3dc97203f0827b3ec676dacf1cfc370fdd9d08de
```
- Link against the usual FFmpeg components in your application (or use with the [TeamSpeak 6 Client](https://teamspeak.com/en/)).
  - To use in the [TeamSpeak 6 Client](https://teamspeak.com/en/), copy the contents of `package/.../lib/` (and `package/.../bin/` on Win) to your TeamSpeak installation path. Backup existing libraries if anything goes wrong.
- For use in other apps, headers are available under the package’s `package/.../include` directory; link via flags like `-lavcodec` as needed.
- We also ship **AMF/NVENC/VPL headers** so you can use low-level APIs if required.
- You can also consume the different components as a Conan-Consumer, see the package_info for the concrete available components (e.g. `avcodec`, `swscale`, `AMF`, etc.)

> [!NOTE]
> On **Windows**, both **Debug** and **Release** **libvpl**/**libvpld** static libraries are packaged so consumers can link a configuration that matches their build type.

> [!WARNING]
> **Release binaries are intentionally unstripped** and include debug symbols. Stripping remains a **consumer decision**. 🧪

---

## 📦 Options

| Option              | Default | Notes                                                                                                           |
| ------------------- | :-----: | --------------------------------------------------------------------------------------------------------------- |
| `with_amf`          |   True  | AMD AMF headers pulled automatically; **auto-disabled on macOS**.                                               |
| `with_qsv`          |   True  | Intel QSV via oneVPL; builds & packages **Debug + Release** `libvpl` on Windows; **auto-disabled on macOS**.    |
| `with_nvenc`        |   True  | Enables NVENC/CUVID and ffnvcodec headers; **requires** `with_vdpau=True` on Linux; **auto-disabled on macOS**. |
| `with_vaapi`        |   True  | Linux/FreeBSD only; VAAPI runtime `.so` files are copied to assist systems without preinstalled libva.          |
| `with_vdpau`        |   True  | Linux/FreeBSD only; `libvdpau` is built from source (meson).                                                    |
| `with_v4l`          |  False  | Linux only; enables `libv4l2` / `v4l2m2m` (requires `libv4l-dev`, `libv4l-0`).                                  |
| `with_libdrm`       |  True   | Linux only; enables `libdrm`                                                                                    |
| `with_videotoolbox` |   True  | Apple targets only; default HW path on macOS.                                                                   |
| `with_appkit`       |   True  | Apple targets only; toggles `--enable-appkit` when configuring FFmpeg.                                          |
| `with_avfoundation` |   True  | Apple targets only; toggles `--enable-avfoundation` when configuring FFmpeg.                                    |
| `with_coreimage`    |   True  | Apple targets only; toggles `--enable-coreimage` when configuring FFmpeg.                                       |
| `with_audiotoolbox` |   False | Apple targets only; toggles `--enable-audiotoolbox` when configuring FFmpeg. (unused for hw accelerated video coding) |
| `with_vulkan`       |  False  | Supported; downloads Vulkan headers when enabled.                                                               |
| `with_mediacodec`   |   False | Android targets only; toggles `--enable-mediacodec` when configuring FFmpeg. Currently unsued                   |
| `with_h264`         |   True  | Enables H.264 parsers and HW bindings.                                                                          |
| `with_asm`          |   True  | Assembler support; NASM required (not used on Apple armv8).                                                     |
| `fPIC`              |   True  | Effective on non-Windows/static builds; removed automatically for shared builds.                                |
| `with_strip`        |  False  | Keep symbols; stripping is left to the consumer.                                                                |


## 🧯 Troubleshooting

* **MSYS2 not detected on Windows:** Ensure your profile contains the required `[conf]` entries pointing to your system MSYS2.
* **NVENC on Linux:** Set `-o ffmpeg:with_vdpau=True`; the recipe enforces this dependency.
* **Missing Linux build tools:** Install the packages listed in **Linux** prerequisites above.
* **Linking QSV on Windows:** Link against the **libvpl** variant that matches your consumer build type (**Debug/Release**).


## License
The files in this repository (not the release assets) are licensed under MIT, which can be found in the LICENSE file.
All components used in the build are licensed under their own terms that can be reviewed in the source package of releases in the specific sub folder of the respective component.
Thus, the resulting binaries/libraries are each licensed under the terms of the originating source. For example, without any changes, the resulting FFmpeg libraries are licensed under LGPL v3.0.

