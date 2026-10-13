import shutil
import subprocess
import traceback

from conan.tools.cmake import CMakeToolchain, CMake
from conan.tools.env import VirtualBuildEnv, Environment, VirtualRunEnv
from conan.tools.env.environment import _EnvVarPlaceHolder, _EnvValue
from conan.tools.microsoft import is_msvc, check_min_vs
from conan.tools.scm import Git, Version
from conan.tools.apple import is_apple_os
from conan.internal.subsystems import subsystem_path
from conan.tools.microsoft import unix_path
from conan.tools.system.package_manager import Apt, PacMan
from conan.errors import ConanException
from conan.tools.build import cross_building
from conan.tools.apple import fix_apple_shared_install_name

from conan import ConanFile
from conan.tools.gnu import AutotoolsToolchain, AutotoolsDeps, Autotools, PkgConfigDeps
from conan.tools.files.symlinks import absolute_to_relative_symlinks
from conan.tools.files import copy, chdir

import os
from pathlib import Path
import re

def _get_str_safe(self, placeholder, subsystem, pathsep, root_path=None, script_path=None):
    """
    :param subsystem:
    :param placeholder: a OS dependant string pattern of the previous env-var value like
    $PATH, %PATH%, et
    :param pathsep: The path separator, typically ; or :
    :return: a string representation of the env-var value, including the $NAME-like placeholder
    """
    values = []
    for v in self._values:
        if v is _EnvVarPlaceHolder:
            if placeholder:
                values.append(placeholder.format(name=self._name))
        else:
            if v is None:
                continue
            if self._path:
                v = subsystem_path(subsystem, v)
                if root_path is not None:
                    if v.startswith(root_path):
                        v = v.replace(root_path, script_path, 1)
                    elif os.sep == "\\":
                        r = root_path.replace("\\", "/")
                        if v.startswith(r):
                            v = v.replace(r, script_path.replace("\\", "/"))
            if v is not None:
                values.append(v)
    if self._path:
        return pathsep.join(values)

    return self._sep.join(values)

_EnvValue.get_str = _get_str_safe

from enum import Enum
class DependenyComponent(Enum):
    FFMPEG = 'ffmpeg'
    AMF = 'amf'
    NV = 'nvcodecheaders'
    VK = 'vulkan'
    LIBVPL = 'libvpl'
    LIBVA = 'libva'
    LIBVDPAU = 'libvdpau'

