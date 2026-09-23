'use strict';
'require baseclass';
'require fs';

var thermalPath = '/sys/class/thermal';
var labels = {
	'cpu0-1-thermal': 'CPU 0–1',
	'cpu2-3-thermal': 'CPU 2–3',
	'modem-thermal': '调制解调器',
	'gpu-thermal': 'GPU',
	'pm8916-thermal': '电源管理芯片（PM8916）',
	'camera-thermal': 'SoC（camera-thermal）'
};
var order = Object.keys(labels);

return baseclass.extend({
	title: '设备温度',
	load: function() {
		return L.resolveDefault(fs.list(thermalPath), []).then(function(entries) {
			return Promise.all(entries.filter(function(entry) {
				return /^thermal_zone\d+$/.test(entry.name);
			}).map(function(entry) {
				var path = thermalPath + '/' + entry.name;
				return Promise.all([
					L.resolveDefault(fs.read(path + '/type'), ''),
					L.resolveDefault(fs.read(path + '/temp'), '')
				]).then(function(values) {
					var raw = values[1].trim();
					return {
						type: values[0].trim() || entry.name,
						temperature: /^-?\d+$/.test(raw) && Number.isFinite(Number(raw))
							? Number(raw) / 1000 : null
					};
				});
			}));
		});
	},
	render: function(sensors) {
		if (!sensors.length)
			return E('p', {}, '未检测到可读取的温度传感器');
		var table = E('table', { 'class': 'table' });
		sensors.sort(function(a, b) {
			var ai = order.indexOf(a.type), bi = order.indexOf(b.type);
			return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi)
				|| a.type.localeCompare(b.type);
		}).forEach(function(sensor) {
			table.appendChild(E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td left', 'width': '33%' }, labels[sensor.type] || sensor.type),
				E('td', { 'class': 'td left' }, sensor.temperature == null
					? '暂不可用' : sensor.temperature.toFixed(1) + ' °C')
			]));
		});
		return table;
	}
});
