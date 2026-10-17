[app]
title = SIGA Químico
package.name = sigaquimico
package.domain = br.gov.saaechale
# icon.filename = assets/icone.png   # descomente quando houver o ícone (PNG 512x512)

source.dir = .
source.include_exts = py,kv,png,jpg,ttf

version = 0.1

requirements = python3,kivy==2.1.0,kivymd==1.2.0,sdl2_ttf==2.0.15,pillow,requests,urllib3,plyer,chardet,idna,certifi

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
