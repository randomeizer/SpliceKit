#!/bin/bash
set -e

# FCPBridge Release Script
# Usage: ./release.sh <version>
# Example: ./release.sh 2.7.0

VERSION="$1"
if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh 2.8.0"
    exit 1
fi

SIGN_ID="Developer ID Application: Brian Tate (RH4U5VJHM6)"
KEYCHAIN_PROFILE="FCPBridge"
PATCHER_APP="patcher/FCPBridgePatcher.app"
ZIP_NAME="FCPBridgePatcher-v${VERSION}.zip"
ZIP_PATH="patcher/${ZIP_NAME}"
SPARKLE_SIGN="/tmp/bin/sign_update"

echo "=== FCPBridge Release v${VERSION} ==="

# Step 1: Bump version in patcher Info.plist
echo "[1/9] Bumping version to ${VERSION}..."
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${PATCHER_APP}/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${PATCHER_APP}/Contents/Info.plist"

# Step 2: Clean build the dylib
echo "[2/9] Building FCPBridge dylib..."
make clean && make

# Step 3: Copy dylib + MCP server into patcher
echo "[3/9] Embedding dylib and MCP server in patcher..."
cp build/FCPBridge "${PATCHER_APP}/Contents/Resources/FCPBridge"
cp mcp/server.py "${PATCHER_APP}/Contents/Resources/mcp/server.py"

# Step 4: Sign all Mach-O binaries individually (with runtime + timestamp)
echo "[4/9] Signing binaries..."
find "${PATCHER_APP}/Contents/Resources" -type f | while read f; do
    if file -b "$f" 2>/dev/null | grep -q "Mach-O"; then
        codesign --force --options runtime --timestamp --sign "${SIGN_ID}" "$f"
        echo "  Signed: $(basename $f)"
    fi
done

# Step 5: Sign the whole app
echo "[5/9] Signing app bundle..."
codesign --force --deep --options runtime --timestamp --sign "${SIGN_ID}" "${PATCHER_APP}"
codesign --verify --deep --strict "${PATCHER_APP}"
echo "  Verification passed"

# Step 6: Create zip
echo "[6/9] Creating zip..."
rm -f "${ZIP_PATH}"
cd patcher && ditto -c -k --keepParent FCPBridgePatcher.app "${ZIP_NAME}" && cd ..
echo "  Created: ${ZIP_PATH} ($(du -h "${ZIP_PATH}" | cut -f1))"

# Step 7: Notarize
echo "[7/9] Submitting for notarization..."
xcrun notarytool submit "${ZIP_PATH}" --keychain-profile "${KEYCHAIN_PROFILE}" --wait
echo "  Notarization accepted"

# Step 8: Staple and recreate zip
echo "[8/9] Stapling..."
xcrun stapler staple "${PATCHER_APP}"
rm -f "${ZIP_PATH}"
cd patcher && ditto -c -k --keepParent FCPBridgePatcher.app "${ZIP_NAME}" && cd ..

# Step 9: Generate Sparkle signature
echo "[9/9] Generating Sparkle EdDSA signature..."
if [ ! -f "${SPARKLE_SIGN}" ]; then
    echo "  Downloading Sparkle tools..."
    curl -sL "$(curl -s https://api.github.com/repos/sparkle-project/Sparkle/releases/latest | python3 -c "import sys,json; [print(a['browser_download_url']) for a in json.loads(sys.stdin.read())['assets'] if a['name'].endswith('.tar.xz')]")" -o /tmp/sparkle.tar.xz
    cd /tmp && tar xf sparkle.tar.xz && cd -
fi
SPARKLE_SIG=$("${SPARKLE_SIGN}" "${ZIP_PATH}")
echo "  ${SPARKLE_SIG}"

FILE_SIZE=$(stat -f%z "${ZIP_PATH}")
echo ""
echo "=== Release v${VERSION} ready ==="
echo ""
echo "Next steps:"
echo "  1. Update appcast.xml with:"
echo "     sparkle:edSignature=\"$(echo ${SPARKLE_SIG} | sed 's/.*edSignature=\"//;s/\".*//')\" length=\"${FILE_SIZE}\""
echo "  2. git add -A && git commit -m 'Release v${VERSION}'"
echo "  3. git push origin main"
echo "  4. gh release create v${VERSION} ${ZIP_PATH} --title 'v${VERSION}' --notes 'Release notes here'"
echo ""
