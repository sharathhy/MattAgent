import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "@fontsource/orbitron/500.css";
import "@fontsource/orbitron/700.css";
import "@fontsource/rajdhani/500.css";
import "@fontsource/rajdhani/600.css";

import { App } from "./App";
import "./index.css";
import { AuthProvider } from "./lib/auth";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000 } } });

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
