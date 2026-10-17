[app]
title = SIGA Operador ETA
icon.filename = assets/icone.png
package.name = sigaoperadoreta
package.domain = br.gov.saaechale

source.dir = .
source.include_exts = py,kv,png,jpg,ttf

version = 0.1

requirements = python3,kivy==2.1.0,kivymd==1.2.0,sdl2_ttf==2.0.15,pillow,requests,urllib3,chardet,idna,certifi,sqlite3

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.accept_sdk_license = True
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
