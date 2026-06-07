const DEFAULT_PORT = 17892;

document.addEventListener("DOMContentLoaded", async () => {
  const stored = await chrome.storage.local.get(["bridgePort"]);
  document.getElementById("port").value = stored.bridgePort || DEFAULT_PORT;
});

document.getElementById("save").addEventListener("click", async () => {
  const port = parseInt(document.getElementById("port").value, 10) || DEFAULT_PORT;
  await chrome.storage.local.set({ bridgePort: port });
  document.getElementById("saved").textContent = "已保存。若修改了端口，请重新加载扩展。";
});

document.getElementById("reset").addEventListener("click", async () => {
  await chrome.storage.local.remove(["bridgeToken"]);
  document.getElementById("saved").textContent = "已清除配对信息，正在重新连接…";
  chrome.runtime.sendMessage({ type: "reset_bridge_connection" }, () => {
    document.getElementById("saved").textContent =
      "已请求重新连接。请确保桌面程序正在运行，并在弹窗中点「是」。";
  });
});
