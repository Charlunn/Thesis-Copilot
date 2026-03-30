import type { QnuCopilotApi } from "./types";

export {};

declare global {
  interface Window {
    qnuCopilot: QnuCopilotApi;
  }
}
