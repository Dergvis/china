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

module.exports = { t };
