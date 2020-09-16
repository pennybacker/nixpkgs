{ stdenv, pkgs }:
{
  buildChromiumExtension = args @ {
    name ? "${args.pname}-${args.version}",
    namePrefix ? "chromium-extension-",
    src ? "",
    unpackPhase ? "",
    configurePhase ? "",
    buildPhase ? "",
    preInstall ? "",
    postInstall ? "",
    ...
  }:
    stdenv.mkDerivation(args // {
      name = namePrefix + name;

      inherit configurePhase buildPhase preInstall postInstall;

      installPhase = ''
        runHook preInstall

        mkdir -p $out/lib
        cp -r . $out/lib

        runHook postInstall
      '';

      doInstallCheck = true;
      installCheckPhase = ''
        test -e $out/lib/manifest.json || (echo "INVALID EXTENSION: missing manifest.json" && exit 1)
      '';

      # Filter out "key" and "update_url" entries from manifest.json
      fixupPhase = ''
        tmpmanifest=$(mktemp)
        ${stdenv.lib.getBin pkgs.jq}/bin/jq \
          'with_entries(.|select((.key != "key") and (.key != "update_url")))' \
          $out/lib/manifest.json >$tmpmanifest
        mv $tmpmanifest $out/lib/manifest.json
      '';
    });
}
