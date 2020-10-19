{ stdenv, fetchFromGitHub, kernel, bc, nukeReferences }:

stdenv.mkDerivation rec {
  name = "rtl8189es-${kernel.version}-${version}";
  version = "2020-10-03";

  src = fetchFromGitHub {
    owner = "jwrdegoede";
    repo = "rtl8189ES_linux";
    rev = "930d3d7cfe3b25c0cf8a57ca4b79f6aef5b6de4b";
    sha256 = "026rrnm4wxyh4li03mpvza49mm0g5by754lrqxys934cmp8v6cv1";
  };

  nativeBuildInputs = [ bc nukeReferences ];
  buildInputs = kernel.moduleBuildDependencies;

  hardeningDisable = [ "pic" "format" ];

  prePatch = ''
    substituteInPlace ./Makefile --replace /lib/modules/ "${kernel.dev}/lib/modules/"
    substituteInPlace ./Makefile --replace '$(shell uname -r)' "${kernel.modDirVersion}"
    substituteInPlace ./Makefile --replace /sbin/depmod \#
    substituteInPlace ./Makefile --replace '$(MODDESTDIR)' "$out/lib/modules/${kernel.modDirVersion}/kernel/net/wireless/"
  '';

  makeFlags = [
    "ARCH=${stdenv.hostPlatform.platform.kernelArch}"
    "KSRC=${kernel.dev}/lib/modules/${kernel.modDirVersion}/build"
    ("CONFIG_PLATFORM_I386_PC=" + (if (stdenv.hostPlatform.isi686 || stdenv.hostPlatform.isx86_64) then "y" else "n"))
    ("CONFIG_PLATFORM_ARM_RPI=" + (if (stdenv.hostPlatform.isAarch32 || stdenv.hostPlatform.isAarch64) then "y" else "n"))
  ] ++ stdenv.lib.optional (stdenv.hostPlatform != stdenv.buildPlatform) [
    "CROSS_COMPILE=${stdenv.cc.targetPrefix}"
  ];

  preInstall = ''
    mkdir -p "$out/lib/modules/${kernel.modDirVersion}/kernel/net/wireless/"
  '';

  postInstall = ''
    nuke-refs $out/lib/modules/*/kernel/net/wireless/*.ko
  '';

  meta = with stdenv.lib; {
    description = "Driver for Realtek rtl8189es";
    homepage = "https://github.com/jwrdegoede/rtl8189ES_linux";
    license = licenses.gpl2;
    platforms = platforms.linux;
    maintainers = with maintainers; [ danielfullmer ];
  };
}
