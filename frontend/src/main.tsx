import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers";
import "./styles/reset.css";
import "./styles/tokens.css";
import "./styles/globals.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Uygulama kök elementi bulunamadı.");
}

createRoot(root).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
);
