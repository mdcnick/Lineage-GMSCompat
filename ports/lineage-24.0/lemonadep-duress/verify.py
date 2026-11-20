#!/usr/bin/env python3
"""Replay the duress patches from exact Git blobs and check syntax, without an Android tree."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


PORT = Path(__file__).resolve().parent
REVISIONS = dict(
    line.split("=", 1) for line in (PORT / "revisions.env").read_text().splitlines()
)
COMPONENTS = {
    "frameworks-base": ("android_frameworks_base", REVISIONS["FRAMEWORKS_BASE_REV"]),
    "packages-apps-Settings": ("android_packages_apps_Settings", REVISIONS["SETTINGS_REV"]),
}
ANDROID = "{http://schemas.android.com/apk/res/android}"

JAVA_PARSE = """
import com.sun.source.util.JavacTask;
import java.util.Arrays;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaFileObject;
import javax.tools.ToolProvider;

class ParseJava {
    public static void main(String[] paths) throws Exception {
        var compiler = ToolProvider.getSystemJavaCompiler();
        var diagnostics = new DiagnosticCollector<JavaFileObject>();
        try (var files = compiler.getStandardFileManager(diagnostics, null, null)) {
            var task = (JavacTask) compiler.getTask(null, files, diagnostics,
                    List.of("-proc:none"), null,
                    files.getJavaFileObjectsFromStrings(Arrays.asList(paths)));
            task.parse();
        }
        boolean failed = false;
        for (var diagnostic : diagnostics.getDiagnostics()) {
            if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                System.err.println(diagnostic);
                failed = true;
            }
        }
        if (failed) System.exit(1);
    }
}
"""


def git(cwd, *args, capture=True, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check,
        stdout=subprocess.PIPE if capture else None,
    )


def component_cache(path, repository, revision):
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        git(path, "init", "-q")
        git(path, "remote", "add", "origin", f"https://github.com/LineageOS/{repository}.git")
    has_revision = git(path, "cat-file", "-e", f"{revision}^{{commit}}", check=False)
    if has_revision.returncode:
        git(path, "fetch", "--depth=1", "--filter=blob:none", "origin",
            f"{revision}:refs/port-bases/{revision}", capture=False)


def replay(component, source, revision, target):
    patches = sorted((PORT / "patches" / component).glob("*.patch"))
    if not patches:
        raise ValueError(f"No patches for {component}")

    target.mkdir()
    git(target, "init", "-q")
    git(target, "config", "user.name", "Duress patch verification")
    git(target, "config", "user.email", "duress-verification@example.invalid")
    paths = set()
    for patch in patches:
        numstat = git(target, "apply", "--numstat", str(patch)).stdout.decode()
        paths.update(line.split("\t", 2)[2] for line in numstat.splitlines())
    existing = git(source, "ls-tree", "-r", "--name-only", revision, "--", *sorted(paths))
    for path in existing.stdout.decode().splitlines():
        dest = target / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(git(source, "show", f"{revision}:{path}").stdout)

    git(target, "add", ".")
    git(target, "commit", "-qm", f"Touched files at LineageOS {revision}")
    for patch in patches:
        git(target, "apply", "--check", "--whitespace=error", str(patch))
        git(target, "am", "--whitespace=error", str(patch), capture=False)
    git(target, "diff", "--check", "HEAD~" + str(len(patches)), "HEAD")
    print(f"{component}: {len(patches)} patch(es) replayed from {revision}", flush=True)
    return [target / path for path in sorted(paths)]


def check_contract(files):
    by_name = {file.name: file for file in files}
    aidl = by_name["ILockSettings.aidl"].read_text()
    lock_utils = by_name["LockPatternUtils.java"].read_text()
    for method in ("setDuressCredentials", "hasDuressCredentials"):
        if method not in aidl or method not in lock_utils:
            raise ValueError(f"Missing framework Binder/API method {method}")

    service = by_name["LockSettingsService.java"].read_text()
    hook = service.index("if (allowDuress && authResult.lskfRejected && !response.isMatched())")
    verification = service.index("authResult =\n                        mSpManager.unlockLskfBasedProtector(")
    primary_result = service.index("reportResultToSoftwareRateLimiter(authResult.response",
                                   verification)
    if not verification < primary_result < hook:
        raise ValueError("Expected normal credential result before duress")
    wipe = by_name["DuressWipe.java"].read_text()
    for required in ("RecoverySystemService::deleteSecrets", "lowLevelShutdown(null)"):
        if required not in wipe:
            raise ValueError(f"Missing wipe action {required}")
    for name in ("EuiccWipe", "RESET_FLAG_IS_FOR_DURESS_WIPE", "SystemClock.sleep"):
        if name in wipe:
            raise ValueError(f"Unexpected wipe dependency or delay {name}")

    manifest = ET.parse(by_name["AndroidManifest.xml"])
    for screen in ("DuressPasswordMainActivity", "DuressPasswordSetupActivity"):
        activity = manifest.find(f".//activity[@{ANDROID}name='.security.{screen}']")
        if (activity is None or activity.get(ANDROID + "exported") != "false"
                or activity.get(ANDROID + "excludeFromRecents") != "true"
                or activity.get(ANDROID + "permission") !=
                "android.permission.MANAGE_SAFETY_CENTER"):
            raise ValueError(f"Missing manifest protection for {screen}")
    print("Checked duress Binder, verification and wipe anchors, and Settings manifest protections")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(
        os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
    ) / "lineage-lemonadep-duress")
    parser.add_argument("--java", default="java", help="path to the JDK 21 java executable")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="duress-verify-") as scratch:
        temp = Path(scratch)
        files = []
        for component, (repository, revision) in COMPONENTS.items():
            source = args.cache / component
            component_cache(source, repository, revision)
            files.extend(replay(component, source, revision, temp / component))

        java_files = [file for file in files if file.suffix == ".java"]
        java_parse = temp / "ParseJava.java"
        java_parse.write_text(JAVA_PARSE)
        subprocess.run([args.java, java_parse, *java_files], check=True)

        xml_files = [file for file in files if file.suffix == ".xml"]
        ET.parse(PORT / "lemonadep.xml")
        for file in xml_files:
            ET.parse(file)
        print(f"Parsed {len(java_files)} Java and {len(xml_files)} XML files")
        check_contract(files)


if __name__ == "__main__":
    main()
