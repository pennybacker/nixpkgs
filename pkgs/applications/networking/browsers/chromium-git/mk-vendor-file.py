#!/usr/bin/env nix-shell
#!nix-shell -i python -p python2 nix git nix-prefetch-git

from __future__ import print_function

import argparse
import json
import os
import re
import shutil
import string
import subprocess
import sys

BASEDIR = "/tmp/z"

SKIP_DEPS = [ "src" ]

def hash_path(path):
    sha256 = subprocess.check_output(["nix", "hash-path", "--base32", "--type", "sha256", path]).strip()
    if re.match(r'[0-9a-z]{52}', sha256) == None:
        raise ValueError('bad hash %s' % sha256)
    return sha256

def checkout_git(url, rev, path):
    subprocess.check_call([
        "nix-prefetch-git",
        "--builder",
        "--url", url,
        "--out", path,
        "--rev", rev,
        "--fetch-submodules"])
    return hash_path(path)

def nix_str_git(path, dep):
    return '''  %(path)-90s = fetchgit { url = %(url)-128s; rev = "%(rev)s"; sha256 = "%(sha256)s"; };\n''' % {
        "path": '"' + path + '"',
        "url": '"' + dep["url"] + '"',
        "rev": dep["rev"],
        "sha256": dep["sha256"],
    }

