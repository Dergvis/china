const I18N = {
  en: {
    landing: 'Open Tourist Card',
    ocr: 'Passport OCR',
    liveness: 'Liveness',
    address: 'Address',
    docs: 'Documents',
    sms: 'SMS e-sign',
    card: 'RF Card',
    funding: 'Bind CNY',
    topup: 'Top-up',
    qr: 'Pay by QR'
  },
  zh: {
    landing: '开通旅游卡',
    ocr: '护照识别',
    liveness: '活体检测',
    address: '地址',
    docs: '文件同意',
    sms: '短信签署',
    card: '俄罗斯卡',
    funding: '绑定CNY卡',
    topup: '充值',
    qr: '扫码支付'
  }
};

function t(lang, key) {
  return (I18N[lang] && I18N[lang][key]) || key;
}

function request(apiBase, path, method = 'GET', data = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase}${path}`,
      method,
      data,
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data);
        reject(res.data || { error: `HTTP ${res.statusCode}` });
      },
      fail: reject
    });
  });
}

App({
  onLaunch() {
    try {
      const saved = wx.getStorageSync('API_BASE');
      if (saved) this.globalData.apiBase = saved;
      const demo = wx.getStorageSync('ALLOW_LOCAL_MOCK_OCR');
      this.globalData.allowLocalMockOcr = Boolean(demo);
    } catch (e) {}
  },
  globalData: {
    apiBase: '',
    showApiConfig: false,
    allowLocalMockOcr: false,
    t,
    setApiBase(nextBase) {
      this.apiBase = nextBase;
      try { wx.setStorageSync('API_BASE', nextBase); } catch (e) {}
    },
    setAllowLocalMockOcr(nextValue) {
      this.allowLocalMockOcr = Boolean(nextValue);
      try { wx.setStorageSync('ALLOW_LOCAL_MOCK_OCR', this.allowLocalMockOcr); } catch (e) {}
    },
    api(path, method = 'GET', data = {}) {
      return request(this.apiBase, path, method, data);
    }
  }
});
