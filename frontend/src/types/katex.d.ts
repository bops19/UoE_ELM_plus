declare module 'katex' {
  export interface KatexRenderOptions {
    displayMode?: boolean;
    throwOnError?: boolean;
    strict?: 'ignore' | 'warn' | 'error' | ((errorCode: string, errorMsg: string, token?: unknown) => 'ignore' | 'warn' | 'error');
    output?: 'html' | 'mathml' | 'htmlAndMathml';
  }

  export interface KatexModule {
    renderToString(expression: string, options?: KatexRenderOptions): string;
  }

  const katex: KatexModule;
  export default katex;
}