def make_vendor_file(chromium_version, target_os):
    topdir = os.path.join(BASEDIR, chromium_version)
    if not os.path.isdir(topdir):
        os.mkdir(topdir)

    # first checkout depot_tools for gclient.py which will help to produce list of deps
    if not os.path.isdir(os.path.join(topdir, "depot_tools")):
        checkout_git("https://chromium.googlesource.com/chromium/tools/depot_tools",
                     "fcde3ba0a657dd3d5cac15ab8a1b6361e293c2fe",
                     os.path.join(topdir, "depot_tools"))

    # Import gclient_eval from the just fetched sources
    sys.path.append(os.path.join(topdir, "depot_tools"))
    import gclient_eval

    # Not setting target_cpu, as it's just used to run script fetching sysroot, which we don't use anyway
    target_cpu = []
    # Normally set in depot_tools/gclient.py
    builtin_vars={
        'checkout_android': 'android' in target_os,
        'checkout_chromeos': 'chromeos' in target_os,
        'checkout_fuchsia': 'fuchsia' in target_os,
        'checkout_ios': 'ios' in target_os,
        'checkout_linux': 'unix' in target_os,
        'checkout_mac': 'mac' in target_os,
        'checkout_win': 'win' in target_os,

        'checkout_arm': 'arm' in target_cpu,
        'checkout_arm64': 'arm64' in target_cpu,
        'checkout_x86': 'x86' in target_cpu,
        'checkout_mips': 'mips' in target_cpu,
        'checkout_mips64': 'mips64' in target_cpu,
        'checkout_ppc': 'ppc' in target_cpu,
        'checkout_s390': 's390' in target_cpu,
        'checkout_x64': 'x64' in target_cpu,

        'host_os': 'linux', # See _PLATFORM_MARPPING in depot_tools/gclient.py
        'host_cpu': 'x64', # See depot_tools/detect_host_arch.py. Luckily this variable is not currently used in DEPS for anything we care about
    }

    # like checkout() but do not delete .git (gclient expects it) and do not compute hash
    # this subdirectory must have "src" name for 'gclient.py' recognises it
    src_dir = os.path.join(topdir, "src")
    if not os.path.isdir(src_dir):
        os.mkdir(src_dir)
        subprocess.check_call(["git", "init"], cwd=src_dir)
        subprocess.check_call(["git", "remote", "add", "origin", "https://chromium.googlesource.com/chromium/src.git"], cwd=src_dir)
        subprocess.check_call(["git", "fetch", "--progress", "--depth", "1", "origin", "+" + chromium_version], cwd=src_dir)
        subprocess.check_call(["git", "checkout", "FETCH_HEAD"], cwd=src_dir)
    else:
        # restore topdir into virgin state
        if ("tag '%s' of" % chromium_version) in open(os.path.join(src_dir, ".git/FETCH_HEAD")).read():
            print("already at", chromium_version)
        else:
            print('git fetch --progress --depth 1 origin "+%s"' % chromium_version)
            subprocess.check_call(["git", "fetch", "--progress", "--depth", "1", "origin", "+%s" % chromium_version], cwd=src_dir)
            subprocess.check_call(["git", "checkout", "FETCH_HEAD"], cwd=src_dir)

        # and remove all symlinks to subprojects, so their DEPS files won;t be included
        subprocess.check_call(["find", ".", "-name", ".gitignore", "-delete"], cwd=src_dir)
        os.system("cd %s; git status -u -s | grep -v '^ D ' | cut -c4- | xargs --delimiter='\\n' rm" % src_dir);
        subprocess.check_call(["git", "checkout", "-f", "HEAD"], cwd=src_dir)

    deps = {}
    need_another_iteration = True
    while need_another_iteration:
        need_another_iteration = False

        subprocess.check_call(["python2", "depot_tools/gclient.py", "config", "https://chromium.googlesource.com/chromium/src.git"], cwd=topdir)
        flat = subprocess.check_output(["python2", "depot_tools/gclient.py", "flatten", "--pin-all-deps"], cwd=topdir)

        content = gclient_eval.Parse(flat, validate_syntax=True, filename='DEPS',
                             vars_override={}, builtin_vars=builtin_vars)

        merged_vars = dict(content['vars'])
        merged_vars.update(builtin_vars)

        for path, fields in content['deps'].iteritems():
            # Skip these
            if path in SKIP_DEPS:
                continue

            # Skip dependency if its condition evaluates to False
            if 'condition' in fields and not gclient_eval.EvaluateCondition(fields['condition'], merged_vars):
                continue

            if not path in deps:
                if fields['dep_type'] == "git":
                    url, rev = fields['url'].split('@')
                    wholepath = os.path.join(topdir, path)
                    memoized_path = os.path.join(BASEDIR, rev)

                    if os.path.exists(memoized_path + ".sha256"): # memoize hash
                        sha256 = open(memoized_path + ".sha256").read()
                    else:
                        shutil.rmtree(memoized_path, ignore_errors=True)
                        sha256 = checkout_git(url, rev, memoized_path)
                        open(memoized_path + ".sha256", "w").write(sha256)

                    if path != "src":
                        shutil.rmtree(wholepath, ignore_errors=True)
                        if not os.path.isdir(os.path.dirname(wholepath)):
                            os.mkdir(os.path.dirname(wholepath))
                        #shutil.copytree(memoized_path, wholepath, copy_function=os.link) # copy_function isn't available in python 2
                        subprocess.check_call(["cp", "-al", memoized_path, wholepath])

                    if os.path.exists(os.path.join(memoized_path, "DEPS")): # Need to recurse
                        need_another_iteration = True

                    deps[path] = {
                        "url": url,
                        "rev": rev,
                        "sha256": sha256,
                        "dep_type": "git",
                    }

                elif fields['dep_type'] == "cipd":
                    pass # Left unimplemented in nixpkgs for simplicity. Ping danielfullmer if it is needed

                else:
                    raise ValueError("Unrecognized dep_type", fields['dep_type'])

    with open('vendor-%s.nix' % chromium_version, 'w') as vendor_nix:
        vendor_nix.write("# GENERATED BY 'mk-vendor-file.py %s' for %s\n" % (chromium_version, ", ".join(target_os)))
        vendor_nix.write("{fetchgit, fetchurl, runCommand}:\n");
        vendor_nix.write("{\n");

        for path, dep in sorted(deps.iteritems()):
            if dep['dep_type'] == "git":
                vendor_nix.write(nix_str_git(path, dep))

        # Some additional non-git sources
        for path, name in [("src/third_party/node/node_modules", "chromium-nodejs"),
                        ("src/third_party/test_fonts/test_fonts", "chromium-fonts")]:
            sha1 = open(os.path.join(topdir, path + ".tar.gz.sha1")).read().strip()
            vendor_nix.write(
'''
"%(path)s" = runCommand "download_from_google_storage" {} ''
    mkdir $out
    tar xf ${fetchurl {
                url  = "https://commondatastorage.googleapis.com/%(name)s/%(sha1)s";
                sha1 = "%(sha1)s";
            }} --strip-components=1 -C $out
'';
''' % { "path": path, "name": name, "sha1": sha1 })

        vendor_nix.write("}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-os', type=str, default=["unix"], action='append')
    parser.add_argument('version', nargs='+')
    args = parser.parse_args()

    for chromium_version in args.version:
        make_vendor_file(chromium_version, args.target_os)

if __name__ == "__main__":
    main()
