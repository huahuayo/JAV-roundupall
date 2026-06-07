/**
 * 生成 TXT 已改由 extension/background.js + lib/magnet-txt-core.js 在后台执行。
 * 本文件保留占位，避免旧缓存引用报错。
 */
(function () {
  "use strict";
  if (window.JM_generateMagnetTxt) return;

  window.JM_generateMagnetTxt = function (code) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "generate_magnet_txt_start", code }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (response?.started) {
          resolve({ ok: true, started: true, message: "任务已在后台执行" });
          return;
        }
        reject(new Error(response?.message || "启动失败"));
      });
    });
  };
})();
