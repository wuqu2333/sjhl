# 世纪互联 SP 管理器 Android 本机版

这个目录是独立的原生 Android 项目。当前版本不需要填写电脑服务器地址，配置、容量池、115 Open 账号、任务队列和前台传输服务都保存在手机本机。

## 当前能力

- 手机本地保存 SharePoint 应用权限配置：Tenant ID、Client ID、Client Secret、Drive ID、Root Path。
- 手机本地保存多个自动容量池，并让 SP 配置归属到指定容量池。
- 手机本地保存 115 Open accessToken / refreshToken。
- 支持填写 115 Cookie 后自动授权 CloudDrive，获取并保存 Open Token。
- 支持添加本地文件上传任务。
- 支持添加 115 Open pickCode 任务，任务执行时再获取下载链接。
- 使用 Microsoft Graph upload session 做 10 MiB 分片上传。
- 通过 Android foreground service 在后台执行传输任务。

## 仍需继续完善

- 115 Cookie 直连下载没有移植；Cookie 当前用于自动换取 CloudDrive Open Token，下载仍走 115 Open 下载链接。
- 手机端还没有移植完整的目录浏览、去重扫描、同步定时任务和多任务并发控制。
- Secret 和 Token 现在保存在 Android SharedPreferences，后续应改成 Android Keystore 加密存储。

## 构建

需要先安装 Android Studio 或 Android SDK + Gradle。

```powershell
cd mobile-native-android
gradle assembleDebug
```

APK 输出位置：

```text
mobile-native-android/app/build/outputs/apk/debug/app-debug.apk
```

本机已经安装了项目内构建工具，也可以直接运行：

```powershell
cd mobile-native-android
.\build-debug-apk.ps1
```
