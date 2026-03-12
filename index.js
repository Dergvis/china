const DEFAULT_I18N = {
  en: { landing: 'Open Tourist Card', ocr: 'Passport OCR', liveness: 'Liveness', address: 'Address', docs: 'Documents', sms: 'SMS e-sign', card: 'RF Card', funding: 'Bind CNY', topup: 'Top-up', qr: 'Pay by QR' },
  zh: { landing: '开通旅游卡', ocr: '护照识别', liveness: '活体检测', address: '地址', docs: '文件同意', sms: '短信签署', card: '俄罗斯卡', funding: '绑定CNY卡', topup: '充值', qr: '扫码支付' }
};

function globalData() {
  try {
    return (getApp() && getApp().globalData) || {};
  } catch (e) {
    return {};
  }
}

function callApi(path, method = 'GET', data = {}) {
  const g = globalData();
  if (typeof g.api === 'function') return g.api(path, method, data);
  const apiBase = g.apiBase || 'http://127.0.0.1:8080';
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase}${path}`,
      method,
      data,
      header: { 'Content-Type': 'application/json' },
      success: (res) => (res.statusCode >= 200 && res.statusCode < 300) ? resolve(res.data) : reject(res.data || { error: `HTTP ${res.statusCode}` }),
      fail: reject
    });
  });
}

function t(lang, key) {
  const g = globalData();
  if (typeof g.t === 'function') return g.t(lang, key);
  return (DEFAULT_I18N[lang] && DEFAULT_I18N[lang][key]) || key;
}

const api = {
  getOffer: (lang) => callApi(`/docs/offer?lang=${lang}`),
  getPdConsent: (lang) => callApi(`/docs/pd-consent?lang=${lang}`),
  getProviderStatus: () => callApi('/kyc/provider/status'),
  getProviderLogs: (tail = 20) => callApi(`/kyc/provider/logs?tail=${tail}`),
  ocr: (data) => callApi('/kyc/ocr', 'POST', data),
  livenessStart: (data) => callApi('/kyc/liveness/start', 'POST', data),
  livenessFinish: (data) => callApi('/kyc/liveness/finish', 'POST', data),
  submitKyc: (data) => callApi('/kyc/submit', 'POST', data),
  acceptDoc: (data) => callApi('/docs/accept', 'POST', data),
  smsSend: (data) => callApi('/pep/sms/send', 'POST', data),
  smsVerify: (data) => callApi('/pep/sms/verify', 'POST', data),
  createCard: (data) => callApi('/rf-card/create', 'POST', data),
  bindCny: (data) => callApi('/cny-card/bind', 'POST', data),
  topup: (data) => callApi('/topup', 'POST', data),
  qrParse: (data) => callApi('/qr/parse', 'POST', data),
  payConfirm: (data) => callApi('/payment/confirm', 'POST', data),
  exportUser: (userId) => callApi(`/export/user/${userId}.json`)
};

function uid() {
  return `u_${Date.now()}`;
}


function hasOcrData(ocr) {
  if (!ocr) return false;
  return Boolean(
    (ocr.passport_number && String(ocr.passport_number).trim()) ||
    (ocr.full_name_latin && String(ocr.full_name_latin).trim()) ||
    (ocr.mrz_raw && String(ocr.mrz_raw).trim())
  );
}

function hasConfiguredApiBase() {
  const g = globalData();
  const base = String((g.apiBase || '')).trim();
  if (!base) return false;
  if (base.startsWith('http://127.0.0.1') || base.startsWith('http://localhost')) return false;
  return true;
}

function canUseLocalMockOcr() {
  const g = globalData();
  return Boolean(g.allowLocalMockOcr);
}

function mockLivenessResult() {
  return {
    liveness_passed: true,
    liveness_score: 0.93,
    liveness_vendor_session_id: `mock-${Date.now()}` ,
    created_at: new Date().toISOString(),
    provider_mode: 'miniapp-local-mock'
  };
}

function mockOcrResult() {
  return {
    document_type: 'passport',
    issuing_country: 'CN',
    full_name_latin: 'ZHANG SAN',
    full_name_cn: '张三',
    passport_number: `MOCK-${Date.now()}` ,
    birth_date: '1990-01-01',
    expiry_date: '2030-01-01',
    gender: 'M',
    nationality: 'CHN',
    mrz_raw: 'P<CHNZHANG<<SAN<<<<<<<<<<<<<<<<<<<<',
    confidence: { full_name_latin: 0.9, passport_number: 0.9 },
    provider_mode: 'miniapp-local-mock'
  };
}

function pickOcrEntries(ocr) {
  const excluded = { confidence: true, provider_raw: true, provider_mode: true };
  return Object.keys(ocr || {})
    .filter((key) => !excluded[key])
    .map((key) => ({ key, value: ocr[key] == null ? '' : String(ocr[key]) }));
}

Page({
  data: {
    step: 0,
    totalSteps: 10,
    lang: 'zh',
    tmap: {},
    userId: uid(),
    status: 'Ready',
    apiBaseInput: '',
    showApiConfig: false,
    apiConfigured: false,
    ocr: {},
    liveness: {},
    address: { address_line1: '', address_line2: '', city: '', region: '', postal_code: '', country: 'CN' },
    kycFinal: {},
    offer: {},
    consent: {},
    offerAccepted: false,
    pdAccepted: false,
    rfPhone: '+7',
    otpId: '',
    otpCode: '123456',
    card: {},
    cny: {},
    topupAmount: 100,
    qrRaw: '',
    draft: {},
    pin: '1111',
    txResult: {},
    exportJson: '',
    ocrItems: [],
    ocrDone: false,
    ocrSource: '',
    providerStatus: '',
    providerDebugMessage: '',
    providerLogTail: '',
    providerLogPath: '',
    demoModeEnabled: false
  },

  onLoad() {
    const g = globalData();
    this.setData({
      apiBaseInput: g.apiBase || '',
      showApiConfig: Boolean(g.showApiConfig),
      apiConfigured: hasConfiguredApiBase(),
      providerStatus: hasConfiguredApiBase() ? 'Checking OCR provider...' : 'OCR backend not configured',
      demoModeEnabled: canUseLocalMockOcr()
    });
    this.loadProviderStatus();
    this.refreshLang();
  },

  nextStep() {
    if (this.data.step === 0 && !this.data.ocrDone) {
      const g = globalData();
      const base = String((g && g.apiBase) || '').trim();
      this.fail({ error: base ? 'Run Passport OCR first' : 'Set apiBase, then run Passport OCR' });
      return;
    }
    if (this.data.step === 1 && !this.data.liveness.liveness_passed) {
      this.fail({ error: 'Run liveness first' });
      return;
    }

    const next = Math.min(this.data.step + 1, this.data.totalSteps - 1);
    this.setData({ step: next });
    if (next === 3 && (!this.data.offer.doc_version || !this.data.consent.doc_version)) {
      this.loadDocs();
    }
  },

  saveApiBase() {
    try {
      const value = String(this.data.apiBaseInput || '').trim();
      if (!value) return this.fail({ error: 'apiBase required' });
      if (!value.startsWith('https://')) {
        return this.fail({ error: 'Use HTTPS public domain in WeChat' });
      }
      const g = globalData();
      if (typeof g.setApiBase === 'function') g.setApiBase(value);
      else g.apiBase = value;
      this.setData({ apiConfigured: hasConfiguredApiBase() });
      this.loadProviderStatus();
      this.ok('apiBase saved');
    } catch (e) { this.fail(e); }
  },

  openApiConfig() {
    this.setData({ showApiConfig: true });
  },

  enableDemoMode() {
    const g = globalData();
    if (typeof g.setAllowLocalMockOcr === 'function') g.setAllowLocalMockOcr(true);
    else g.allowLocalMockOcr = true;
    this.setData({ demoModeEnabled: true });
    this.ok('Demo mode enabled: local OCR mock active');
  },

  prevStep() {
    this.setData({ step: Math.max(this.data.step - 1, 0) });
  },

  goToStep(e) {
    this.setData({ step: Number(e.currentTarget.dataset.step || 0) });
  },

  ensureApiBase() {
    const g = globalData();
    const base = (g.apiBase || '').trim();
    if (!base) {
      this.fail({ error: 'Set apiBase first (HTTPS domain)' });
      return false;
    }
    if (base.startsWith('http://127.0.0.1') || base.startsWith('http://localhost')) {
      this.fail({ error: '127.0.0.1/localhost blocked by WeChat legal domains' });
      return false;
    }
    return true;
  },

  async loadProviderStatus() {
    if (!hasConfiguredApiBase()) {
      this.setData({ providerStatus: 'OCR backend not configured' });
      return;
    }
    try {
      const status = await api.getProviderStatus();
      const mode = status.ocr_mode || 'unknown';
      const provider = status.kyc_provider || 'unknown';
      const tencentReady = status.tencent_ready ? 'tencent-ready' : 'tencent-not-ready';
      const last = status.last_ocr_mode || 'unknown';
      this.setData({
        providerStatus: `OCR provider: ${provider} (${mode}, ${tencentReady}), last=${last}`,
        providerDebugMessage: status.last_ocr_message || ''
      });
      const logs = await api.getProviderLogs(12);
      this.setData({ providerLogTail: (logs.lines || []).join('\n') });
    } catch (e) {
      this.setData({ providerStatus: 'Cannot read OCR provider status from backend' });
    }
  },

  refreshProviderStatus() {
    this.loadProviderStatus();
    this.ok('Provider status refreshed');
  },

  async testConnection() {
    if (!this.ensureApiBase()) return;
    await this.loadDocs();
    this.ok('API connected');
  },

  refreshLang() {
    const lang = this.data.lang;
    this.setData({
      tmap: {
        landing: t(lang, 'landing'), ocr: t(lang, 'ocr'), liveness: t(lang, 'liveness'), address: t(lang, 'address'),
        docs: t(lang, 'docs'), sms: t(lang, 'sms'), card: t(lang, 'card'), funding: t(lang, 'funding'),
        topup: t(lang, 'topup'), qr: t(lang, 'qr')
      }
    });
  },

  switchLang() {
    this.setData({ lang: this.data.lang === 'zh' ? 'en' : 'zh' });
    this.refreshLang();
    this.loadDocs();
  },

  async loadDocs() {
    if (!this.ensureApiBase()) return;
    try {
      const [offer, consent] = await Promise.all([api.getOffer(this.data.lang), api.getPdConsent(this.data.lang)]);
      this.setData({ offer, consent });
    } catch (e) { this.fail(e); }
  },

  onInput(e) {
    const { key } = e.currentTarget.dataset;
    this.setData({ [key]: e.detail.value });
  },

  onAddressInput(e) {
    const { key } = e.currentTarget.dataset;
    this.setData({ [`address.${key}`]: e.detail.value });
  },

  async runOcrWithImage(imageData = 'base64-mock-image') {
    let ocr = null;
    if (hasConfiguredApiBase()) {
      ocr = await api.ocr({ user_id: this.data.userId, image: imageData, image_base64: imageData });
      if (!hasOcrData(ocr)) {
        throw { error: 'OCR returned empty passport data' };
      }
    } else if (canUseLocalMockOcr()) {
      ocr = mockOcrResult();
    } else {
      throw { error: 'OCR provider is not connected. Configure apiBase to use Tencent/backend OCR.' };
    }
    const confidence = ocr.confidence || {};
    const ocrItems = pickOcrEntries(ocr);
    const kycFinal = {};
    ocrItems.forEach((entry) => {
      kycFinal[entry.key] = entry.value;
    });
    if (!kycFinal.full_name_cn) {
      kycFinal.full_name_cn = '';
    }
    kycFinal.confidence = confidence;
    this.setData({
      ocr,
      ocrItems,
      kycFinal,
      ocrDone: true,
      ocrSource: String(ocr.provider_mode || 'unknown')
    });
  },

  onKycInput(e) {
    const { key } = e.currentTarget.dataset;
    const value = e.detail.value;
    const ocrItems = (this.data.ocrItems || []).map((entry) => (entry.key === key ? { key, value } : entry));
    this.setData({ [`kycFinal.${key}`]: value, ocrItems });
  },

  async runOcr() {
    try {
      const chosen = await new Promise((resolve) => {
        wx.chooseImage({ count: 1, success: resolve, fail: () => resolve(null) });
      });
      let imagePayload = 'base64-mock-image';
      if (chosen && chosen.tempFilePaths && chosen.tempFilePaths[0]) {
        const path = chosen.tempFilePaths[0];
        try {
          const fileSystem = wx.getFileSystemManager();
          const base64 = await new Promise((resolve, reject) => {
            fileSystem.readFile({ filePath: path, encoding: 'base64', success: (r) => resolve(r.data), fail: reject });
          });
          imagePayload = base64;
        } catch (e) {
          imagePayload = path;
        }
      }
      await this.runOcrWithImage(imagePayload);
      const mode = this.data.ocr.provider_mode;
      this.ok(mode === 'miniapp-local-mock' ? 'OCR completed (local mock, not Tencent)' : `OCR completed (${mode || 'provider'})`);
      this.nextStep();
    } catch (e) {
      const msg = (e && (e.error || e.errMsg)) || '';
      if (msg.includes('OCR provider is not connected')) {
        this.setData({ showApiConfig: true, apiConfigured: false, demoModeEnabled: canUseLocalMockOcr() });
      }
      this.fail(e);
    }
  },

  async runLiveness() {
    try {
      let liveness;
      if (hasConfiguredApiBase()) {
        const start = await api.livenessStart({ user_id: this.data.userId });
        liveness = await api.livenessFinish({ user_id: this.data.userId, session_id: start.session_id, frames: ['frame1'] });
      } else {
        liveness = mockLivenessResult();
      }
      this.setData({ liveness });
      if (!liveness.liveness_passed) return this.fail({ error: 'Liveness failed' });
      this.ok(liveness.provider_mode === 'miniapp-local-mock' ? 'Liveness passed (local mock)' : 'Liveness passed');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async submitKyc() {
    if (!this.ensureApiBase()) return;
    try {
      if (!this.data.address.address_line1 || !this.data.address.city || !this.data.address.country) {
        return this.fail({ error: 'Address required: line1, city, country' });
      }
      await api.submitKyc({ user_id: this.data.userId, kyc_final: this.data.kycFinal, address: this.data.address });
      this.ok('KYC submitted');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  toggleOffer(e) { this.setData({ offerAccepted: e.detail.value.includes('ok') }); },
  togglePd(e) { this.setData({ pdAccepted: e.detail.value.includes('ok') }); },

  async acceptDocs() {
    if (!this.ensureApiBase()) return;
    try {
      if (!this.data.offerAccepted || !this.data.pdAccepted) return this.fail({ error: 'Both checkboxes required' });
      await api.acceptDoc({ user_id: this.data.userId, doc_version: this.data.offer.doc_version, accepted: true });
      await api.acceptDoc({ user_id: this.data.userId, doc_version: this.data.consent.doc_version, accepted: true });
      this.ok('Docs accepted');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async sendOtp() {
    if (!this.ensureApiBase()) return;
    try {
      const r = await api.smsSend({ user_id: this.data.userId, rf_phone: this.data.rfPhone });
      this.setData({ otpId: r.otp_id });
      this.ok('OTP sent');
    } catch (e) { this.fail(e); }
  },

  async verifyOtp() {
    if (!this.ensureApiBase()) return;
    try {
      await api.smsVerify({ user_id: this.data.userId, otp_id: this.data.otpId, code: this.data.otpCode });
      const card = await api.createCard({ user_id: this.data.userId });
      this.setData({ card });
      this.ok('PEP verified + card created');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async bindCny() {
    if (!this.ensureApiBase()) return;
    try {
      const cny = await api.bindCny({ user_id: this.data.userId, card_last4: '1234', brand: 'UnionPay' });
      this.setData({ cny });
      this.ok('CNY token bound');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async topup() {
    if (!this.ensureApiBase()) return;
    try {
      const txResult = await api.topup({ user_id: this.data.userId, amount_cny: Number(this.data.topupAmount) });
      this.setData({ txResult });
      this.ok('Topup success');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async scanQr() {
    if (!this.ensureApiBase()) return;
    try {
      const scan = await new Promise((resolve) => {
        wx.scanCode({ success: resolve, fail: () => resolve({ result: 'pay:coffee_shop:50:RUB:inv-1' }) });
      });
      const draft = await api.qrParse({ user_id: this.data.userId, qr_raw: scan.result });
      this.setData({ qrRaw: scan.result, draft });
      this.ok('QR parsed');
    } catch (e) { this.fail(e); }
  },

  async confirmPay() {
    if (!this.ensureApiBase()) return;
    try {
      const txResult = await api.payConfirm({ user_id: this.data.userId, draft_id: this.data.draft.draft_id, method: 'pin', pin: this.data.pin });
      this.setData({ txResult });
      this.ok('Payment success');
      this.nextStep();
    } catch (e) { this.fail(e); }
  },

  async exportJson() {
    if (!this.ensureApiBase()) return;
    try {
      const data = await api.exportUser(this.data.userId);
      this.setData({ exportJson: JSON.stringify(data, null, 2) });
      this.ok('Export ready');
    } catch (e) { this.fail(e); }
  },

  ok(status) { this.setData({ status }); wx.showToast({ title: status, icon: 'success' }); },
  fail(e) {
    const msg = (e && (e.error || e.errMsg)) || 'Error';
    this.setData({ status: msg });
    wx.showToast({ title: msg, icon: 'none' });
  }
});
