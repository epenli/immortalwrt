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
PassWall 为 26.9.27，Xray 为 26.9.9；**重新运行不会自动追逐上游最新版**。
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

另外保存 Go 编译缓存（`tmp/go-build`）；Go 模块下载已在 `dl/go-mod-cache`
中，随下载缓存保存。Go 编译缓存按设备、工具链和 Go 构建配方隔离。

完整的软件包构建状态缓存包含目标/hostpkg 编译目录、对应 staging 目录和 APK
输出，只有全部源码、补丁、展开配置和工具链指纹完全一致时才复用，没有模糊回退。
PassWall 的页面、Lua 和翻译文件不参与该指纹，但其 Makefile 仍参与；命中时先
清理旧 PassWall 包和翻译 APK，再从当前源码重新编译。其他核心、依赖和内核
交给 make 根据已恢复的编译状态复用。每次仍执行全部成品校验及 QEMU 检查。
只有校验成功的状态才保存；缓存失效或被淘汰时正常重新编译。
首次启用需要建立缓存，实际提速需在后续命中时确认。

工作流每天北京时间 03:23 检查上游 PassWall 的 `PKG_VERSION`（GitHub 定时任务可能延迟）。
版本提高时自动固定对应提交及源码归档 SHA-256，提交 `passwall/source.json`，
并在同一轮工作流中构建京东云和棒子的 APK；不会依赖机器人提交再触发另一轮工作流。
如果两路更新源均已发布该版本，就跳过编译；如果之前编译或发布失败，则下次检查重试。
网络/API 错误会让检查明确失败，不会被当作“没有更新”。

手动运行也先检查，可勾选 `force_build` 强制重建。推送 `passwall/` 或本工作流修改
仍直接构建，以便发布本地修复。新增构建沿用自动取消旧任务的设置。
只有两路成品验证成功才发布；不会在路由器上自动安装，也不会启动整机固件构建。
本定时检查只跟进 PassWall 本体版本，核心组件及其他 feeds 仍使用各自固定的源码版本。

## 在 PassWall 页面更新核心

京东云和 4G Dongle 的新固件，以及本工作流生成的 PassWall APK，均集成
`component-source.lua`。原有“组件更新”的按钮操作保持不变，检查并下载
`epenli/immortalwrt` 的已验证构建。第一次成功发布之前，页面会明确提示尚无成品。
不安装计划任务，不后台自动替换核心，不修改节点、订阅或代理规则。

支持 Xray、sing-box、Hysteria、ChinaDNS-NG、Geoview；PassWall 本体通过同一页面下载并安装本工程的 APK
更新，规则数据沿用其规则更新入口。只有更新固定源码并成功发布更高程序版本，
才会显示“有更新”；同版本重建不会假装成新版本。

两个构建都通过后，独立发布任务才拥有 contents:write 权限。它将成品核心放在
`passwall-build-运行ID-重试编号` Release，随后更新 `passwall-components-jdcloud`
和 `passwall-components-ufi` 中的 components.json。清单指向具体构建的固定地址，
含版本、大小和 SHA-256；客户端下载使用 HTTPS 证书验证，替换前复核哈希和版本，
同时执行新核心检测当前系统的动态库兼容性。更新保留一份 `.passwall-previous`
备份。软件包版本记录不会因直接替换核心自动改变，以组件页面的运行版本为准。

现机适配只需备份并更新 api.lua、app_update.lua 和新增 component-source.lua；
不需要刷机。普通上游 PassWall APK 会覆盖适配，因此后续应使用本工程生成的 APK。


## PassWall 本体一键更新

顶部 PassWall “检查更新”读取本工程的已发布 APK 版本；点击“更新”通过带 CSRF
校验的 POST 请求安装对应设备的本体及中文包。下载使用 HTTPS，校验 SHA-256，
先用 APK 离线模拟安装；依赖不满足则停止，不更新系统库或内核模块。

安装前将配置与规则备份到设备 `/etc/passwall-before-apk-update.tar.gz`，并处理
26.9.27 的规则目录迁移。该备份不上传 GitHub。成功后清除版本缓存，原来正在
运行的代理服务会重启。失败时显示错误和备份路径，不宣称自动恢复全部软件包。
这里只负责用户点击更新，不设置定时安装任务。

PassWall 源码另固定在 `passwall/source.json`，不整体更新 LuCI 或所有 feeds。
