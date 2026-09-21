# 检查结果（2026-09-21）

- GitHub Actions 工作流通过 actionlint 1.7.12 检查（未调用 shellcheck / pyflakes）。
- YAML 可解析，唯一触发方式为手动 workflow_dispatch，仓库权限为 contents: read。
- Python 构建辅助脚本通过语法检查。
- 上游固定提交中的 UFI003 配置、UFI001C 设备树、6.18 内核设置及固件包定义已检查。
- 构建脚本会在云端检查展开后的 Kconfig，缺少必需包即停止；产物收集时检查 Android boot / sparse 文件头以及已知分区容量。
- 设备在线备份共 23 个清单文件，合计 118,266,521 字节；本地字节数和 SHA-256 复核通过，无线固件与配置压缩包可读取，设备树头部标识正确。

基础版第 7 次云端构建和 boot/system 镜像检查成功；已通过 Fastboot 刷入实机。Linux 6.18.35、APK 3.0.5、USB RNDIS、中文 LuCI、Wi-Fi AP/STA 和根分区扩容至 3.3 GiB 已实测。蜂窝模块识别成功，但此前报告 SIM 缺失，移动数据未验证。旧 rootfs 已补充完整在线备份（3,571,432,960 字节），不是离线一致性快照。

本次 PassWall 增量：使用原固定 LuCI feed 的 PassWall 26.9.16，加入中文包、Xray、sing-box、libatomic 和缺少的五个内核模块，展开 Kconfig 时必须保留。新增内容需重新通过云端构建和实机代理功能验证；基础版成功不代表增量已验证。


## ext4 sysupgrade 适配（待完整刷写验证）

- 新增专用 tar/fwtool 升级包：Android boot、gzip 原始 ext4、长度及 SHA256 清单；Fastboot sparse 镜像仍单独保留。
- 仅接受 thwc,ufi001c 和已观测到的 p11-p14 标签、起始扇区、容量；写入仅限 p12/p14。
- 实机只读布局校验通过，当前 ext4 根环境被写入保护拒绝；没有刷写运行中的系统。
- 使用实机 BusyBox、/tmp 测试文件和替换过的 I/O 函数，验证损坏/截断/重复成员/链接镜像拒绝，以及写入、读回、配置恢复失败会终止而不会报告完成。
- 打包阶段使用 e2fsck -fn 检查原始文件系统；运行阶段流式解压，不将 512 MiB 原始镜像存入 RAM。
- 保留配置时跳过 OpenStick 网络初始化和自定义主机名/USB/LAN 默认值；新装默认 IP 为 192.168.31.1。
- 尚未验证真实 RAM 根切换、分区写入、配置恢复后启动和断电恢复。构建通过也不等于这些项目通过。
