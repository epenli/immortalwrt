'use strict';
'require baseclass';
'require fs';
'require rpc';

var frequencies = rpc.declare({ object: 'iwinfo', method: 'freqlist', params: [ 'device' ] });
var extraTypes = [ 'nss-top-thermal', 'nss-thermal', 'wcss-phya0-thermal',
    'wcss-phya1-thermal', 'lpass-thermal', 'ddrss-top-thermal' ];
function read(path) { return L.resolveDefault(fs.read(path), ''); }
function list(path) { return L.resolveDefault(fs.list(path), []); }
function temperature(raw) {
    raw = raw.trim();
    return /^-?\d+$/.test(raw) && Number.isFinite(Number(raw)) ? Number(raw) / 1000 : null;
}
function table(rows) {
    return E('table', { 'class': 'table' }, rows.map(function(row) {
        return E('tr', { 'class': 'tr' }, [
            E('td', { 'class': 'td left', 'width': '33%' }, row.label),
            E('td', { 'class': 'td left' }, row.value == null ? '暂不可用' : row.value.toFixed(1) + ' °C')
        ]);
    }));
}
return baseclass.extend({
    title: '设备温度',
    load: function() {
        return Promise.all([
            list('/sys/class/thermal').then(function(entries) {
                return Promise.all(entries.filter(function(e) { return /^thermal_zone\d+$/.test(e.name); }).map(function(e) {
                    var path = '/sys/class/thermal/' + e.name;
                    return Promise.all([read(path + '/type'), read(path + '/temp')]).then(function(v) {
                        return { type: v[0].trim(), value: temperature(v[1]) };
                    });
                }));
            }),
            list('/sys/class/ieee80211').then(function(entries) {
                return Promise.all(entries.filter(function(e) { return /^phy\d+$/.test(e.name); }).map(function(e) {
                    var path = '/sys/class/ieee80211/' + e.name;
                    return Promise.all([
                        L.resolveDefault(frequencies(e.name), {}),
                        list(path).then(function(children) {
                            return Promise.all(children.filter(function(h) { return /^hwmon\d+$/.test(h.name); }).map(function(h) {
                                return Promise.all([read(path + '/' + h.name + '/name'), read(path + '/' + h.name + '/temp1_input')]);
                            }));
                        })
                    ]).then(function(v) {
                        var bands = Array.from(new Set((v[0].results || []).map(function(f) {
                            return f.mhz >= 2400 && f.mhz < 2500 ? '2.4' : f.mhz >= 4900 && f.mhz < 5925 ? '5' : 'other';
                        })));
                        var sensor = v[1].find(function(h) { return h[0].trim() === 'ath11k_hwmon'; });
                        return { band: bands.length === 1 ? bands[0] : null, value: sensor ? temperature(sensor[1]) : null };
                    });
                }));
            })
        ]);
    },
    render: function(data) {
        var self = this;
        function zone(type) { var s = data[0].find(function(x) { return x.type === type; }); return s ? s.value : null; }
        function radio(band) { var s = data[1].find(function(x) { return x.band === band; }); return s ? s.value : null; }
        var details = E('details', {}, [
            E('summary', { 'style': 'cursor:pointer;margin:0.5em 0' }, '更多温度（6 项）'),
            table(extraTypes.map(function(type) { return { label: type, value: zone(type) }; }))
        ]);
        details.open = !!this.detailsOpen;
        details.addEventListener('toggle', function() { self.detailsOpen = details.open; });
        return E('div', {}, [table([
            { label: 'CPU', value: zone('cpu-thermal') },
            { label: '2.4 GHz 无线', value: radio('2.4') },
            { label: '5 GHz 无线', value: radio('5') }
        ]), details]);
    }
});
