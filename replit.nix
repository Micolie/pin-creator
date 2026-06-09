{ pkgs }:
{
  deps = [
    pkgs.python313
    pkgs.python313Packages.pip
    pkgs.libjpeg
    pkgs.zlib
    pkgs.freetype
  ];
}
