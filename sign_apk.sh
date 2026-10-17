#!/usr/bin/env bash
# Alinea y firma el APK. Con SIGNING_PASSWORD usa una clave propia y persistente
# (guardada cifrada en keystore/), así las versiones nuevas se instalan ENCIMA de las viejas.
set -euo pipefail

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
[ -n "$SDK" ] || { echo "No encuentro el Android SDK"; exit 1; }
BT="$SDK/build-tools/$(ls "$SDK/build-tools" | sort -V | tail -1)"

UNSIGNED="$(ls build/proj/android/app/build/outputs/apk/release/*.apk | head -1)"
OUT="build/out/${APK_NAME:?}"
KS="build/signing.jks"
mkdir -p build/out keystore

if [ -n "${SIGNING_PASSWORD:-}" ]; then
  if [ -f keystore/signing.jks.enc ]; then
    echo "Usando la clave de firma guardada."
    openssl enc -d -aes-256-cbc -pbkdf2 -in keystore/signing.jks.enc -out "$KS" -pass env:SIGNING_PASSWORD \
      || { echo "bad decrypt: la contraseña SIGNING_PASSWORD no coincide con la clave guardada"; exit 1; }
  else
    echo "Creando una clave de firma nueva (se guarda cifrada en el repositorio)."
    keytool -genkeypair -keystore "$KS" -alias apkfactory -keyalg RSA -keysize 2048 -validity 36500 \
      -storepass "$SIGNING_PASSWORD" -keypass "$SIGNING_PASSWORD" -dname "CN=APK Factory, O=Personal"
    openssl enc -aes-256-cbc -pbkdf2 -salt -in "$KS" -out keystore/signing.jks.enc -pass env:SIGNING_PASSWORD
  fi
  export KSPASS="$SIGNING_PASSWORD"
else
  echo "AVISO: sin SIGNING_PASSWORD se usa una clave temporal. Para actualizar sobre una versión ya instalada hay que desinstalarla antes."
  keytool -genkeypair -keystore "$KS" -alias apkfactory -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass android -keypass android -dname "CN=APK Factory Temp"
  export KSPASS="android"
fi

"$BT/zipalign" -f -p 4 "$UNSIGNED" build/aligned.apk
"$BT/apksigner" sign --ks "$KS" --ks-pass env:KSPASS --key-pass env:KSPASS \
  --ks-key-alias apkfactory --out "$OUT" build/aligned.apk
"$BT/apksigner" verify --verbose "$OUT" | head -5
rm -f build/aligned.apk "$KS"
echo "APK firmado: $OUT ($(du -h "$OUT" | cut -f1))"
