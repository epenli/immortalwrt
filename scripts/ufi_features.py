"""Install public UFI runtime features; no device credentials or personal config."""
import json
from pathlib import Path

REQUIRED_PACKAGES = {'kmod-ledtrig-netdev'}
TRIGGERS = {
    'phy0rx': ('Wi-Fi 接收流量', '无线芯片接收活动，包含 AP 和客户端。'),
    'phy0tx': ('Wi-Fi 发送流量', '无线芯片发送活动，包含 AP 和客户端。'),
    'phy0assoc': ('Wi-Fi 关联状态', '无线芯片的关联状态，不代表 DHCP 或外网可用。'),
    'phy0radio': ('Wi-Fi 无线开启', '无线芯片开启状态，不代表已连接上级热点。'),
    'usb-gadget': ('USB 通讯活动', '棒子作为 USB 设备与电脑通讯时闪烁，不区分收发。'),
    'usb-host': ('USB 主机通讯活动', '棒子作为 USB 主机连接外设时的活动；连接电脑请选 usb-gadget。'),
    'mmc0': ('内置存储读写', '内置存储读写活动。'),
    'cpu': ('CPU 活动', 'CPU 活动，不是温度或联网状态。'),
    **{f'cpu{i}': (f'CPU {i} 活动', f'第 {i} 个 CPU 核心的活动。') for i in range(4)},
}

def install(source):
    source = Path(source)
    scripts = Path(__file__).resolve().parent
    overlay = source / 'files'
    def write(path, content, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
    for trigger, (title, description) in TRIGGERS.items():
        data = json.dumps({'trigger': f'{title} ({trigger})', 'description': description,
                           'kernel': True}, ensure_ascii=False)
        write(overlay / f'www/luci-static/resources/view/system/led-trigger/{trigger}.js',
              "'use strict';\n'require baseclass';\nreturn baseclass.extend(" +
              data[:-1] + ', addFormOptions: function(s) {} });\n')
    for src, dst in [('ufi-wifi-recovery.sh', 'usr/sbin/ufi-wifi-recovery'),
                     ('ufi-wifi-recovery.init', 'etc/init.d/ufi-wifi-recovery')]:
        write(overlay / dst, (scripts / src).read_text(), 0o755)
    write(overlay / 'etc/uci-defaults/zz-ufi-wifi-recovery',
          '#!/bin/sh\n/etc/init.d/ufi-wifi-recovery enable\nexit 0\n', 0o755)
    # This pinned fork has no netdev trigger package, unlike older OpenWrt trees.
    write(source / 'package/kernel/linux/modules/ufi-leds.mk', '''define KernelPackage/ledtrig-netdev
  SUBMENU:=LED modules
  TITLE:=LED network device trigger
  KCONFIG:=CONFIG_LEDS_TRIGGER_NETDEV
  FILES:=$(LINUX_DIR)/drivers/leds/trigger/ledtrig-netdev.ko
  AUTOLOAD:=$(call AutoProbe,ledtrig-netdev)
endef

$(eval $(call KernelPackage,ledtrig-netdev))
''')
    config = source / '.config'
    with config.open('a') as stream:
        stream.write('\n# UFI LED network interface link/RX/TX support\n')
        for package in sorted(REQUIRED_PACKAGES):
            stream.write(f'CONFIG_PACKAGE_{package}=y\n')
