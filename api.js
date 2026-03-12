function request(path, method = 'GET', data = {}) {
  const app = getApp();
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBase}${path}`,
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

const api = {
  getOffer: (lang) => request(`/docs/offer?lang=${lang}`),
  getPdConsent: (lang) => request(`/docs/pd-consent?lang=${lang}`),
  ocr: (data) => request('/kyc/ocr', 'POST', data),
  livenessStart: (data) => request('/kyc/liveness/start', 'POST', data),
  livenessFinish: (data) => request('/kyc/liveness/finish', 'POST', data),
  submitKyc: (data) => request('/kyc/submit', 'POST', data),
  acceptDoc: (data) => request('/docs/accept', 'POST', data),
  smsSend: (data) => request('/pep/sms/send', 'POST', data),
  smsVerify: (data) => request('/pep/sms/verify', 'POST', data),
  createCard: (data) => request('/rf-card/create', 'POST', data),
  bindCny: (data) => request('/cny-card/bind', 'POST', data),
  topup: (data) => request('/topup', 'POST', data),
  qrParse: (data) => request('/qr/parse', 'POST', data),
  payConfirm: (data) => request('/payment/confirm', 'POST', data),
  exportUser: (userId) => request(`/export/user/${userId}.json`)
};

module.exports = { api };
