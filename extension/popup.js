const DEFAULT_PORT = 17892;

function detectBrowser() {
  const ua = navigator.userAgent || "";
  if (/115Browser|115\/|115browser/i.test(ua)) return "115 浏览器";
  if (/Edg\//i.test(ua)) return "Microsoft Edge";
  return "Chromium";
}

async function refresh() {
  document.getElementById("browser").textContent = detectBrowser();

  const stored = await chrome.storage.local.get(["bridgePort", "bridgeToken"]);
  const token = stored.bridgeToken || "";
  const statusEl = document.getElementById("status");
  const pageEl = document.getElementById("page");

  statusEl.textContent = "等待桌面程序...";
  statusEl.className = "status bad";

  const port = stored.bridgePort || DEFAULT_PORT;
  let ws;
  try {
    ws = new WebSocket(`ws://127.0.0.1:${port}`);
  } catch (_) {
    statusEl.textContent = "无法连接";
    return;
  }

  ws.addEventListener("open", () => {
    ws.send(
      JSON.stringify({
        type: "hello",
        browser: detectBrowser().includes("115") ? "115" : "edge",
        version: "popup",
        token,
      })
    );
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "auth_pending") {
      statusEl.textContent = "等待桌面程序允许...";
      statusEl.className = "status bad";
      pageEl.textContent = "请在 JAV一网打尽 桌面程序弹出的窗口中点「是」。";
      return;
    }
    if (msg.type === "hello_ack") {
      statusEl.textContent = "已连接";
      statusEl.className = "status ok";
      if (msg.token) {
        chrome.storage.local.set({ bridgeToken: msg.token, bridgePort: port }).catch(() => {});
      }
      chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
        const tab = tabs[0];
        if (tab) {
          pageEl.textContent = `${tab.title || "(无标题)"}\n${tab.url || ""}`;
        }
      });
      ws.close();
    }
    if (msg.type === "auth_rejected") {
      statusEl.textContent = "连接被拒绝";
      statusEl.className = "status bad";
      pageEl.textContent = "您已在桌面程序中拒绝扩展连接。";
      ws.close();
    }
    if (msg.type === "error") {
      statusEl.textContent = "连接失败";
      statusEl.className = "status bad";
      ws.close();
    }
  });

  ws.addEventListener("error", () => {
    statusEl.textContent = "桌面程序未运行";
    statusEl.className = "status bad";
  });
}

document.getElementById("openOptions").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

document.getElementById("reconnect").addEventListener("click", () => {
  refresh();
});

refresh();
