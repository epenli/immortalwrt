'use strict';
'require baseclass';
'require fs';

var thermalPath = '/sys/class/thermal';
var labels = {
	'camera-thermal': 'SoC',
	'modem-thermal': '调制解调器',
	'pm8916-thermal': '电源管理芯片'
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
		var table = E('table', { 'class': 'table' });
		order.forEach(function(type) {
			var sensor = sensors.find(function(item) { return item.type === type; })
				|| { type: type, temperature: null };
			table.appendChild(E('tr', { 'class': 'tr' }, [
				E('td', { 'class': 'td left', 'width': '33%' }, labels[sensor.type] || sensor.type),
				E('td', { 'class': 'td left' }, sensor.temperature == null
					? '暂不可用' : sensor.temperature.toFixed(1) + ' °C')
			]));
		});
		return table;
	}
});
