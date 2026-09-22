# JDCloud RE-SS-01 干净固件

独立工作流：Build JDCloud RE-SS-01 clean PassWall。
官方 ImmortalWrt 源码及 feeds 的提交锁定在 source.json 和 feeds.conf。

目标为 qualcommax/ipq60xx、jdcloud_re-ss-01，SquashFS sysupgrade 镜像。
内置中文 LuCI、PassWall、Xray 26.9.9、Sing-box、原版 Hysteria 2.7.0 和匹配的内核依赖。
包含 kmod-fs-f2fs、mkf2fs、f2fsck，供 eMMC 配置存储初始化与挂载。
新配置默认使用 Sing-box DNS。Xray 源码版本和 SHA-256 在 build.py 中固定，兼容当前 PassWall。
保留上游无线、有线网络驱动及升级机制，不加入第三方加速补丁。
不预置代理节点、订阅、管理员密码或无线密码。
全新配置的管理地址为 192.168.10.251，用户名 root；首次使用自行设置密码。
软件包管理器为 APK。旧版 opkg 软件包不可直接安装到新版。

工作流缓存下载源码与 ccache，并保存匹配软件包、完整配置、日志和 SHA256SUMS。
只有编译及镜像校验均成功才生成 clean 产物；unvalidated 产物不能视为可刷固件。

首版实机发现缺少 F2FS 初始化工具/驱动以及 Xray 与 PassWall 版本不匹配，本次构建修复这两项。
新版仍需编译产物检查、实机启动及重启后配置持久化验证。
刷机前必须备份配置、核对分区和镜像兼容性，并用当前系统的 sysupgrade -T 检查。
不能把 UFI003 固件用于本设备，也不能用 initramfs 镜像代替日常 sysupgrade 镜像。
跨版本迁移配置应另行检查，避免直接覆盖新版所有系统文件。
