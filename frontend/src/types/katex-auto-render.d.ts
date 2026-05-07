declare module 'katex/contrib/auto-render' {
  export interface KatexAutoRenderOptions {
    delimiters?: Array<{ left: string; right: string; display: boolean }>;
    throwOnError?: boolean;
  }

  export default function renderMathInElement(
    element: HTMLElement,
    options?: KatexAutoRenderOptions,
  ): void;
}