class ffmpeg(ConanFile):
    name = 'ffmpeg'
    license = 'LGPL-3.0-or-later'
    url = 'https://github.com/teamspeak/ffmpeg'
    description = 'FFmpeg (LGPL v3 build with HW-accelerated en/decoding only)'
    homepage = 'https://github.com/teamspeak/ffmpeg'
    settings = 'os', 'arch', 'compiler', 'build_type'
    package_type = 'shared-library'
    exports_sources = 'patches/*'
    topics = topics = ('ffmpeg', 'multimedia', 'video', 'audio', 'hwaccel', 'vaapi', 'nvdec', 'qsv', 'vdpau', 'amf')
    win_bash = True
    options = {
        'fPIC': [True, False],

        'with_libdrm': [True, False],
        'with_amf': [True, False],
        'with_qsv': [True, False],
        "with_vulkan": [True, False],
        'with_nvenc': [True, False],
        'with_vaapi': [True, False],
        'with_vdpau': [True, False],
        'with_v4l': [True, False],
        
        "with_h264": [True, False],

        "with_asm": [True, False],

        "with_appkit": [True, False],
        "with_avfoundation": [True, False],
        "with_coreimage": [True, False],
        "with_audiotoolbox": [True, False],
        "with_videotoolbox": [True, False],
        "with_mediacodec": [True, False],

        "with_strip":  [True, False],
        "with_symbols": [True, False],

    }
    default_options = {
        "fPIC": True,
        'with_amf': True,
        'with_qsv': True,
        'with_libdrm': True,
        "with_vulkan": False,
        'with_nvenc': True,
        'with_vaapi': True,
        'with_vdpau': True,
        'with_v4l': False,

        'with_h264': True,

        'with_asm': True,

        # macos
        "with_appkit": True,
        "with_avfoundation": True,
        "with_coreimage": True,
        "with_audiotoolbox": False,
        "with_videotoolbox": True,

        # android
        "with_mediacodec": False,

        "with_strip": False,
        "with_symbols": False,
    }


    CHECKOUT_PATH_FFMPEG = 'dt'
    CHECKOUT_PATH_LIBVPL = 'libvpl'
    CHECKOUT_PATH_LIBVA = 'libva'
    CHECKOUT_PATH_LIBVDPAU = 'libvdpau'
    BUILD_PATH = 'build'

    DEPS_ROOT = 'deps_root' # source.folder / deps_root
    PKG_CONFIG_SUB_PATH = 'lib/pkgconfig' # source.folder / deps_root / lib / pkgconfig


    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        if self.settings.os not in ["Linux", "FreeBSD"] or cross_building(self):
            del self.options.with_vaapi
            del self.options.with_vdpau
            del self.options.with_vulkan
            del self.options.with_libdrm
            del self.options.with_v4l
            # TODO: VAAPI/VDPAU are disabled during cross-compilation because this recipe builds
            # libva and libvdpau from source (see _setup_vaapi() and _setup_vdpau()), but those
            # build methods don't configure cross-compilation toolchains (autogen.sh/meson have no
            # --host/--target flags set). To enable cross-compilation support, would need to:
            # 1. Pass cross-compilation toolchain to autotools/meson
            # 2. Set up target sysroots and pkg-config paths
            # 3. Configure host vs target architecture detection properly
            if cross_building(self):
                # nvenc requires vdpau for nvdec hw accel decoding, so disable it too when cross-compiling
                del self.options.with_nvenc
        if self.settings.os != "Macos":
            del self.options.with_appkit
        if self.settings.os not in ["Macos", "iOS", "tvOS"]:
            del self.options.with_coreimage
            del self.options.with_audiotoolbox
            del self.options.with_videotoolbox
        if not is_apple_os(self):
            del self.options.with_avfoundation
        else:
            del self.options.with_qsv
            del self.options.with_amf
            self.options.rm_safe("with_nvenc")
            if str(self.settings.arch).startswith("armv8"):
                del self.options.with_asm
        if not self.settings.os == "Android":
            del self.options.with_mediacodec
        if self.options.get_safe('shared'):
            self.options.rm_safe("fPIC")
        if self.settings.os in ["Linux", "FreeBSD"] and self.options.get_safe('with_nvenc') and not self.options.get_safe('with_vdpau'):
            raise ConanException("option 'with_nvenc' needs 'with_vdpau' to be turned on (for nvdec hw accel decoding)")

        if self.options.get_safe("with_symbols", False) and self.options.get_safe("with_strip", False):
            raise ConanException("with_symbols=True cannot be combined with with_strip=True")

    def build_requirements(self):
        # assembler
        if self.options.get_safe("with_asm"):
            self.tool_requires("nasm/2.16.01")
        if self.settings.os in ["Linux", "FreeBSD"]:
            if self.options.get_safe("with_libdrm"):
                self.tool_requires("libdrm/2.4.119")
        if self.settings_build.os == "Windows": # Note: we always do msys2 in this recipe and not is_msvc(self)
            self.win_bash = True
            if not self.conf.get("tools.microsoft.bash:path", check_type=str):
                self.tool_requires("msys2/cci.latest")

    def requirements(self):
        if self.options.get_safe("with_harfbuzz"):
            self.requires("harfbuzz/8.3.0")

    def package_id(self):
        del self.info.settings.build_type
        del self.info.settings.compiler

    def system_requirements(self):
        if cross_building(self) or self.settings.os == "Linux":
            apt = Apt(self)
            if self.options.get_safe("with_vaapi"):
                # apt.install(["libva2", "libva-dev"])
                pass
            if self.options.get_safe("with_vdpau"):
                # apt.install(["libvdpau", "libvdpau-dev"])
                pass
            if cross_building(self) and self.settings.os == "Windows":
                packages = [
                    "mingw-w64",
                    "mingw-w64-common",
                    "mingw-w64-tools",
                    "mingw-w64-x86-64-dev",
                    "gcc-mingw-w64",
                    "gcc-mingw-w64-x86-64",
                    "g++-mingw-w64",
                    "g++-mingw-w64-x86-64",
                ]
                apt.install(packages)
            else:
                if self.options.get_safe("with_v4l"):
                    # apt.install(["libv4l-dev", "libv4l-0"])
                    pass
        if self.settings.os == "Windows":
            pacman = PacMan(self)
            pacman.install(["make"])

    def source(self):
        dst_path = Path(os.path.join(".", self.CHECKOUT_PATH_FFMPEG))
        self._get_source(DependenyComponent.FFMPEG, dst_path)

    def generate(self):
        vb = VirtualBuildEnv(self)
        env = vb.environment()
        env.prepend_path("PKG_CONFIG_PATH", self._deps_pkg_config_path())
        self._setup_msys2_env(env)
        buildenv_vars = env.vars(self)
        buildenv_vars.save_script(vb._filename)

        if not cross_building(self):
            env = VirtualRunEnv(self)
            env.generate()

        if (self.settings.os == "Windows" and is_msvc(self)
                and self.options.get_safe("with_symbols", False)):
            self._patch_msvc_pdb_link_flags()

        args = self._get_configure_args()
        tc = self._create_toolchain()

        compilers_from_conf = self.conf.get("tools.build:compiler_executables", default={}, check_type=dict)
        self.output.info("Compiler conf tools.build:compiler_executables:")
        self.output.info(f"{compilers_from_conf}")
        nm = buildenv_vars.get("NM")
        if nm:
            args.append(f"--nm={unix_path(self, nm)}")
        ar = buildenv_vars.get("AR")
        if ar:
            args.append(f"--ar={unix_path(self, ar)}")
        if self.options.get_safe('with_asm'):
            if is_apple_os(self):
                asm = buildenv_vars.get("AS")
                self.output.info(f"AS={asm}")
            else:
                asm = compilers_from_conf.get("asm", buildenv_vars.get("AS"))
            if asm:
                args.append(f"--as={unix_path(self, asm)}")
        strip = buildenv_vars.get("STRIP")
        if strip:
            args.append(f"--strip={unix_path(self, strip)}")
        cc = compilers_from_conf.get("c", buildenv_vars.get("CC", self._default_compilers.get("cc")))
        if cc:
            args.append(f"--cc={unix_path(self, cc)}")
        cxx = compilers_from_conf.get("cpp", buildenv_vars.get("CXX", self._default_compilers.get("cxx")))
        if cxx:
            args.append(f"--cxx={unix_path(self, cxx)}")
        ld = buildenv_vars.get("LD")
        if ld:
            args.append(f"--ld={unix_path(self, ld)}")
        ranlib = buildenv_vars.get("RANLIB")
        if ranlib:
            args.append(f"--ranlib={unix_path(self, ranlib)}")
        pkg_config = self.conf.get("tools.gnu:pkg_config", default=buildenv_vars.get("PKG_CONFIG"), check_type=str)
        if pkg_config:
            # the ffmpeg configure script hardcodes the name of the executable,
            # unlike other tools that use the PKG_CONFIG environment variable
            # if we are aware the user has requested a specific pkg-config, we pass it to the configure script
            args.append(f"--pkg-config={unix_path(self, pkg_config)}")
        else:
            self._setup_msys2_pkgconfig()
        if is_msvc(self):
            args.append("--toolchain=msvc")
            if not check_min_vs(self, "190", raise_invalid=False):
                # Visual Studio 2013 (and earlier) doesn't support "inline" keyword for C (only for C++)
                tc.extra_defines.append("inline=__inline")
        if self.settings.compiler == "apple-clang" and Version(self.settings.compiler.version) >= "15":
            # Workaround for link error "ld: building exports trie: duplicate symbol '_av_ac3_parse_header'"
            # tc.extra_ldflags.append("-Wl,-ld_classic")
            pass
        if cross_building(self):
            if is_apple_os(self) and self.options.with_audiotoolbox:
                args.append("--disable-outdev=audiotoolbox")

        tc.extra_cflags = self._get_cflags()
        tc.extra_ldflags = self._get_ldflags()

        if tc.cflags:
            args.append("--extra-cflags={}".format(" ".join(tc.cflags)))
        if tc.ldflags:
            args.append("--extra-ldflags={}".format(" ".join(tc.ldflags)))
        tc.configure_args.extend(args)
        self.output.info(tc.cflags)
        try:
            tc.generate()
            if is_msvc(self):
                # Custom AutotoolsDeps for cl like compilers
                # workaround for https://github.com/conan-io/conan/issues/12784
                includedirs = []
                defines = []
                libs = []
                libdirs = []
                linkflags = []
                cxxflags = []
                cflags = []
                for dependency in self.dependencies.values():
                    deps_cpp_info = dependency.cpp_info.aggregated_components()
                    includedirs.extend(deps_cpp_info.includedirs)
                    defines.extend(deps_cpp_info.defines)
                    libs.extend(deps_cpp_info.libs + deps_cpp_info.system_libs)
                    libdirs.extend(deps_cpp_info.libdirs)
                    linkflags.extend(deps_cpp_info.sharedlinkflags + deps_cpp_info.exelinkflags)
                    cxxflags.extend(deps_cpp_info.cxxflags)
                    cflags.extend(deps_cpp_info.cflags)

                env = Environment()
                env.append("CPPFLAGS", [f"-I{unix_path(self, p)}" for p in includedirs] + [f"-D{d}" for d in defines])
                env.append("_LINK_", [lib if lib.endswith(".lib") else f"{lib}.lib" for lib in libs])
                env.append("LDFLAGS", [f"-LIBPATH:{unix_path(self, p)}" for p in libdirs] + linkflags)
                env.append("CXXFLAGS", cxxflags)
                env.append("CFLAGS", cflags)
                env.vars(self).save_script("conanautotoolsdeps_cl_workaround")
            else:
                deps = AutotoolsDeps(self)
                deps.generate()
            deps = PkgConfigDeps(self)
            deps.generate()
        except Exception as e:
            traceback.print_exc()
            raise e

    def build(self):
        shutil.rmtree(self._deps_root, ignore_errors=True)
        build_env = VirtualBuildEnv(self).vars()
        with build_env.apply():
            if self.options.get_safe('with_amf'):
                self._setup_amfheaders()
            if self.options.get_safe('with_nvenc'):
                self._setup_nvheaders()
            if self.options.get_safe('with_vulkan'):
                self._setup_vulkanheaders()
            if self.options.get_safe('with_qsv'):
                self._setup_qsv()
            if self.options.get_safe('with_vaapi'):
                self._setup_vaapi()
            if self.options.get_safe('with_vdpau'):
                self._setup_vdpau()

            autotools = Autotools(self)
            with chdir(self, os.path.join(self.source_folder, self.CHECKOUT_PATH_FFMPEG)):
                try:
                    autotools.configure(build_script_folder=os.path.join(self.source_folder, self.CHECKOUT_PATH_FFMPEG))
                except Exception as e:
                    self.run("tail -n 1000 ffbuild/config.log")
                    raise e
                autotools.make()
                autotools.install(args=["DESTDIR="])

                # FFmpeg's MSVC shared-library links write the PDB beside the
                # per-library build output.  The upstream install rules do
                # not reliably copy those PDBs to the configured prefix, so
                # preserve them explicitly for package().
                if (self.settings.os == "Windows" and is_msvc(self)
                        and self.options.get_safe("with_symbols", False)):
                    install_bin = Path(self._ffmpeg_build_path, "bin")
                    install_bin.mkdir(parents=True, exist_ok=True)
                    for pdb in Path(self.source_folder, self.CHECKOUT_PATH_FFMPEG).rglob("*.pdb"):
                        if not pdb.is_file():
                            continue
                        # vc*.pdb is the compiler-side intermediate PDB
                        # produced by /Zi, not a DLL linker PDB.
                        if pdb.name.lower().startswith("vc"):
                            continue
                        destination = install_bin / pdb.name
                        if pdb.resolve() != destination.resolve():
                            shutil.copy2(pdb, destination)

    def _patch_msvc_pdb_link_flags(self):
        """Give each MSVC FFmpeg DLL a distinct PDB in its build output."""
        configure = Path(self.source_folder, self.CHECKOUT_PATH_FFMPEG, "configure")
        text = configure.read_text(encoding="utf-8")
        replacements = (
            (
                "SHFLAGS='-Wl,-dll -Wl,-def:$$(@:$(SLIBSUF)=.def) "
                "-Wl,-implib:$(SUBDIR)$(SLIBNAME:$(SLIBSUF)=.lib)'",
                "SHFLAGS='-Wl,-dll -Wl,-def:$$(@:$(SLIBSUF)=.def) "
                "-Wl,-implib:$(SUBDIR)$(SLIBNAME:$(SLIBSUF)=.lib) "
                "-Wl,-pdb:$$(@:$(SLIBSUF)=.pdb)'",
            ),
            (
                "SHFLAGS='-dll -def:$$(@:$(SLIBSUF)=.def) "
                "-implib:$(SUBDIR)$(SLIBNAME:$(SLIBSUF)=.lib)'",
                "SHFLAGS='-dll -def:$$(@:$(SLIBSUF)=.def) "
                "-implib:$(SUBDIR)$(SLIBNAME:$(SLIBSUF)=.lib) "
                "-pdb:$$(@:$(SLIBSUF)=.pdb)'",
            ),
        )
        for old, new in replacements:
            if text.count(old) != 1:
                raise ConanException(
                    "Unable to add per-DLL PDB output to FFmpeg configure "
                    f"(expected one MSVC SHFLAGS entry, found {text.count(old)})")
            text = text.replace(old, new)
        configure.write_text(text, encoding="utf-8")

    def package(self):
        if self.options.get_safe("with_symbols", False):
            self._verify_build_symbols()
        absolute_to_relative_symlinks(self, self._deps_lib_path())
        absolute_to_relative_symlinks(self, os.path.join(self._ffmpeg_build_path, "lib"))
        # all platforms: headers
        copy(self, "*.h", src=os.path.join(self._ffmpeg_build_path, "include"),
             dst=os.path.join(self.package_folder, "include"), keep_path=True)
        if self.options.get_safe('with_amf'):
            copy(self, "*.h",
                 src=os.path.join(self.build_folder, self.DEPS_ROOT, "include", "AMF"),
                 dst=os.path.join(self.package_folder, "include", "AMF"), keep_path=True)
        if self.options.get_safe('with_nvenc'):
            copy(self, "*.h",
                 src=os.path.join(self.build_folder, self.DEPS_ROOT, "include", "ffnvcodec"),
                 dst=os.path.join(self.package_folder, "include", "ffnvcodec"), keep_path=True)
        if self.options.get_safe('with_qsv'):
            copy(self, "*.h",
                 src=os.path.join(self.build_folder, self.DEPS_ROOT, "include", "vpl"),
                 dst=os.path.join(self.package_folder, "include", "vpl"), keep_path=True)
            copy(self, "*.a", src=os.path.join(self.build_folder, self.DEPS_ROOT, "lib"),
                 dst=os.path.join(self.package_folder, "lib"), keep_path=False)
            copy(self, "*.lib", src=os.path.join(self.build_folder, self.DEPS_ROOT, "lib"),
                 dst=os.path.join(self.package_folder, "lib"), keep_path=False)
        # linux .so
        copy(self, "*.so.*", os.path.join(self._ffmpeg_build_path, "lib"), os.path.join(self.package_folder, "lib"), keep_path=False)
        copy(self, "*.so", os.path.join(self._ffmpeg_build_path, "lib"), os.path.join(self.package_folder, "lib"), keep_path=False)
        # vaapi (linux only) copy .so's for systems that don't have libva installed
        copy(self, "libva*.so.*", self._deps_lib_path(), os.path.join(self.package_folder, "lib"), keep_path=False)
        copy(self, "libva*.so", self._deps_lib_path(), os.path.join(self.package_folder, "lib"), keep_path=False)
        # libva public headers (va/va.h, va/va_drm.h, ...): needed by consumers
        # that call libva directly at build time (e.g. hw_probe/qsv_probe). We
        # don't want to depend on libva-dev being installed on every build
        # host.
        if self.options.get_safe('with_vaapi'):
            copy(self, "*.h", os.path.join(self._deps_include_path(), "va"),
                 os.path.join(self.package_folder, "include", "va"), keep_path=True)
        copy(self, "libvdpau*.so.*", self._deps_lib_path(), os.path.join(self.package_folder, "lib"), keep_path=False)
        copy(self, "libvdpau*.so", self._deps_lib_path(), os.path.join(self.package_folder, "lib"), keep_path=False)
        # windows .dll and .lib for linker tables
        copy(self, "*.dll", src=os.path.join(self._ffmpeg_build_path, "bin"),
             dst=os.path.join(self.package_folder, "bin"), keep_path=False)
        copy(self, "*.dll.*", src=os.path.join(self._ffmpeg_build_path, "bin"),
             dst=os.path.join(self.package_folder, "bin"), keep_path=False)
        # MSVC emits the PDBs next to the generated DLLs.  The source checkout
        # is never a valid source for build symbols and may contain stale files.
        if self.options.get_safe("with_symbols", False):
            pdb_sources = [
                os.path.join(self._ffmpeg_build_path, "bin"),
                self._ffmpeg_build_path,
            ]
            for pdb_source in pdb_sources:
                copy(self, "*.pdb", src=pdb_source,
                     dst=os.path.join(self.package_folder, "bin"), keep_path=False,
                     excludes="vc*.pdb")

            if self.settings.os == "Windows":
                dlls = list(Path(self._ffmpeg_build_path, "bin").glob("*.dll"))
                pdbs = {path.stem.lower() for source in pdb_sources
                        for path in Path(source).glob("*.pdb")
                        if not path.name.lower().startswith("vc")}
                missing = [dll.name for dll in dlls if dll.stem.lower() not in pdbs]
                if missing:
                    raise ConanException(
                        "FFmpeg symbol build produced DLLs without matching PDBs: "
                        + ", ".join(sorted(missing)))
        copy(self, "*.lib", src=os.path.join(self._ffmpeg_build_path, "bin"),
             dst=os.path.join(self.package_folder, "lib"), keep_path=False)

        # mac dylibs
        # excludes=["*.dSYM/*"]: copy() recurses into subdirectories, and the
        # dSYM bundle's inner DWARF companion is named identically to the real
        # dylib (e.g. libavcodec.62.11.100.dylib) and also matches "*.dylib".
        # Without the exclude, keep_path=False would flatten that DWARF file
        # over the real dylib, shipping a dSYM companion instead of the library.
        copy(self, "*.dylib", src=os.path.join(self._ffmpeg_build_path, "bin"),
             dst=os.path.join(self.package_folder, "lib"), keep_path=False,
             excludes=["*.dSYM/*"])
        copy(self, "*.dylib", src=os.path.join(self._ffmpeg_build_path, "lib"),
             dst=os.path.join(self.package_folder, "lib"), keep_path=False,
             excludes=["*.dSYM/*"])
        if self.options.get_safe("with_symbols", False) and self.settings.os == "Macos":
            expected_dsyms = []
            for symbol_source in (
                    os.path.join(self._ffmpeg_build_path, "bin"),
                    os.path.join(self._ffmpeg_build_path, "lib")):
                # A dSYM is a directory bundle.  Conan's `copy("*.dSYM", ...)`
                # only matches the directory entry and does not copy the bundle
                # contents, leaving an apparently successful package with no
                # usable symbols.  Copy each bundle recursively instead.
                for dsym in Path(symbol_source).glob("*.dSYM"):
                    if not dsym.is_dir():
                        continue
                    expected_dsyms.append(dsym.name)
                    copy(self, "*", src=str(dsym),
                         dst=os.path.join(self.package_folder, "lib", dsym.name),
                         keep_path=True)

            package_lib = Path(self.package_folder, "lib")
            missing_dsyms = [name for name in expected_dsyms
                             if not (package_lib / name / "Contents" / "Resources" /
                                     "DWARF").is_dir()]
            if missing_dsyms:
                raise ConanException(
                    "FFmpeg symbol packaging failed to copy dSYMs: "
                    + ", ".join(sorted(missing_dsyms)))

            # Strip the real, packaged dylibs (debug + local symbols only;
            # exported symbols and LC_UUID are preserved) now that their dSYM
            # companions are confirmed present, so the dSYMs stay matched.
            # Top-level glob only: must not descend into the *.dSYM bundles
            # just verified above.
            strip_tool = shutil.which("strip") or "strip"
            for dylib in package_lib.glob("*.dylib"):
                if dylib.is_symlink():
                    continue
                subprocess.run([strip_tool, "-S", "-x", str(dylib)], check=True)

        # licenses (FFmpeg ships multiple COPYING* and LICENSE files)
        # usually, LGPLv3 is the correct one to consider without any changes to this conanfile.
        # Otherwise, other licenses might apply.
        copy(self, "LICENSE*", src=os.path.join(self.source_folder, self.CHECKOUT_PATH_FFMPEG),
             dst=os.path.join(self.package_folder, "licenses"), keep_path=False)
        copy(self, "COPYING*", src=os.path.join(self.source_folder, self.CHECKOUT_PATH_FFMPEG),
             dst=os.path.join(self.package_folder, "licenses"), keep_path=False)

        fix_apple_shared_install_name(self)

    def package_info(self):
        def _add_component(name, dependencies):
            component = self.cpp_info.components[name]
            component.set_property("pkg_config_name", f"lib{name}")
            self._set_component_version(name)
            component.libs = [name]
            if name != "avutil":
                component.requires = ["avutil"]
            for dep in dependencies:
                component.requires.append(dep)
            if self.settings.os in ("FreeBSD", "Linux"):
                component.system_libs.append("m")
            return component

        avutil = _add_component("avutil", [])
        avfilter = _add_component("avfilter", ["swscale", "avformat", "avcodec", "swresample"])
        avformat = _add_component("avformat", ["avcodec", "swscale"])
        avcodec = _add_component("avcodec", ["swresample"])
        _add_component("swscale", [])
        swresample = _add_component("swresample", [])

        if self.options.get_safe('with_amf'):
            amf_version = self._read_amf_version()
            if amf_version is not None:
                self.cpp_info.components["AMF"].set_property("component_version", amf_version)
                self.cpp_info.components["AMF"].version = amf_version
            else:
                self.output.warning(f"cannot determine AMF version!")

        if self.options.get_safe('with_nvenc'):
            nvenc_version = self._read_nvenc_version()
            if nvenc_version is not None:
                self.cpp_info.components["NVENC"].set_property("component_version", nvenc_version)
                self.cpp_info.components["NVENC"].version = nvenc_version
            else:
                self.output.warning(f"cannot determine NVENC version!")

        if self.options.get_safe('with_qsv'):
            qsv_version = self._read_qsv_version()
            if qsv_version is not None:
                self.cpp_info.components["QSV"].set_property("component_version", qsv_version)
                self.cpp_info.components["QSV"].version = qsv_version
            else:
                self.output.warning(f"cannot determine QSV version!")


        if self.settings.os in ("FreeBSD", "Linux"):
            avutil.system_libs.extend(["pthread", "dl"])
            if self.options.get_safe("fPIC"):
                if self.settings.compiler in ("gcc", "clang"):
                    # https://trac.ffmpeg.org/ticket/1713
                    # https://ffmpeg.org/platform.html#Advanced-linking-configuration
                    # https://ffmpeg.org/pipermail/libav-user/2014-December/007719.html
                    avcodec.exelinkflags.append("-Wl,-Bsymbolic")
                    avcodec.sharedlinkflags.append("-Wl,-Bsymbolic")
            avfilter.system_libs.append("pthread")
        elif self.settings.os == "Windows":
            avcodec.system_libs = ["mfplat", "mfuuid", "strmiids"]
            avutil.system_libs = ["user32", "bcrypt"]
            avformat.system_libs = ["secur32"]
        elif is_apple_os(self):
            avfilter.frameworks = ["CoreGraphics"]
            avcodec.frameworks = ["CoreFoundation", "CoreVideo", "CoreMedia"]
            if self.settings.os == "Macos":
                avfilter.frameworks.append("OpenGL")
            avfilter.frameworks.append("Metal")

        if self.options.get_safe("with_audiotoolbox"):
            avcodec.frameworks.append("AudioToolbox")
        if self.options.get_safe("with_videotoolbox"):
            avcodec.frameworks.append("VideoToolbox")

        if self.options.get_safe("with_appkit"):
            avfilter.frameworks.append("AppKit")
        if self.options.get_safe("with_coreimage"):
            avfilter.frameworks.append("CoreImage")

        # Headers-only component for consumers that dlopen FFmpeg at runtime
        # (see teamspeak_client_lib's FFmpegDynamicLib). Exposes include_dirs
        # only — no .libs, no system_libs, no frameworks, no requires — so
        # consumers get the public headers without dragging any link flags
        # into their link line.
        headers = self.cpp_info.components["headers"]
        headers.set_property("pkg_config_name", "libffmpeg_headers")

    @property
    def _ffmpeg_build_path(self):
        return os.path.join(self.build_folder, self.BUILD_PATH)

    def _verify_build_symbols(self):
        """Fail before packaging if the requested symbols were stripped."""
        if self.settings.os == "Windows":
            # MSVC emits one PDB beside each generated DLL.  The detailed
            # per-DLL check below also catches partial FFmpeg builds.
            if not is_msvc(self):
                return
            dll_dir = Path(self._ffmpeg_build_path, "bin")
            pdbs = {path.stem.lower() for path in dll_dir.glob("*.pdb")}
            missing = [dll.name for dll in dll_dir.glob("*.dll")
                       if dll.stem.lower() not in pdbs]
            if missing:
                raise ConanException(
                    "FFmpeg symbol build produced DLLs without matching PDBs: "
                    + ", ".join(sorted(missing)))
            return

        if self.settings.os in ("Linux", "Android"):
            binaries = [path for path in Path(self._ffmpeg_build_path, "lib").glob("*.so*")
                        if path.is_file() and not path.is_symlink()]
            readelf = shutil.which("llvm-readelf") or shutil.which("readelf")
            if not readelf:
                raise ConanException("with_symbols=True requires llvm-readelf or readelf")
            missing = []
            for binary in binaries:
                result = subprocess.run([readelf, "-S", str(binary)],
                                        capture_output=True, text=True, check=True)
                if ".debug_info" not in result.stdout:
                    missing.append(binary.name)
            if missing:
                raise ConanException(
                    "FFmpeg symbol build produced ELF libraries without DWARF: "
                    + ", ".join(sorted(missing)))
            return

        if self.settings.os == "Macos":
            binaries = [path for root in ("bin", "lib")
                        for path in Path(self._ffmpeg_build_path, root).glob("*.dylib")
                        if path.is_file() and not path.is_symlink()]
            dsymutil = shutil.which("dsymutil")
            if not dsymutil:
                raise ConanException("with_symbols=True requires dsymutil")
            missing = []
            for binary in binaries:
                dsym = Path(str(binary) + ".dSYM")
                subprocess.run([dsymutil, str(binary), "-o", str(dsym)], check=True)
                dwarf_dir = dsym / "Contents" / "Resources" / "DWARF"
                if not dwarf_dir.is_dir() or not any(item.is_file() for item in dwarf_dir.iterdir()):
                    missing.append(binary.name)
            if missing:
                raise ConanException(
                    "FFmpeg symbol build produced Mach-O libraries without dSYMs: "
                    + ", ".join(sorted(missing)))

    @property
    def _deps_root(self):
        return os.path.join(self.source_folder, self.DEPS_ROOT)

    @property
    def _target_os(self):
        if self.settings.os == "Windows":
            return "win32" if is_msvc(self) else "mingw32"
        elif is_apple_os(self):
            return "darwin"

        # Taken from https://github.com/FFmpeg/FFmpeg/blob/0684e58886881a998f1a7b510d73600ff1df2b90/configure#L5485
        # This is the map of Conan OS settings to FFmpeg acceptable values
        return {
            "AIX": "aix",
            "Android": "android",
            "FreeBSD": "freebsd",
            "Linux": "linux",
            "Neutrino": "qnx",
            "SunOS": "sunos",
        }.get(str(self.settings.os), "none")

    @property
    def _target_arch(self):
        # Taken from acceptable values https://github.com/FFmpeg/FFmpeg/blob/0684e58886881a998f1a7b510d73600ff1df2b90/configure#L5010
        if str(self.settings.arch).startswith("armv8"):
            return "aarch64"
        elif self.settings.arch == "x86":
            return "i686"
        return str(self.settings.arch)

    @property
    def _default_compilers(self):
        if self.settings.compiler == "gcc":
            return {"cc": "gcc", "cxx": "g++"}
        elif self.settings.compiler in ["clang", "apple-clang"]:
            return {"cc": "clang", "cxx": "clang++"}
        elif is_msvc(self):
            return {"cc": "cl.exe", "cxx": "cl.exe"}
        return {}

    def _get_local_source(self, component: DependenyComponent, target_path: Path):
        cd = self.conan_data["sources"][self.version]
        local_root = '.'
        if 'local_root' in cd:
            local_root = cd['local_root']
        comp = cd[component.value]
        if 'local' not in comp:
            return False 
        local_path = Path(os.path.join(local_root, comp['local']))
        if not local_path.exists() or not local_path.is_dir():
            self.output.info(f'Skipping local version for {component.value} since "{local_path.absolute()}" doesn\'t exist...')
            return False

        # copy to target path
        os.makedirs(target_path.absolute(), exist_ok=True)
        shutil.copytree(local_path.absolute(), target_path.absolute(), symlinks=True, ignore_dangling_symlinks=True, dirs_exist_ok=True)
        return True
  
    def _normalize_sparse(spec) -> list[str]:
        """
        Accepts either a single string or a list/tuple of strings.
        Returns a normalized list of sparse paths (may be empty).
        """
        if not spec:
            return []
        if isinstance(spec, str):
            return [spec]
        if isinstance(spec, (list, tuple)):
            return [str(p) for p in spec if p]
        raise ValueError(f"Invalid 'sparse' specification: {spec!r}")
    
    def _get_git_source(self, component: DependenyComponent, target_path: Path):
        comp = self.conan_data["sources"][self.version][component.value]
        repo = self.conan_data["repos"][component.value]["git"]
        if repo is None or len(repo) == 0:
            self.output.error(f"Repository is undefined for dependency {component.value}, cannot fetch sources!")
            return False

        sparse_paths = []
        if 'sparse' in self.conan_data["repos"][component.value]:
            if isinstance(self.conan_data["repos"][component.value]["sparse"], str):
                sparse_paths = [self.conan_data["repos"][component.value]["sparse"]]
            else:
                sparse_paths =[str(p) for p in self.conan_data["repos"][component.value]["sparse"] if p]
 
        sparse_patterns: list[str] = []
        for raw in sparse_paths:
            p = str(raw).strip().strip('"').strip("'").strip('/')
            if not p:
                continue
            # Include as-file and as-dir patterns; one of them will match appropriately.
            sparse_patterns.append(f"/{p}")        # exact file (or path)
            sparse_patterns.append(f"/{p}/")       # the directory itself
            sparse_patterns.append(f"/{p}/**")     # everything under the directory

        use_commit = 'commit' in comp
 
        os.makedirs(target_path.absolute(), exist_ok=True)

        git = Git(self)
        clone_args = ['-n']
        if sparse_patterns:
            clone_args.append('--filter=tree:0')
        with chdir(self, target_path.absolute()):
            if not use_commit:
                clone_args.extend(['-b', comp['tag'], '--depth', '1'])
            git.clone(url=repo, target=".", args=clone_args)

            if sparse_patterns:
                git.run(f'sparse-checkout set --no-cone {" ".join(sparse_patterns)}')

            if use_commit:
                git.run(f'checkout {comp["commit"]}')
            else:
                git.run('checkout')

        return True

    def _get_source(self, component: DependenyComponent, target_path: Path):
        if self._get_local_source(component, target_path):
            return
        if self._get_git_source(component, target_path):
            return
        raise ConanException(f'Couldn\'t fetch source for component {component.value}, failed to build.')

    def _setup_msys2_env(self, env):
        if not self.settings.os == "Windows":
            return

        self.win_bash = True
        print(self.conf.get("tools.microsoft.bash:path"))
        if not self.conf.get("tools.microsoft.bash:path", check_type=str):
            # check if it exists
            raise ConanException("MSYS2 Conf \"tools.microsoft.bash:path\" not set. This is required for a Windows build."
                                 "Install MSYS2 and add the path to the bash.exe of the installation to the [conf] section of your profile.")
        if not self.conf.get("tools.microsoft.bash:subsystem", check_type=str):
            raise ConanException("MSYS2 Conf \"tools.microsoft.bash:subsystem\" not set. This is required for a Windows build."
                                 "Add it to the [conf] section of your profile with a value of \"msys2\".")
        if not self.conf.get("tools.microsoft.bash:subsystem", check_type=str) == "msys2":
            raise ConanException(
                f"MSYS2 Conf \"tools.microsoft.bash:subsystem\" is set to {self.conf.get('tools.microsoft.bash:subsystem', check_type=str)}. But it is required to be set to msys2.")

        self.msys_bin = os.path.dirname(os.path.abspath(self.conf.get("tools.microsoft.bash:path", check_type=str)))
        self.msys_root = os.path.join(self.msys_bin, os.pardir, os.pardir)

        if not os.path.exists(self.msys_root):
            err = f"MSYS2 root ({self.msys_root}) not found."
            self.output.error(err)
            raise ConanException(err)
        self.output.info(f"MSYS2 Root: {self.msys_root}, Bin: {self.msys_bin}")

        env.prepend_path("PATH", self.msys_bin)
        env.define_path("MSYS_ROOT", self.msys_root)
        env.define_path("MSYS_BIN", self.msys_bin)

    def _setup_msys2_pkgconfig(self):
        if not self.settings.os == "Windows":
            return
        self.run('pacman -S --noconfirm pkg-config make')
        pass

    def _read_component_version(self, component_name):
        # since 5.1, major version may be defined in version_major.h instead of version.h
        component_folder = os.path.join(self.package_folder, "include", f"lib{component_name}")
        version_file_name = os.path.join(component_folder, "version.h")
        version_major_file_name = os.path.join(component_folder, "version_major.h")
        pattern = f"define LIB{component_name.upper()}_VERSION_(MAJOR|MINOR|MICRO)[ \t]+(\\d+)"
        version = dict()
        for file in (version_file_name, version_major_file_name):
            if os.path.isfile(file):
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        match = re.search(pattern, line)
                        if match:
                            version[match[1]] = match[2]
        if "MAJOR" in version and "MINOR" in version and "MICRO" in version:
            return f"{version['MAJOR']}.{version['MINOR']}.{version['MICRO']}"
        return None

    def _set_component_version(self, component_name):
        version = self._read_component_version(component_name)
        if version is not None:
            self.cpp_info.components[component_name].set_property("component_version", version)
            # TODO: to remove once support of conan v1 dropped
            self.cpp_info.components[component_name].version = version
        else:
            self.output.warning(f"cannot determine version of lib{component_name} packaged with ffmpeg!")

    def _read_amf_version(self):
        version_path = os.path.join(self.package_folder, "include", "AMF", "core", "Version.h")
        pattern = f"define AMF_VERSION_(MAJOR|MINOR|RELEASE|BUILD\_NUM)\s*(\\d+)"
        version = dict()
        with open(version_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    version[match[1]] = match[2]
        if "MAJOR" in version and "MINOR" in version and "RELEASE" in version and "BUILD_NUM" in version:
            return f"{version['MAJOR']}.{version['MINOR']}.{version['RELEASE']}.{version['BUILD_NUM']}"
        return None

    def _read_nvenc_version(self):
        version_path = os.path.join(self.package_folder, "include", "ffnvcodec", "nvEncodeAPI.h")
        pattern = f"define NVENCAPI_(MAJOR|MINOR)_VERSION\s*(\\d+)"
        version = dict()
        with open(version_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    version[match[1]] = match[2]
        if "MAJOR" in version and "MINOR" in version:
            return f"{version['MAJOR']}.{version['MINOR']}"
        return None

    def _read_qsv_version(self):
        version_path = os.path.join(self.package_folder, "include", "vpl", "mfxdefs.h")
        pattern = f"define MFX_VERSION_(MAJOR|MINOR)\s*(\\d+)"
        version = dict()
        with open(version_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    version[match[1]] = match[2]
        if "MAJOR" in version and "MINOR" in version:
            return f"{version['MAJOR']}.{version['MINOR']}"
        return None

    def _create_toolchain(self):
        tc = AutotoolsToolchain(self)
        tc.update_configure_args({
            "--sbindir": None,
            "--includedir": None,
            "--oldincludedir": None,
            "--datarootdir": None,
            "--build": None,
            "--host": None,
            "--target": None,
            "--prefix": None,
        })
        return tc

    def _get_cflags(self):
        cflags = [f'-I{unix_path(self, self._deps_include_path())}']
        if self.options.get_safe("with_qsv"):
            cflags.append(f'-I{unix_path(self, os.path.join(self._deps_include_path(), "vpl"))}')
        if cross_building(self):
            cflags.append("-D_FORTIFY_SOURCE=0")
            cflags.append("-U_FORTIFY_SOURCE")
        if self.options.get_safe("with_symbols", False):
            # The recipe runs through an MSYS2 bash shell on Windows.  MSYS2
            # treats slash-prefixed arguments as paths, so `/Zi` becomes a
            # bogus `.../msys64/Zi` source path before cl.exe sees it.  MSVC
            # accepts both slash and dash option spelling; use the latter to
            # preserve the flag through MSYS2 argument conversion.
            cflags.append("-Zi" if is_msvc(self) else "-g")
        return cflags

    def _get_ldflags(self):
        ldflags = []
        if self.settings.os == "Windows":
            ldflags.append(f'-LIBPATH:{self._deps_lib_path()}')
            # Use dash spelling for MSYS2 compatibility; link.exe accepts it
            # and MSYS2 will not reinterpret it as a filesystem path.
            ldflags.append("-DEBUG")
            if self.options.get_safe("with_symbols", False):
                ldflags.append("-DEBUG:FULL")
        else:
            ldflags.append(f'-L{unix_path(self, self._deps_lib_path())}')
        if cross_building(self) and self.settings.os == "Windows":
            ldflags.append("-static")
        # ffmpeg is pure C — don't link any C++ runtime into its shared libraries.
        # ffmpeg is pure C — never link any C++ runtime.
        # Without this, clang's -static-libstdc++ from the profile bakes libc++
        # into the output, which contaminates processes that load them.
        if self.settings.os == "Linux":
            ldflags.append("-nostdlib++")
        return ldflags

    def _get_configure_args(self):
        codecs = ["av1", "vp8", "vp9"]
        if self.options.get_safe('with_h264'):
            codecs.append("h264")
        hwaccels = []
        extra_args = []

        if self.options.get_safe('with_vaapi'):
            hwaccels.append("vaapi")

        if self.options.get_safe('with_vdpau'):
            hwaccels.append("vdpau")

        if self.options.get_safe('with_v4l'):
            hwaccels.append(("libv4l2", "v4l2m2m"))

        if self.options.get_safe('with_qsv'):
            hwaccels.append(("libvpl", "qsv"))

        if self.options.get_safe('with_amf'):
            hwaccels.append('amf')

        if self.options.get_safe('with_vulkan'):
            hwaccels.append('vulkan')

        if self.options.get_safe("with_nvenc"):
            extra_args.append("--enable-ffnvcodec")
            hwaccels.append("nvenc")
            hwaccels.append("cuvid")

        if self.options.get_safe("with_videotoolbox"):
            hwaccels.append("videotoolbox")

        return self._generate_configure_args(unix_path(self, self._ffmpeg_build_path), codecs, hwaccels, extra_args)

    def _deps_include_path(self):
        return os.path.join(self._deps_root, 'include')

    def _deps_lib_path(self):
        return os.path.join(self._deps_root, 'lib')

    def _deps_pkg_config_path(self):
        return os.path.join(self._deps_root, self.PKG_CONFIG_SUB_PATH)

    def _setup_nvheaders(self):
        shutil.rmtree('nvheaders', ignore_errors=True)

        src_path = Path(os.path.join(".", "nvheaders")).absolute()
        self._get_source(DependenyComponent.NV, src_path)

        DST_PATH = Path(self._deps_root).absolute()
        with chdir(self, src_path):
            with open('Makefile', 'r') as fin:
                lines = fin.readlines()
                lines[0] = f"PREFIX = {DST_PATH}\n"
            with open('Makefile', 'w') as fout:
                fout.writelines(lines)

        tc = AutotoolsToolchain(self, namespace="nvheaders")
        tc.generate()
        autotools = Autotools(self, namespace='nvheaders')

        with chdir(self, src_path):
            autotools.make()
            autotools.install(args=["DESTDIR="])
        shutil.rmtree('nvheaders', ignore_errors=True)
        self.output.success(f"NV headers copied to {self._deps_include_path()}")

    def _setup_amfheaders(self):
        self.output.success(f"Retrieving AMF headers...")
        src_path = Path(os.path.join(".", "amfheaders"))

        self._get_source(DependenyComponent.AMF, src_path)
        
        # move files/folders to dst
        dst_dir = Path(os.path.join(self._deps_include_path(), "AMF")).absolute()
        os.makedirs(dst_dir, exist_ok=True)

        for f in Path(os.path.join(src_path, "amf", "public", "include")).iterdir():
            self.output.info(f"Moving {f.absolute()} to {os.path.join(dst_dir, f.name)}")
            shutil.move(f.absolute(), os.path.join(dst_dir, f.name))

        # cleanup checkout
        shutil.rmtree(src_path.absolute(), ignore_errors=True)
        self.output.success(f"AMF headers copied to {self._deps_include_path()}")

    def _setup_vulkanheaders(self):
        self.output.success(f"Retrieving Vulkan headers...")
        src_path = Path(os.path.join(".", "vkheaders"))

        self._get_source(DependenyComponent.VK, src_path)
        
        # move files/folders to dst
        dst_dir = Path(self._deps_include_path()).absolute()
        os.makedirs(dst_dir.absolute(), exist_ok=True)

        for f in Path(os.path.join(src_path, "include")).iterdir():
            self.output.info(f"Moving {f.absolute()} to {os.path.join(dst_dir, f.name)}")
            shutil.move(f.absolute(), os.path.join(dst_dir, f.name))

        # cleanup checkout
        shutil.rmtree(src_path.absolute(), ignore_errors=True)
        self.output.success(f"Vulkan headers copied to {self._deps_include_path()}")

    def _setup_qsv(self):
        for build_type in ["Debug", "Release"]:
            # build oneVPL (libvpl) from source

            cleanup_files = [
                "conan_toolchain.cmake",
                "CMakePresets.json",
            ]
            for file in cleanup_files:
                p = Path(file)
                if p.exists():
                    os.remove(p)

            self.output.info(f"Building libvpl from source... crossbuild: {cross_building(self)}")
            checkout_dir = f"{self.CHECKOUT_PATH_LIBVPL}_{build_type.lower()}"
            dst_path = Path(os.path.join(".", checkout_dir)).absolute()
            self._get_source(DependenyComponent.LIBVPL, dst_path)

            tc = CMakeToolchain(self)
            tc.variables["BUILD_SHARED_LIBS"] = False
            tc.variables["CMAKE_INSTALL_PREFIX"] = unix_path(self, self._deps_root)
            tc.variables["CMAKE_BUILD_TYPE"] = build_type
            tc.variables["INSTALL_EXAMPLES"] = False
            if is_msvc(self):
                runtime: str = self.settings.get_safe("compiler.runtime")
                if runtime is not None:
                    is_static = runtime == "static" or runtime.startswith("MT")
                    tc.variables["CMAKE_MSVC_RUNTIME_LIBRARY"] = "MultiThreaded$<$<CONFIG:Debug>:Debug>" if is_static else "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL"
                    tc.variables["CMAKE_POLICY_DEFAULT_CMP0091"] = "NEW"
            if cross_building(self) and self.settings.os == "Windows":
                # cross-compile to Windows/MSYS2
                tc.variables["CMAKE_SYSTEM_NAME"] = "Windows"
                tc.variables["CMAKE_C_COMPILER"] = "x86_64-w64-mingw32-gcc"
                tc.variables["CMAKE_CXX_COMPILER"] = "x86_64-w64-mingw32-g++"
                tc.variables["CMAKE_RC_COMPILER"] = "x86_64-w64-mingw32-windres"

            # 2) Generate a CMake toolchain in the 'libvpl' namespace
            build_dir = os.path.join(dst_path.absolute(), 'build')
            os.makedirs(build_dir, exist_ok=True)
            original_build_dir = self.folders.base_build
            self.folders.set_base_build(build_dir)
            tc.generate()
            cmake = CMake(self)
            with chdir(self, build_dir):
                self.output.info(f"cmake configure with build_script_path={dst_path.absolute()}")
                cmake.configure(build_script_folder=dst_path.absolute(), variables=tc.variables)
                cmake.build(build_type=build_type)
                backup = self.folders.base_package
                self.folders.set_base_package(self._deps_root)
                cmake.install(build_type=build_type)
                self.folders.set_base_package(backup)
            self.folders.set_base_build(original_build_dir)

            # add -lc++ to Libs in package config
            if build_type == "Release":
                package_config_file = os.path.join(self._deps_pkg_config_path(), "vpl.pc")
                with open(package_config_file, 'r') as fin:
                    lines = fin.readlines()
                for (idx, line) in enumerate(lines):
                    if line.startswith('Libs: '):
                        if self.settings.os == "Windows":
                            libpath = os.path.join(self._deps_root, "lib", "vpl.lib").replace("\\", "/")
                            lines[idx] = f"Libs: {libpath} -lAdvapi32 -lOle32\n"
                        else:
                            libcpp = 'stdc++'
                            if self.settings.compiler == "clang":
                                libcpp = "c++"
                            lines[idx] = line.replace("-lvpl", f"-lvpl -l{libcpp}")
                with open(package_config_file, 'w') as fout:
                    fout.writelines(lines)

    def _setup_vaapi(self):
        self.output.info(f"Building libva from source...")
        dst_path = Path(os.path.join(".", self.CHECKOUT_PATH_LIBVA)).absolute()
        self._get_source(DependenyComponent.LIBVA, dst_path)
        with chdir(self, dst_path):
            self.run(f"./autogen.sh --prefix={self._deps_root} --libdir={self._deps_lib_path()} --with-drivers-path=/usr/lib/dri")
            self.run("make")
            self.run("make install")

    def _setup_vdpau(self):
        if self.settings.os not in ["Linux", "FreeBSD"]:
            return
        self.output.info(f"Building libvdpau from source...")
        dst_path = Path(os.path.join(".", self.CHECKOUT_PATH_LIBVDPAU)).absolute()
        self._get_source(DependenyComponent.LIBVDPAU, dst_path)

        with chdir(self, dst_path):
            self.run(f"meson setup builddir")
            self.run(f"meson configure builddir -Dprefix={self._deps_root} -Dbindir=bin -Ddatadir=share -Dincludedir=include -Dlibdir=lib -Dlibexecdir=libexec -Dbuildtype=release -Ddebug=false")
            self.run("meson compile -C builddir")
            self.run("meson install -C builddir")
 
    def _generate_configure_args(self, prefix, codecs, hwaccels, extra_args):
        """
        Generate an FFmpeg configure command.

        :param prefix: installation prefix for --prefix=
        :param codecs: list of codec names (e.g. ["h264", "av1"])
        :param hwaccels: list of hwaccel specs, each either:
            - a string "vaapi", "vdpau", etc. (suffix == lib flag)
            - a tuple ("libflag", "suffix") for cases like libv4l2/v4l2m2m
        :param extra_args: extra arguments to pass to ffmpeg
        """

        def opt_enable_disable(what, v):
            return "--{}-{}".format("enable" if v else "disable", what)

        args = [
            "--disable-everything",
            "--disable-programs",
            "--disable-doc",
            "--enable-shared",
            "--enable-version3",
            "--pkg-config-flags=--static",
            opt_enable_disable("libdrm", self.options.get_safe("with_libdrm")),
            opt_enable_disable("pic", self.options.get_safe("fPIC", True)),
            opt_enable_disable("appkit", self.options.get_safe("with_appkit")),
            opt_enable_disable("avfoundation", self.options.get_safe("with_avfoundation")),
            opt_enable_disable("coreimage", self.options.get_safe("with_coreimage")),
            opt_enable_disable("audiotoolbox", self.options.get_safe("with_audiotoolbox")),
            opt_enable_disable("videotoolbox", self.options.get_safe("with_videotoolbox")),
            opt_enable_disable("asm", self.options.get_safe("with_asm")),
            opt_enable_disable("stripping", self.options.get_safe("with_strip")),
            f"--prefix={prefix}",
            "--enable-avutil",
            "--enable-swscale",
            "--enable-avcodec",
            "--disable-avdevice",
            "--enable-filter=hwdownload",
            "--enable-filter=hwupload",
            "--enable-bsf=extract_extradata",
            "--enable-filter=sr_amf",
            "--enable-filter=format",
            f'--arch={self._target_arch}',
        ]
        args.extend(extra_args)
        if cross_building(self):
            args.extend([
                f'--target-os={self._target_os}',
                '--enable-cross-compile',
            ])
            if self.settings.os == "Windows":
                target = "x86_64-w64-mingw32"
                args.extend([
                    f"--cross-prefix={target}-",
                    f'--sysroot=/usr/{target}',
                    f'--sysinclude=/usr/{target}/include'
                ])
        if self.settings.build_type == "Debug":
            args.extend([
                "--disable-optimizations",
                "--disable-mmx",
                "--enable-debug",
            ])
        elif self.options.get_safe("with_symbols", False):
            # Keep Release optimizations; only request compiler debug data.
            args.append("--enable-debug")

        if self.settings.os == "Macos":
            # Install names default to the conan build-tree's absolute lib
            # path, which makes the dylibs unusable outside that machine —
            # and in particular breaks dlopen from the .app bundle. @rpath
            # lets consumers resolve via their own LC_RPATH / @loader_path.
            args.append("--install-name-dir=@rpath")

        # software codec cores + parsers
        # for codec in codecs:
        #     args += [
        #         f"--enable-decoder={codec}",
        #         f"--enable-encoder={codec}",
        #         f"--enable-parser={codec}",
        #     ]

        # hardware accel backends and their codec bindings
        for hw in hwaccels:
            if isinstance(hw, tuple):
                lib_flag, suffix = hw
            else:
                lib_flag = suffix = hw

            # enable the backend library
            args.append(f"--enable-{lib_flag}")

            # enable hw-specific encoders/decoders
            for codec in codecs:
                args.append(f"--enable-encoder={codec}_{suffix}")
                args.append(f"--enable-parser={codec}")
            for codec in codecs:
                args.append(f"--enable-decoder={codec}_{suffix}")

        # format as a line‑wrapped shell command
        return args
