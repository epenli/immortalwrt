# UF1003 MB V02 后续固件更新

本流程针对已经实测的 OpenStick LK1ST V0.01、14 分区布局。不要套用于其他板型或分区布局。

## 更新软件包与更新系统的区别

- `apk update` 只刷新软件包索引，不升级内核或整个固件。
- 需要新增内核模块、升级内核或更换整套固件时，重新构建并刷同次产出的 boot/rootfs。
- 内核模块必须匹配构建配置与 ABI；同一个 Linux 版本号不等于可以混装。
- 官方没有发布此社区 target/openstick/video 的匹配仓库。这三个默认源已注释；保存每次构建的 firmware/packages、packages 和校验清单。
- 不运行无选择的 `apk upgrade`，不强制忽略内核包依赖。

## 1. 先备份当前配置

在 LuCI 的“系统 → 备份/升级”导出备份并下载到电脑。这个页面可用于备份，但本工程的镜像不能作为 sysupgrade 固件上传。

也可通过 SSH 执行 `sysupgrade -b /tmp/ufi-config-backup.tar.gz`，然后将文件下载到电脑。先检查压缩包能读取、包含所需网络/Wi-Fi/防火墙和 PassWall 配置。节点与订阅是个人数据，不要上传 GitHub。

记录当前管理 IP、SSID、APN、SSH 端口和主机名。硬件关键分区/旧 rootfs 备份应单独保存。刷入 rootfs 会覆盖已安装软件与设置；配置备份不等于软件包备份。

## 2. 下载并核对新构建

从 Actions 下载成功构建的 `ufi003-clean-编号`，解压并核对 SHA256SUMS。使用同一包中 firmware 目录的：

- `*-openstick-ufi003-ext4-boot.img`
- `*-openstick-ufi003-ext4-system.img`

工作流已解压 `.img.gz` 并校验 Android/sparse 头和容量。不要混用不同构建的 boot 与 system。system.img 是 Android sparse 格式，不能用 dd 直接写入。

## 3. 从当前系统进入 Fastboot

ADB 在新固件中默认关闭。在 SSH 中按需临时开启（USB 网卡会短暂断开）：

```sh
uci set gc.config.adb='1'
uci commit gc
/etc/init.d/gc restart
```

电脑上运行 `adb devices`，确认唯一目标设备，再运行 `adb -s <ADB序列号> reboot bootloader`。此进入方式已在旧系统实测成功，新系统再次进入的完整路径仍应在刷写前验证。

Windows 要区分两种驱动：正常系统的父设备用 USB Composite Device，子接口分别用 RNDIS/ADB；Fastboot 模式用 Android Bootloader Interface。不要把整个正常运行的复合设备绑定成 ADB。

## 4. 核对分区后刷写

在 platform-tools 目录执行：

```powershell
.\fastboot.exe devices
.\fastboot.exe -s <Fastboot序列号> getvar partition-size:boot
.\fastboot.exe -s <Fastboot序列号> getvar partition-size:rootfs
```

这块设备实测 boot = 0x4000000（64 MiB），rootfs = 0xd4dfbe00（3,571,432,960 字节）。实际操作时将占位符替换为上一步返回的设备序列号。容量或分区不符时停止核对。

将已校验的新镜像分别复制为命令所在目录的 boot.img、system.img 后，逐条执行：

```powershell
.\fastboot.exe -s <Fastboot序列号> flash rootfs .\system.img
.\fastboot.exe -s <Fastboot序列号> flash boot .\boot.img
.\fastboot.exe -s <Fastboot序列号> reboot
```

必须每条返回 OKAY 才执行下一条。system.img 对应 rootfs 分区，不是 system 分区。不要额外 erase，不修改 GPT、aboot、devinfo 或基带 NV。首次实测 rootfs 写入约 192 秒，等待期间不要断电。

## 5. 检查新系统并恢复配置

首次启动可能自动扩容并重启，预期通过 USB 访问 192.168.1.1。先核对内核版本、根分区容量、USB、LuCI 和无线设备，再恢复兼容配置。

同分支的小幅更新可恢复配置备份，但必须先查看备份内容；跨版本建议选择性恢复网络、无线、防火墙和 PassWall 设置。不要用旧系统文件覆盖新内核、模块、APK 数据库/签名密钥或软件源。恢复网络后管理 IP 可能切回备份中的地址。

设置管理员密码和 Wi-Fi 加密，检查蜂窝 SIM/APN。PassWall 需要用户提供自己的节点/订阅；先验证直连网络，再启用代理。全程保留旧镜像和备份，回退时也应核对镜像格式、分区和恢复路径。
