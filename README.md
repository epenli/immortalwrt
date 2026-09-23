# UF1003 MB V02 精简固件云编译

这是 GitHub Actions 构建工程。基础版第 7 次构建已在 UF1003 MB V02 实机启动：Linux 6.18.35、APK、USB RNDIS、LuCI、Wi-Fi 和根分区扩容正常。蜂窝模块已识别，但 SIM/移动数据尚未验证。第 9 次已完成 PassWall、缓存配置和 UF1003 专用 ext4 sysupgrade 适配的编译。其位图填充问题已离线修复并重新打包，完整升级启动仍待实测。

后续升级请阅读 [UPDATE.md](UPDATE.md)。首次安装带升级适配的版本仍使用 Fastboot；之后可使用本工程专用的 ext4 sysupgrade 包。升级写入与重启恢复尚未实机验证。

## 源码与板型

- 源码：[lkiuyu/immortalwrt](https://github.com/lkiuyu/immortalwrt)，社区适配分支 `master`。
- 固定提交：`05d3cf2aff0bfc8ec0abdaf057215fc8504b378c`（2026-06-23，当次检查时该分支的最新提交）。
- 目标：`msm89xx/msm8916`；配置：`openstick-ufi003`；源码设置的内核系列：6.18。
- 该配置继承 UFI001C 设备树 `msm8916-thwc-ufi001c`，并选择 UFI003 的基带、WCNSS 和 Wi-Fi NV 固件。
- 现有设备恰好也是 `thwc,ufi001c` 设备树加 UFI003 固件包。这是选用候选配置的依据，不等同于新内核已适配验证。
- 这是较新的 **ImmortalWrt 社区开发版候选方案**，不是 OpenWrt 官方稳定版，也不声称比所有其他分支更新。

上游配置依据：[设备配置](https://github.com/lkiuyu/immortalwrt/blob/05d3cf2aff0bfc8ec0abdaf057215fc8504b378c/target/linux/msm89xx/image/msm8916.mk)、[内核配置](https://github.com/lkiuyu/immortalwrt/blob/05d3cf2aff0bfc8ec0abdaf057215fc8504b378c/target/linux/msm89xx/Makefile)。

## 保留的功能

- LuCI 管理界面、简体中文、防火墙、DHCP/DNS、SSH、IPv6。
- 4G：ModemManager、QRTR、rmtfs、上游棒子初始化服务和 UFI003 基带固件。
- Wi-Fi：wcn36xx 与相应固件。
- USB 默认使用 NCM 网卡，关闭 RNDIS、ECM 和 ADB 端点；保留配置升级时沿用原来的 USB 设置。
- PassWall（非 PassWall2）及中文界面，包含 Xray 和 sing-box 客户端引擎与所需内核模块；不预设订阅或节点，不默认启用代理。
- 上游 `openstick-tweaks`、`gc`、`rootfs-resizer` 等硬件支持依赖。ADB 程序因上游依赖仍可能打包，但自定义默认设置关闭 ADB USB 端点。

不主动选择 Docker、Alist、Passwall2、Samba、ZeroTier、DDNS-Go、网页终端等附加应用。保留 OpenWrt/ImmortalWrt 的基础包与设备默认依赖，并非删除一切非 LuCI 包。

自定义内容包括板型与软件包、默认地址 192.168.31.1、主机名和中文界面、关闭 ADB 端点、移除上游硬编码 DNS，以及注释官方未发布的 msm89xx/openstick/video 软件源。无线固件仍包含硬件必需的二进制文件，“干净”不代表完全没有闭源固件。

## 上传与运行

1. 在 GitHub 新建一个仓库。按你的账户条件确认 Actions 可用；私有仓库的运行和存储受账户额度影响。
2. 将这个目录的**内容**放到仓库根目录，包括隐藏目录 `.github`。不要把外层 `ufi-build` 目录整体嵌套进去。可以使用 GitHub Desktop 或 git 保证隐藏目录也上传。
3. 确认仓库里存在 `.github/workflows/build.yml`，以及 `config.seed`、`feeds.conf`、`source.json`、`scripts/`、`files/`。
4. 打开仓库的 **Actions → Build UFI clean firmware → Run workflow**。
5. 等待运行结束，在该次运行页面下载 `ufi003-clean-运行编号`。如果失败，下载 `ufi003-build-logs-运行编号` 诊断。

工作流只允许手动触发；不会自动发布 Release，也不会连接或刷写你的棒子。无须填写棒子密码、SSH 密钥或 GitHub PAT。构建只使用公开源码与 GitHub 提供的只读令牌。

首次全量编译可能需要数小时，具体时间取决于 Runner 和下载速度。本工作流设定 350 分钟超时；不保证在该时间内完成。产物和日志保留 14 天，请及时下载。

## 下载后有什么

- `firmware/`：该目标生成的 `*ufi003*boot.img`、`*ufi003*system.img` 、专用 `*-ext4-sysupgrade.bin` 及清单等。
- `packages/`：这次编译产生的匹配软件包（若生成）。
- `source.json`、`feeds.conf`、`feed-commits.txt`：固定与实际源码版本。
- `expanded.config`、`diffconfig`：完整配置和最小配置。
- `SHA256SUMS`：下载后用于核对文件完整性。

成功编译仅代表构建通过，仍需检查分区、启动格式和硬件工作状态。专用 sysupgrade 包包含 boot 和压缩原始 ext4，带校验与 fwtool 元数据；仅用于已安装本工程升级脚本且分区完全匹配的 UF1003。 上游的 `system.img` 使用 Android sparse 格式，不能直接当作原始 ext4 镜像用 `dd` 写入。

当前设备 boot 分区是 `mmcblk0p12`（64 MiB），rootfs 是 `mmcblk0p14`（约 3.33 GiB），本配置的初始 ext4 镜像大小为 512 MiB。上游 `rootfs-resizer` 会在首次启动尝试扩容并重启；基础版第 7 次构建已验证扩容启动。不要为了套用其他型号教程而重写 GPT 或 bootloader。

## 首次启动与配置

构建文件没有写入个人密码、SIM 信息或现有配置。默认 LAN 地址 `192.168.31.1`，主机名 `UFI-Clean`；实际以启动结果为准。首次通过 USB 管理，设置管理员密码，再配置 Wi-Fi 密码和运营商 APN。Wi-Fi 驱动被编入，不代表热点会默认开启。

硬编码公共 DNS 已去除，正常使用 DHCP/运营商提供的 DNS。不要把不匹配的其他目标软件源或滚动更新的内核模块强行装入此固件；保留本次构建的软件包。

## 更新源码

当前所有源码和 feeds 固定到完整提交，避免每次运行默默换版本。若想跟进新版本，更新 `source.json` 和 `feeds.conf` 中的提交后重新编译、核对。

设备源码最后更新时间与各 feed 不同，仍可能出现构建接口不兼容。工作流会先运行 `make defconfig`，检查关键包是否被保留，失败就停止；这不能替代真正的全量编译。仓库默认分支有变化时，不应仅因名称相同就认定还兼容这块板。

## 本地备份

设备备份放在构建目录之外的 `ufi-backup` 目录，不在这个可上传工程中。备份包含配置和设备专属基带/NV 数据，请仅本地保存。不要把整个父目录上传到 GitHub。

本机已保存旧系统 p1-p13、磁盘头尾、eMMC boot 区，以及完整 p14 在线镜像和校验清单。在线备份不能当作离线一致性快照。每次刷写前仍须备份当前配置；备份和个人信息不上传此仓库。

## 构建缓存

Actions 缓存 dl 下载目录与 ccache 编译对象（ccache 上限 3 GiB）。第一次建立缓存，后续构建优先恢复；源码包仍由构建系统校验散列，ccache 按编译器内容和编译输入判断是否可复用。缓存不包含设备备份、个人配置或密码。

编译失败时也尽可能保留已有编译缓存，统计写入日志的 ccache.log。缓存被回收或源码/编译器改变时会重新构建；工具链、链接和打包仍可能运行，不能承诺第二次不用 make 或固定缩短多少时间。没有缓存整个 build_dir/staging_dir，以免把旧内核模块或过期配置带入新镜像。

## 第 9 次修复后的下载

下载 [成功的重打包任务](https://github.com/epenli/ufi-clean-build/actions/runs/35686880231) 中的 `ufi003-clean-9-repacked-3`。原第 9 次构建的红色状态不会改变；不要使用原 `ufi003-unvalidated-9`。

重打包复用第 9 次已编译的内容，只补齐 inode 位图无效范围内的填充位，并逐字节验证其他区域完全不变。ext4 只读复检、Fastboot 稀疏镜像往返转换一致性和完整 SHA256SUMS 检查均通过。两种升级格式及匹配软件包保存在同一新产物中。

## 完整 PassWall 构建

内置 Hysteria 2.7.0、Xray 26.9.9、sing-box、geoview、GeoIP 和 GeoSite。新装默认 sing-box DNS，保留配置升级沿用原设置。UFI 使用 ext4 根文件系统，不套用京东云 F2FS overlay 初始化方案。云端从实际 ext4 升级镜像提取程序，检查包版本，并用 ARM64 QEMU 测试 HY2、Xray DNS 配置与 Geo 规则转换。测试成功才发布成品，不等于已完成实机刷写验证。

## 短信管理

内置 4IceG `luci-app-sms-manager` 1.0.9 和简体中文，源码固定在 `322392909e046c172f06e8dfff8a956b9ede4bbb`。入口：调制解调器 → 短信管理器。全新安装收发设备默认为 `any`，由 ModemManager 自动选择可用设备；多调制解调器场景应手动选择。默认号码前缀 +86，不包含个人短信、号码或密码。

收件箱将号码、完整时间和原始内容一致的 SIM/设备副本一对一合并显示，保留全部底层 ID；同一存储内的重复短信不合并。用户确认删除一行时会处理对应的两份副本。当前 UFI003 已验证接收和页面去重，发送、删除及新固件启动仍待实测。保留配置升级会沿用原短信设置；插件升级可能覆盖页面修复。

## 蜂窝流量与 LED

内核加入 BAM-DMUX 网络接口统计补丁，使 `wwan0` 的 RX/TX 包数和字节数供 LuCI 与 `netdev` LED 读取。LED 配置选择“网络设备活动”，设备选 `wwan0`，模式选 RX/TX。`phy0rx/phy0tx` 是 Wi-Fi 活动，`usb-gadget` 是 USB 活动。不会覆盖保留的 LED 配置，也不会操作 SIM 控制 GPIO。

补丁基于上游 v4 提案并适配 6.18.35，尚待新镜像实机验证。TX 统计的是驱动接受的包，包含延迟发送队列，并非运营商确认送达或计费流量。
