# JDCloud RE-SS-01 干净固件

独立工作流：Build JDCloud RE-SS-01 clean PassWall。
官方 ImmortalWrt 源码及 feeds 的提交锁定在 source.json 和 feeds.conf。

目标为 qualcommax/ipq60xx、jdcloud_re-ss-01，SquashFS sysupgrade 镜像。
内置中文 LuCI、PassWall、Xray、Sing-box 和匹配的内核依赖。
保留上游无线、有线网络驱动及升级机制，不加入第三方加速补丁。
不预置代理节点、订阅、管理员密码或无线密码。
全新配置的管理地址为 192.168.10.251，用户名 root；首次使用自行设置密码。
软件包管理器为 APK。旧版 opkg 软件包不可直接安装到新版。

工作流缓存下载源码与 ccache，并保存匹配软件包、完整配置、日志和 SHA256SUMS。
只有编译及镜像校验均成功才生成 clean 产物；unvalidated 产物不能视为可刷固件。

当前仅完成编译准备及旧系统只读核对；产物未经本机实际启动验证。
刷机前必须备份配置、核对分区和镜像兼容性，并用当前系统的 sysupgrade -T 检查。
不能把 UFI003 固件用于本设备，也不能用 initramfs 镜像代替日常 sysupgrade 镜像。
跨版本迁移配置应另行检查，避免直接覆盖新版所有系统文件。
