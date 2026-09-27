# 独立 PassWall APK 构建

在 Actions → **Build PassWall APK packages** → **Run workflow** 启动。
一次运行分别生成 `passwall-apk-jdcloud-编号` 与 `passwall-apk-ufi-编号`。
这是 ImmortalWrt 的 APK 软件包，不是 Android 应用，也不是刷机镜像。

## 内容与版本

- PassWall 与简体中文翻译、Hysteria 2、sing-box、Xray、geoview、GeoIP/GeoSite。
- PassWall 的 DNS、转发工具及编译产生的依赖库。
- `packages/`：用户空间 APK 和本地仓库索引 `packages.adb`。
- `kernel-packages/`：单独存放的内核和 kmod APK，不要批量安装。
- `manifest.json`：每个包的版本、架构、依赖、SHA-256；另附完整配置和 feed 提交。
- `PROGRAM-CHECKS.txt`：从成品 APK 解包后，在 ARM64 模拟器中运行核心程序与 Geo 转换的结果。
- `SHA256SUMS`：整个下载包的校验清单。

沿用对应固件的 source.json、feeds.conf、配置和修补脚本。当前锁定的
PassWall 为 26.9.16，Xray 为 26.9.9；**重新运行不会自动追逐上游最新版**。
如需更新版本，应审核并更新固定的 feed 提交和兼容性修补。
构建产物不包含设备的节点、订阅、密码、SIM 信息或现机配置。

## 安装到现有固件

选择对应设备的产物，解压到有足够空间的目录。先检查：

```sh
apk --print-arch
apk list --installed luci-app-passwall
sha256sum -c SHA256SUMS
```

架构和固件来源应与 `manifest.json`、`source.json` 对应。即使两款设备均为
AArch64，也不要混装内核模块；kmod 需要与正在运行的内核版本及 ABI 完全匹配。
现有固件已集成所需 kmod 时，仅使用 `packages/`。

从解压目录执行模拟安装，确认依赖和版本变更：

```sh
apk add --simulate --allow-untrusted \
  --repository "$PWD/packages/packages.adb" \
  luci-app-passwall luci-i18n-passwall-zh-cn \
  hysteria sing-box xray-core geoview v2ray-geoip v2ray-geosite
```

检查模拟结果后，去掉 `--simulate` 再执行。该命令会同时考虑设备现有的软件源；
如要明确安装本次构建的某个版本，可指定其 APK 文件路径。
`--allow-untrusted` 用于尚未被设备信任的独立构建签名，只对这次命令生效。
不要使用强制忽略依赖，也不要执行 `apk add kernel-packages/*.apk`。
保留自己的 PassWall 配置备份；若包版本与已安装版本相同，APK 可能不做替换。
构建不会自动安装到路由器或重启网络服务。

## 构建范围和缓存

不调用整机 firmware/rootfs/image 打包目标，只编译 PassWall、所需依赖及
内核模块。因为依赖中有 kmod，仍需准备并编译匹配内核；首次运行不会瞬间完成。
沿用两路固件各自的下载、ccache 和完整工具链缓存。完整工具链只有在源码、
配置、路径和宿主依赖指纹一致时复用，不跨设备强行共用。

工作流仅在手动运行或 `passwall/`、本工作流文件变更时启动；
新增或修改这套流程不会触发原来的整机固件构建。
