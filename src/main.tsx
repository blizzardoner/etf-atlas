import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    const base = new URL(import.meta.env.BASE_URL, document.baseURI);
    navigator.serviceWorker
      .register(new URL("sw.js", base), { scope: base.pathname })
      .catch((error) => console.warn("离线缓存注册失败", error));
  });
}
