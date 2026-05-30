$ErrorActionPreference = "Stop"

function Run-Step([scriptblock]$Step, [string]$Name) {
    & $Step
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$project = Resolve-Path $PSScriptRoot
$root = Resolve-Path (Join-Path $project "..")
$tools = Join-Path $root "tools/android-build"
$env:JAVA_HOME = Join-Path $tools "jdk-17"
$env:ANDROID_HOME = Join-Path $tools "android-sdk"

$java = Join-Path $env:JAVA_HOME "bin/javac.exe"
$jar = Join-Path $env:JAVA_HOME "bin/jar.exe"
$keytool = Join-Path $env:JAVA_HOME "bin/keytool.exe"
$androidJar = Join-Path $env:ANDROID_HOME "platforms/android-35/android.jar"
$buildTools = Join-Path $env:ANDROID_HOME "build-tools/35.0.0"
$aapt2 = Join-Path $buildTools "aapt2.exe"
$d8 = Join-Path $buildTools "d8.bat"
$zipalign = Join-Path $buildTools "zipalign.exe"
$apksigner = Join-Path $buildTools "apksigner.bat"

foreach ($required in @($java, $jar, $keytool, $androidJar, $aapt2, $d8, $zipalign, $apksigner)) {
    if (-not (Test-Path $required)) {
        throw "Missing Android build tool: $required"
    }
}

$manual = Join-Path $project ("build/manual-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$compiled = Join-Path $manual "compiled.zip"
$gen = Join-Path $manual "gen"
$classes = Join-Path $manual "classes"
$dex = Join-Path $manual "dex"
New-Item -ItemType Directory -Force -Path $manual, $gen, $classes, $dex | Out-Null

Run-Step { & $aapt2 compile --dir (Join-Path $project "app/src/main/res") -o $compiled } "aapt2 compile"
Run-Step {
    & $aapt2 link `
        -o (Join-Path $manual "app-unsigned.apk") `
        -I $androidJar `
        --manifest (Join-Path $project "app/src/main/AndroidManifest.xml") `
        --java $gen `
        --min-sdk-version 23 `
        --target-sdk-version 35 `
        --auto-add-overlay `
        $compiled
} "aapt2 link"

$javaSources = @()
$javaSources += Get-ChildItem -Recurse -File (Join-Path $project "app/src/main/java") -Filter "*.java" | ForEach-Object { $_.FullName }
$javaSources += Get-ChildItem -Recurse -File $gen -Filter "*.java" | ForEach-Object { $_.FullName }
$argsFile = Join-Path $manual "javac.args"
$javaSources | Set-Content -Encoding ASCII $argsFile

Run-Step { & $java -encoding UTF-8 -source 17 -target 17 -classpath $androidJar -d $classes "@$argsFile" } "javac"
$classesJar = Join-Path $manual "classes.jar"
Run-Step { & $jar cf $classesJar -C $classes . } "jar classes"
Run-Step { & $d8 --lib $androidJar --min-api 23 --output $dex $classesJar } "d8"
Run-Step { & $jar uf (Join-Path $manual "app-unsigned.apk") -C $dex . } "jar apk"
Run-Step { & $zipalign -f 4 (Join-Path $manual "app-unsigned.apk") (Join-Path $manual "app-aligned.apk") } "zipalign"

# Reuse debug keystore from sibling project
$ks = Join-Path (Join-Path $root "mobile-native-android") "debug.keystore"
if (-not (Test-Path $ks)) {
    Run-Step {
        & $keytool -genkeypair -v `
            -keystore $ks `
            -storepass android `
            -keypass android `
            -alias androiddebugkey `
            -keyalg RSA `
            -keysize 2048 `
            -validity 10000 `
            -dname "CN=Android Debug,O=Android,C=US"
    } "keytool"
}

$outDir = Join-Path $project "app/build/outputs/apk/debug"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outApk = Join-Path $outDir "app-debug.apk"
Run-Step { & $apksigner sign --ks $ks --ks-pass pass:android --key-pass pass:android --out $outApk (Join-Path $manual "app-aligned.apk") } "apksigner sign"
Run-Step { & $apksigner verify --verbose $outApk } "apksigner verify"
Get-Item $outApk
Write-Host "`nAPK built successfully: $outApk" -ForegroundColor Green
