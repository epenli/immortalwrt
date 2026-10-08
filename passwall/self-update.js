        if (app === 'passwall') {
            btn.value = '正在校验并安装 APK…';
            XHR.post(appUpdateUrl, { token: tokenStr }, function (x, json) {
                removePageNotice(app);
                if (!json || json.code) {
                    appInfoList[app] = undefined;
                    onRequestError(btn, json ? json.error : '安装请求失败，请刷新后检查已安装版本', true);
                } else {
                    onUpdateSuccess(btn);
                }
            }, 300);
            return;
        }
