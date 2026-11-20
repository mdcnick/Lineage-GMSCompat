# Duress credentials on LineageOS 24.0 for lemonadep

This patch series targets Android 17 and the OnePlus 9 Pro T-Mobile LE2127. It adds duress PIN and password enrollment to Settings and connects it to the normal lockscreen credential verifier. Phase 1 is a source checkpoint. Android compilation, runtime behavior, and the device's hardware-backed erase behavior await later phases.

## Source and patch order

Apply each directory's numbered patches in order, with frameworks/base first. The upstream port commits retain GrapheneOS author attribution and Apache-2.0 licensing. The separate framework regression patch keeps the service and cryptographic wipe tests reviewable.

| Component | Patch series | Upstream source |
| --- | --- | --- |
| `frameworks/base` | [Implementation](patches/frameworks-base/0001-Add-duress-PIN-and-password-for-lemonadep.patch), [regressions](patches/frameworks-base/0002-Test-duress-verification-and-wipe-dispatch-with-mock.patch) | [GrapheneOS framework commit 0170b3e](https://github.com/GrapheneOS/platform_frameworks_base/commit/0170b3e9d957a67a7dad69cbe71aeaea8fc570d3) |
| `packages/apps/Settings` | [Configuration UI](patches/packages-apps-Settings/0001-Add-duress-password-management-UI.patch) | [GrapheneOS Settings commit 56d9f6b](https://github.com/GrapheneOS/platform_packages_apps_Settings/commit/56d9f6b6d3a5ea49afcbdbb20db787876489d8d7) |

[revisions.env](revisions.env) pins the LineageOS manifest and both patch bases. [lemonadep.xml](lemonadep.xml) adds the LE2127 device tree and its dependencies, pinned on `lineage-24.0` using the [device](https://github.com/LineageOS/android_device_oneplus_lemonadep/blob/8a129d327148b573543c9032628e23eb212c1950/lineage.dependencies) and [common](https://github.com/LineageOS/android_device_oneplus_sm8350-common/blob/34661bff0fe0d9ce4463c71f6d3b80f0b04b80d5/lineage.dependencies) dependency files. The two component pins were selected from the LineageOS 24.0 branch for the port. Keep them and the patches together when rebasing.

The service tests duress after the selected user's normal PIN or password is rejected by the synthetic-password protector. A valid real credential takes precedence. Weaver `INCORRECT_KEY`, Gatekeeper `RESPONSE_ERROR` from the normal LSKF check, and credential-type mismatch are eligible. Lockout-only responses, software rate-limit short circuits, early synthetic-password failures, FRP and repair users, and internal unified-profile credentials skip the check. Gatekeeper exposes a single error result for rejected guesses, so what the shipping HAL reports is a hardware validation item.

Only a privileged system-user caller who freshly verifies the current owner screen lock can enroll, query or delete the pair. The Binder management call itself has duress dispatch disabled. The verifier hashes a duplicate of a rejected credential with the stored, independently salted SyntheticPasswordManager scrypt parameters and clears the duplicate and temporary stretched hash. Deletion, replacement, or a change of the tested user's protector can cancel an in-flight check before the wipe commits. Removing the owner's screen lock clears the stored pair. After a match, the service calls `RecoverySystemService.deleteSecrets()` and immediately requests `PowerManagerService.lowLevelShutdown(null)`. This uses the existing KeyMint and optional Secretkeeper deletion path. The LE2127 adaptation excludes eSIM operations and the upstream test-only shutdown delay.

In Settings, use **Security & privacy → Device unlock → Duress password**, or **Display & touch → Lock screen → Duress password** with legacy or disabled Safety Center. The two protected activities require native owner lock confirmation. Keyguard submits credentials in the active input mode. A PIN keypad sends a PIN, a password field sends a password, and a pattern screen sends a pattern. Exercise both PIN and password screen-lock configurations for full coverage.

## Goal workflow and acceptance

Keep one active native goal per authorized phase. Before starting a phase, check the native goal state and create a new goal for that phase if none is active. Complete a goal after the phase's acceptance checks pass. If usage limits or an external dependency stop work, record the branch and commit or PR, commands and results, cached inputs or artifacts, and the exact next step here before handing off. If native goals are unavailable, record that in the checkpoint and continue within the authorized phase. Reuse the source and output directories across runs.

| Phase | Acceptance |
| --- | --- |
| 1. Reviewable patches | Exact-base replay of both components, focused syntax and integration-anchor checks, provenance and handoff in Git, and a review PR. |
| 2. Integration | Full source workspace synced, resolved manifest recorded, patches applied cleanly, framework and Settings built, and focused tests pass on the host or an Android 17 disposable emulator. |
| 3. Signed image | Build and sign the LE2127 target. Record the source manifest, artifact hashes, package metadata, and signing verification. |
| 4. Hardware validation | After separate explicit authorization, flash a disposable or freshly wiped test installation and complete the validation plan below. The connected production phone is outside this work. |

## Phase 1 checkpoint

Feature branch on Nick's fork is [`feature/lineage24-lemonadep`](https://github.com/mdcnick/Lineage-GMSCompat/tree/feature/lineage24-lemonadep). The next authorized phase starts at the source integration commands below.

Patch replay and whitespace checks passed against exact touched blobs from both pinned repositories. JDK 21 parsed 15 Java files and the verifier parsed five downstream XML files. It checked the framework Binder endpoints, normal-verification ordering, KeyMint/shutdown call sites and the two Settings activities' manifest permissions. These are static checks. The Android regression tests in the framework patch cover accepted credentials taking precedence, real-verifier rejection versus throttle/error, management authorization, PIN and password match/non-match, validation, deletion, and mock wipe/shutdown ordering.

To rerun, use Git, Python 3, and JDK 21. The verifier fetches only the two component trees and the Git blobs touched by the patches. It reuses the cache on later runs.

```bash
python3 ports/lineage-24.0/lemonadep-duress/verify.py --java /path/to/jdk-21/bin/java
```

## Phase 2 integration and focused tests

This machine has the small patch repository and a SHA-256-verified November 2 official `lemonadep` OTA. It has no initialized Android source workspace, `repo`, or Git LFS on PATH as of Phase 1. Prepare a Linux x86-64 build environment using the device guide, with the required packages and enough disk for the shared Phase 2 and Phase 3 tree. Install Repo and Git LFS before the commands below. The device makefiles, kernel and supporting HAL trees are included by the port's local manifest. Proprietary vendor files still need extraction from an official OTA. [LineageOS LE2127 build guide](https://wiki.lineageos.org/devices/lemonadep/build/variant2/), [extracting blobs from an OTA](https://wiki.lineageos.org/extracting_blobs_from_zips/).

Run this once in a new build workspace. On continuation, reuse the checkout and skip initialization and replay steps already confirmed.

```bash
port="$HOME/Projects/code-workspace-starter/code-workspace/projects/lineage-gmscompat/ports/lineage-24.0/lemonadep-duress"
workspace="$HOME/android/lineage-24.0-lemonadep-duress"

source "$port/revisions.env"
mkdir -p "$workspace"
cd "$workspace"
repo init -u https://github.com/LineageOS/android.git -b "$LINEAGE_BRANCH" --git-lfs
git -C .repo/manifests checkout --detach "$LINEAGE_MANIFEST_REV"

mkdir -p .repo/local_manifests
cp "$port/lemonadep.xml" .repo/local_manifests/duress-lemonadep-device.xml
cat > .repo/local_manifests/duress-source-pins.xml <<EOF_MANIFEST
<manifest>
    <extend-project name="LineageOS/android_frameworks_base" path="frameworks/base"
        revision="$FRAMEWORKS_BASE_REV" upstream="refs/heads/$LINEAGE_BRANCH" />
    <extend-project name="LineageOS/android_packages_apps_Settings" path="packages/apps/Settings"
        revision="$SETTINGS_REV" upstream="refs/heads/$LINEAGE_BRANCH" />
</manifest>
EOF_MANIFEST
repo sync -c --no-manifest-update --fail-fast -j4
repo manifest -r -o "$workspace/lineage24-lemonadep-base.xml"

test "$(git -C frameworks/base rev-parse HEAD)" = "$FRAMEWORKS_BASE_REV"
test "$(git -C packages/apps/Settings rev-parse HEAD)" = "$SETTINGS_REV"
git -C frameworks/base am --whitespace=error "$port"/patches/frameworks-base/*.patch
git -C packages/apps/Settings am --whitespace=error "$port"/patches/packages-apps-Settings/*.patch
git -C frameworks/base rev-parse HEAD
git -C packages/apps/Settings rev-parse HEAD
```

Keep the resolved base manifest and the patch repository revision. The remaining projects in LineageOS's default manifest include moving branches. The resolved manifest freezes their revisions once the first sync completes. If a patch or checkout fails, identify the actual base and refresh the patch and verifier together before building.

Extract proprietary blobs offline. The cached OTA passed the hash below. Extraction and compatibility with the pinned device trees are Phase 2 checks. If extraction reports missing or mismatched vendor files, locate a verified LineageOS 24.0 `lemonadep` OTA compatible with the device-tree revisions before continuing.

```bash
cd "$workspace"
ota="$HOME/Downloads/lineageos-lemonadep/2026-11-02/lineage-24.0-20261102-nightly-lemonadep-signed.zip"
printf '%s  %s\n' 936d26aa3096d221bbd0609fde2a6429c24cfbce7a3500ed0b281435f2f181 "$ota" \
    | sha256sum -c -
(cd device/oneplus/lemonadep && ./extract-files.py "$ota")

source build/envsetup.sh
breakfast lemonadep userdebug
m -j8 services Settings

service_gate_tests='FrameworksServicesTests:LockSettingsServiceTests#duressIsCheckedOnlyAfterWeaverRejectsCredential,duressIsCheckedAfterGatekeeperRejectsCredential,duressIsSkippedWhenWeaverThrottlesOrErrors,duressManagementRequiresRealOwnerCredential,duressStorageCannotBeAccessedThroughGenericBinderMethods'
atest -b FrameworksServicesTests:DuressPasswordHelperTest "$service_gate_tests"
atest SettingsRoboTests:DeviceUnlockSubpageFragmentTest
```

Run the instrumentation tests on an Android 17 emulator whose framework includes these patches. The tests use fake storage or credential services and mock wipe actions. Reuse a compatible emulator build if one is already available. If needed, build an emulator product using `source vendor/lineage/vars/aosp_target_release`, `lunch sdk_phone64_x86_64 "$aosp_target_release" userdebug`, and `m -j8`. Confirm that product in the synced source if target names have changed. With the patched emulator running, address its serial explicitly using `atest -s "$test_emulator_serial" FrameworksServicesTests:DuressPasswordHelperTest "$service_gate_tests"`. Complete a Settings UI smoke test for both Safety Center routes, owner confirmation and cancellation, credential validation, and deletion. For the emulator smoke test, leave trigger dispatch to the mocked instrumentation tests. [AOSP Atest documentation](https://source.android.com/docs/core/tests/development/atest).

## Phase 3 signed artifact

Reuse the integrated tree and recorded manifest. Use the LineageOS signing template with private build keys, including APEX signing keys, then select `breakfast lemonadep user` and run `m -j8 bacon`. Reuse the same keys for related builds. Verify the generated OTA with the template's `check_keys.py`, test ZIP integrity, check the OTA device and build metadata, and save SHA-256 hashes for the OTA and accompanying boot/recovery artifacts. Record the build variant, source revisions, public certificate fingerprints and verification results. [LineageOS signing and verification guide](https://wiki.lineageos.org/signing_builds/).

## Phase 4 disposable hardware validation

Perform these checks only after separate explicit authorization for a disposable or freshly wiped LE2127. Use synthetic credentials and non-sensitive canaries. Keep credential values out of notes, logs, screenshots and recordings.

1. Confirm the exact LE2127 test device and signed artifact, and prepare the matching recovery and clean reinstall path. Keep the production phone disconnected from the test host.
2. Before a trigger, verify that normal unlock, cold boot, and any relevant secondary-user unlock work. Use a PIN screen lock for the PIN trial and a password screen lock for a separate password trial. Verify the owner-only Settings surface, successful enrollment, short or invalid input and confirmation mismatch, rejected owner authentication, and deletion. Check how stock PIN auto-confirm affects the permitted input length.
3. For each input mode, show that a wrong non-match and a deleted duress credential leave the device running and the canaries readable. With synthetic values, show that a duress value equal to the real credential unlocks normally, including that a throttle-only response never dispatches the wipe. A retry may be required after the normal verifier is ready.
4. For each destructive trial, start from a fresh installation with distinct real and duress credentials. Create canaries in credential-encrypted and device-encrypted storage and verify a test KeyMint-backed key can decrypt its test ciphertext. Enter the applicable duress credential through Keyguard and observe immediate low-level power-off. Record any KeyMint or Secretkeeper failures without recording credential input.
5. Before manually resetting, use the approved test recovery and access plan to determine whether the prior keys and canaries can still be recovered. Check cold boot and the former real credential. Distinguish verified key destruction from a boot failure, a later factory reset, or storage your test tools could never read in the baseline. A successful result requires evidence that pre-trigger data and hardware-backed test keys became inaccessible. Reinstall fresh for the other input mode.

The erase guarantee depends on the shipping KeyMint and storage-encryption implementation, and on the existing deletion call completing. A blocked HAL call can delay shutdown. A reported deletion failure still leads to shutdown and requires investigation. Pending hardware validation, this patch series establishes the intended code path and test plan.
