import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export interface SessionSummary {
  id: string;
  title: string;
  useCase: string;
  archivedAt: number | null;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  attachmentCount: number;
}

export interface SessionMessage {
  id: number | string;
  role: 'user' | 'assistant' | string;
  content: string;
  msgType: string;
  status?: string;
  payload?: JsonObject | null;
  usage?: UsageMetrics | null;
  usageModel?: string;
  usageCost?: number;
  elapsedSec?: number;
  createdAt?: number;
  reasoningSummary?: string;
  reasoningStatus?: string;
}

export interface SessionView {
  id: string;
  title: string;
  useCase: string;
  prompt?: string;
  context?: string;
  promptPresetId?: string;
  messages: SessionMessage[];
  attachments?: AttachmentRecord[];
  messageCount: number;
}

export interface SessionsResponse {
  sessions: SessionSummary[];
}

export interface ModelCatalogPayload {
  defaults?: {
    useCase?: string;
    tier?: string;
    thinking?: string;
  };
  thinkingPolicy?: {
    enabledUseCases?: string[];
    defaultLevels?: Array<{ key: string; label: string }>;
    overridesByModelPrefix?: Record<string, Array<{ key: string; label: string }>>;
  };
  modelMap?: Record<string, Record<string, string[]>>;
  modelMetadata?: Record<string, ModelMetadataEntry>;
  serviceTierTextPricing?: Record<string, {
    standard?: {
      inputPricePerMtok?: number;
      outputPricePerMtok?: number;
      cachedInputPricePerMtok?: number;
    };
    priority?: {
      inputPricePerMtok?: number;
      outputPricePerMtok?: number;
      cachedInputPricePerMtok?: number;
    };
    flex?: {
      inputPricePerMtok?: number;
      outputPricePerMtok?: number;
      cachedInputPricePerMtok?: number;
    };
  }>;
}

export interface ModelMetadataEntry {
  contextWindow?: number;
  canonicalModelId?: string;
  assistantVoices?: string[];
  ttsVoices?: string[];
}

export interface VmCatalogResponse {
  catalog: ModelCatalogPayload;
  catalogView: VmCatalogView;
  developerLabel?: string;
}

export interface VmCatalogView {
  selectedModel?: string;
  serviceTier?: 'default' | 'flex' | 'priority' | string;
  selectedModelInputPriceStr?: string;
  selectedModelCachedInputPriceStr?: string;
  selectedModelOutputPriceStr?: string;
  voicePrimaryAudioInputPriceLabel?: string;
  voicePrimaryAudioOutputPriceLabel?: string;
  voicePrimaryAudioInputPriceStr?: string;
  voicePrimaryAudioOutputPriceStr?: string;
  voiceTranscriptionInputPriceStr?: string;
  voiceTranscriptionOutputPriceStr?: string;
  voicePricingFooter?: string;
  ttsTextInputPriceStr?: string;
  ttsAudioOutputPriceStr?: string;
  ttsSpeechGenerationPriceStr?: string;
  ttsUsesCharacterPricing?: boolean;
  ttsPricingFooter?: string;
}

export interface UsageRow {
  model: string;
  input: number;
  cachedInput?: number;
  output: number;
  total: number;
  reasoning: number;
  cost: number;
  tokenSharePct: number;
  costSharePct: number;
  costDisplay?: string;
}

export interface UsageScope {
  totals: {
    input: number;
    cachedInput?: number;
    output: number;
    total: number;
    reasoning: number;
    cost: number;
    costDisplay: string;
  };
  rows: UsageRow[];
  date?: string;
}

export interface UsageView {
  lastResponse: {
    usage: UsageMetrics | null;
    cost: number;
    costDisplay: string;
    elapsedSec: number | null;
    elapsedDisplay: string;
  };
  activeSession: UsageScope;
  today: UsageScope;
  week: UsageScope;
  month: UsageScope;
  allTime: UsageScope;
  panels: {
    chatCostDisplay: string;
    dayCostDisplay: string;
    allTimeCostDisplay: string;
  };
}

export interface UsageMetrics {
  input?: number;
  output?: number;
  total?: number;
  reasoning?: number;
  cachedInput?: number;
  details?: {
    inputText?: number;
    inputAudio?: number;
    inputImage?: number;
    inputCachedText?: number;
    inputCachedAudio?: number;
    inputCachedImage?: number;
    outputText?: number;
    outputAudio?: number;
  };
}

export interface VoiceTurnResult {
  sessionView?: SessionView;
  usageView?: UsageView;
  audio?: string;
  audioMime?: string;
  voice?: string;
}

export interface VoiceRealtimeTurnPersistResult {
  sessionView?: SessionView;
  usageView?: UsageView;
  usageSummary?: {
    turnUsage?: UsageMetrics | null;
    turnCost?: number;
    activeSession?: UsageScope;
  };
}

export interface TranscriptionTurnResult {
  sessionView?: SessionView;
  usageView?: UsageView;
  timestampsAvailable?: boolean;
  sourceKind?: string;
  sourceName?: string;
}

export interface ChatStreamEvent {
  content?: string;
  reasoning?: {
    summary?: string;
    status?: string;
  };
  usageView?: UsageView;
  usage?: unknown;
  error?: string;
  errorCode?: string;
  requestId?: string;
  done?: boolean;
}

export interface PromptPreset {
  id: string;
  name: string;
  instructions: string;
  context: string;
}

export interface AttachmentRecord {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  active: boolean;
  usable: boolean;
  statusLabel: string;
  displayMeta: string;
  toggleTitle: string;
}

export interface UsageHistoryResponse {
  date: string;
  summary: {
    input: number;
    cachedInput?: number;
    output: number;
    total: number;
    reasoning: number;
    cost: number;
    costDisplay: string;
  };
  rows: Array<{
    ts: number;
    sessionId: string;
    useCase: string;
    model: string;
    input: number;
    cachedInput?: number;
    output: number;
    total: number;
    reasoning: number;
    cost: number;
    costDisplay: string;
  }>;
}

export type UsageScopeKey = 'session' | 'today' | 'week' | 'month' | 'all_time';

export interface UsageModelBreakdownBucket {
  timestampLabel: string;
  input: number;
  cachedInput?: number;
  output: number;
  total: number;
  reasoning: number;
  cost: number;
  costDisplay: string;
  messageCount: number;
}

export interface UsageModelBreakdownResponse {
  scope: UsageScopeKey;
  model: string;
  totals: {
    input: number;
    cachedInput?: number;
    output: number;
    total: number;
    reasoning: number;
    cost: number;
    costDisplay: string;
  };
  buckets: UsageModelBreakdownBucket[];
}

export interface DeepResearchMcpProfile {
  id: string;
  label: string;
  description: string;
  isDefault: boolean;
}

export interface DeepResearchToolsSelection {
  webSearch: boolean;
  codeInterpreter: boolean;
  fileSearch: boolean;
  mcp: boolean;
}

export interface ComputerRunSnapshot {
  runId: string;
  status: string;
  nextAction?: JsonObject | null;
  timeline?: JsonObject[];
  finalText?: string;
  usage?: JsonObject | null;
  error?: string;
  errorCode?: string;
}

export interface ImageResult {
  b64: string;
  mime: string;
  prompt?: string;
  instruction?: string;
  model?: string;
  style?: string;
  size?: string;
}

export interface ImageProject {
  id: string;
  name: string;
  createdAt: number;
  updatedAt: number;
}

@Injectable({ providedIn: 'root' })
export class BackendApiService {
  constructor(private readonly http: HttpClient) {}

  getSessions(): Observable<SessionsResponse> {
    return this.http.get<SessionsResponse>('/sessions');
  }

  getVmSession(sessionId: string): Observable<{ sessionView: SessionView }> {
    return this.http.get<{ sessionView: SessionView }>(`/vm/session/${encodeURIComponent(sessionId)}`);
  }

  getVmCatalog(
    selectedModel?: string,
    voiceMode?: string,
    processingMode?: 'standard' | 'priority' | 'flex' | string,
  ): Observable<VmCatalogResponse> {
    const params = new URLSearchParams();
    if (selectedModel) params.set('selectedModel', selectedModel);
    if (voiceMode) params.set('voiceMode', voiceMode);
    if (processingMode) params.set('processingMode', processingMode);
    const query = params.toString();
    return this.http.get<VmCatalogResponse>(`/vm/catalog${query ? `?${query}` : ''}`);
  }

  getVmUsage(sessionId: string, selectedModel: string, voiceMode: string): Observable<{ usageView: UsageView }> {
    const params = new URLSearchParams({
      sessionId,
      selectedModel,
      voiceMode,
    });
    return this.http.get<{ usageView: UsageView }>(`/vm/usage?${params.toString()}`);
  }

  getPromptPresets(): Observable<{ presets: PromptPreset[] }> {
    return this.http.get<{ presets: PromptPreset[] }>('/prompt-presets');
  }

  createPromptPreset(payload: { name: string; instructions: string; context?: string }): Observable<{ preset: PromptPreset }> {
    return this.http.post<{ preset: PromptPreset }>('/prompt-presets', payload);
  }

  updatePromptPreset(
    presetId: string,
    payload: { name: string; instructions: string; context?: string },
  ): Observable<{ preset: PromptPreset }> {
    return this.http.patch<{ preset: PromptPreset }>(`/prompt-presets/${encodeURIComponent(presetId)}`, payload);
  }

  deletePromptPreset(presetId: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`/prompt-presets/${encodeURIComponent(presetId)}`);
  }

  getUsageHistory(sessionId?: string): Observable<UsageHistoryResponse> {
    const params = new URLSearchParams();
    if (sessionId) params.set('sessionId', sessionId);
    const query = params.toString();
    return this.http.get<UsageHistoryResponse>(`/usage/history${query ? `?${query}` : ''}`);
  }

  getUsageModelBreakdown(
    scope: UsageScopeKey,
    model: string,
    sessionId?: string,
  ): Observable<UsageModelBreakdownResponse> {
    const params = new URLSearchParams();
    params.set('scope', scope);
    params.set('model', model);
    if (sessionId) params.set('sessionId', sessionId);
    return this.http.get<UsageModelBreakdownResponse>(`/usage/model-breakdown?${params.toString()}`);
  }

  getModelCatalog(): Observable<ModelCatalogPayload> {
    return this.http.get<ModelCatalogPayload>('/model-catalog');
  }

  getDeepResearchMcpProfiles(): Observable<{ profiles: DeepResearchMcpProfile[]; defaultProfileId?: string }> {
    return this.http.get<{ profiles: DeepResearchMcpProfile[]; defaultProfileId?: string }>('/deep-research/mcp-profiles');
  }

  updateSessionSetup(
    sessionId: string,
    payload: { useCase?: string; prompt?: string; context?: string; promptPresetId?: string },
  ): Observable<{ sessionView: SessionView }> {
    return this.http.patch<{ sessionView: SessionView }>(`/sessions/${encodeURIComponent(sessionId)}`, payload);
  }

  updateSessionTitle(sessionId: string, title: string): Observable<{ sessionView: SessionView }> {
    return this.http.patch<{ sessionView: SessionView }>(`/sessions/${encodeURIComponent(sessionId)}`, { title });
  }

  archiveSession(sessionId: string, archived: boolean): Observable<{ ok: boolean; archivedAt: number | null }> {
    return this.http.patch<{ ok: boolean; archivedAt: number | null }>(`/sessions/${encodeURIComponent(sessionId)}/archive`, { archived });
  }

  clearSession(sessionId: string): Observable<{ ok: boolean; sessionView?: SessionView }> {
    return this.http.post<{ ok: boolean; sessionView?: SessionView }>(`/sessions/${encodeURIComponent(sessionId)}/clear`, {});
  }

  deleteSession(sessionId: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`/sessions/${encodeURIComponent(sessionId)}`);
  }

  uploadAttachments(sessionId: string, useCase: string, files: File[]): Observable<{ files: AttachmentRecord[] }> {
    const formData = new FormData();
    formData.append('useCase', useCase);
    for (const file of files) {
      formData.append('files', file, file.name);
    }
    return this.http.post<{ files: AttachmentRecord[] }>(`/sessions/${encodeURIComponent(sessionId)}/attachments`, formData);
  }

  updateAttachment(sessionId: string, attachmentId: string, active: boolean): Observable<{ file: AttachmentRecord }> {
    return this.http.patch<{ file: AttachmentRecord }>(
      `/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}`,
      { active },
    );
  }

  deleteAttachment(sessionId: string, attachmentId: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(
      `/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}`,
    );
  }

  textToSpeech(payload: {
    sessionId: string;
    useCase: string;
    model: string;
    text: string;
    voice: string;
  }): Observable<{ audio: string; audioMime: string; sessionView?: SessionView; usageView?: UsageView }> {
    return this.http.post<{ audio: string; audioMime: string; sessionView?: SessionView; usageView?: UsageView }>('/tts', payload);
  }

  createAudioTurn(payload: {
    sessionId: string;
    model: string;
    useCase: string;
    voice: string;
    file: File;
  }): Observable<VoiceTurnResult> {
    const formData = new FormData();
    formData.append('audio', payload.file, payload.file.name || 'turn.webm');
    formData.append('model', payload.model);
    formData.append('useCase', payload.useCase);
    formData.append('voice', payload.voice);
    return this.http.post<VoiceTurnResult>(`/sessions/${encodeURIComponent(payload.sessionId)}/audio/turn`, formData);
  }

  createTranscriptionTurn(payload: {
    sessionId: string;
    model: string;
    useCase: string;
    sourceKind: 'uploaded' | 'recorded';
    file: File;
  }): Observable<TranscriptionTurnResult> {
    const formData = new FormData();
    formData.append('audio', payload.file, payload.file.name || 'transcription.webm');
    formData.append('model', payload.model);
    formData.append('useCase', payload.useCase);
    formData.append('sourceKind', payload.sourceKind);
    return this.http.post<TranscriptionTurnResult>(
      `/sessions/${encodeURIComponent(payload.sessionId)}/transcription/turn`,
      formData,
    );
  }

  bootstrapVoiceSession(payload: {
    sessionId: string;
    model: string;
    useCase: string;
    voice: string;
  }): Observable<{
    clientSecret: string;
    expiresAt?: number;
    model: string;
    voice: string;
    transcriptionModel: string;
    sessionType: string;
  }> {
    return this.http.post<{
      clientSecret: string;
      expiresAt?: number;
      model: string;
      voice: string;
      transcriptionModel: string;
      sessionType: string;
    }>(`/sessions/${encodeURIComponent(payload.sessionId)}/voice/bootstrap`, {
      model: payload.model,
      useCase: payload.useCase,
      voice: payload.voice,
    });
  }

  persistRealtimeVoiceTurn(
    sessionId: string,
    payload: {
      userText: string;
      assistantText: string;
      model: string;
      useCase: string;
      userUsage?: UsageMetrics | null;
      assistantUsage?: UsageMetrics | null;
      userUsageModel?: string;
      elapsedSec?: number;
    },
  ): Observable<VoiceRealtimeTurnPersistResult> {
    return this.http.post<VoiceRealtimeTurnPersistResult>(
      `/sessions/${encodeURIComponent(sessionId)}/voice/turns`,
      payload,
    );
  }

  updateSettings(payload: { model?: string; effort?: string }): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>('/settings', payload);
  }

  startComputerRun(payload: {
    sessionId: string;
    userText: string;
    model: string;
    displayWidth?: number;
    displayHeight?: number;
    startUrl?: string;
    reasoningSummary?: 'auto' | 'concise' | 'detailed';
  }): Observable<ComputerRunSnapshot> {
    return this.http.post<ComputerRunSnapshot>('/computer-runs/start', payload);
  }

  stepComputerRun(runId: string, acknowledgedSafetyChecks?: JsonObject[]): Observable<ComputerRunSnapshot> {
    return this.http.post<ComputerRunSnapshot>(`/computer-runs/${encodeURIComponent(runId)}/step`, {
      acknowledgedSafetyChecks: acknowledgedSafetyChecks || [],
    });
  }

  closeComputerRun(runId: string): Observable<{ ok: boolean; runId: string; status: string }> {
    return this.http.post<{ ok: boolean; runId: string; status: string }>(`/computer-runs/${encodeURIComponent(runId)}/close`, {});
  }

  embedIndex(payload: {
    sessionId: string;
    model: string;
    includeInactive?: boolean;
    rebuild?: boolean;
  }): Observable<{ ok: boolean; indexedFiles: number; indexedChunks: number; model: string; sessionId: string }> {
    return this.http.post<{ ok: boolean; indexedFiles: number; indexedChunks: number; model: string; sessionId: string }>(
      '/embed-index',
      payload,
    );
  }

  embedSearch(payload: {
    sessionId: string;
    model: string;
    query: string;
    topK?: number;
  }): Observable<{
    sessionId: string;
    model: string;
    query: string;
    topK: number;
    matches: Array<{ fileName: string; chunkIndex: number; score: number; snippet: string }>;
    files: Array<{ fileName: string; score: number }>;
  }> {
    return this.http.post<{
      sessionId: string;
      model: string;
      query: string;
      topK: number;
      matches: Array<{ fileName: string; chunkIndex: number; score: number; snippet: string }>;
      files: Array<{ fileName: string; score: number }>;
    }>('/embed-search', payload);
  }

  embedText(payload: {
    sessionId: string;
    useCase: string;
    model: string;
    text: string;
  }): Observable<{ dimensions: number; preview: number[]; model: string }> {
    return this.http.post<{ dimensions: number; preview: number[]; model: string }>('/embed', payload);
  }

  generateImage(payload: {
    sessionId: string;
    useCase: string;
    model: string;
    prompt: string;
    moderation: 'auto' | 'low';
    style: 'photorealistic' | 'illustration' | '3d_render' | 'poster' | 'minimal';
    size: 'square' | 'portrait' | 'landscape';
    count: 1 | 2 | 4;
  }): Observable<{ image: string; mime: string; images: ImageResult[] }> {
    return this.http.post<{ image: string; mime: string; images: ImageResult[] }>('/image', payload);
  }

  editImage(payload: {
    sessionId: string;
    useCase: string;
    model: string;
    instruction: string;
    moderation: 'auto' | 'low';
    style: 'photorealistic' | 'illustration' | '3d_render' | 'poster' | 'minimal';
    size: 'square' | 'portrait' | 'landscape';
    count: 1 | 2 | 4;
    file: File;
  }): Observable<{ image: string; mime: string; images: ImageResult[] }> {
    const formData = new FormData();
    formData.append('sessionId', payload.sessionId);
    formData.append('useCase', payload.useCase);
    formData.append('model', payload.model);
    formData.append('instruction', payload.instruction);
    formData.append('moderation', payload.moderation);
    formData.append('style', payload.style);
    formData.append('size', payload.size);
    formData.append('count', String(payload.count));
    formData.append('image', payload.file, payload.file.name || 'image.png');
    return this.http.post<{ image: string; mime: string; images: ImageResult[] }>('/image/edit', formData);
  }

  getImageProjects(): Observable<{ projects: ImageProject[] }> {
    return this.http.get<{ projects: ImageProject[] }>('/image-projects');
  }

  createImageProject(name: string): Observable<{ project: ImageProject }> {
    return this.http.post<{ project: ImageProject }>('/image-projects', { name });
  }

  renameImageProject(projectId: string, name: string): Observable<{ project: ImageProject }> {
    return this.http.patch<{ project: ImageProject }>(`/image-projects/${encodeURIComponent(projectId)}`, { name });
  }

  deleteImageProject(projectId: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`/image-projects/${encodeURIComponent(projectId)}`);
  }

  updateImageMessageMeta(
    sessionId: string,
    messageId: number,
    patch: { favorite?: boolean; hiddenInWorkspace?: boolean; projectId?: string | null },
  ): Observable<{ ok: boolean; payload: JsonObject }> {
    return this.http.patch<{ ok: boolean; payload: JsonObject }>(
      `/sessions/${encodeURIComponent(sessionId)}/messages/${messageId}/image-meta`,
      patch,
    );
  }

  async streamChat(
    payload: {
      sessionId: string;
      userText: string;
      model: string;
      useCase: string;
      effort?: string;
      serviceTier?: 'default' | 'flex' | 'priority';
      includeWebSearch?: boolean;
      deepResearchTools?: DeepResearchToolsSelection;
      deepResearchMcpProfileId?: string;
    },
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const apiKey = String(environment.apiKey || '').trim();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const response = await fetch('/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    });

    if (!response.ok) {
      let errorText = `Request failed (${response.status})`;
      let errorCode = '';
      let requestId = '';
      try {
        const data = await response.json();
        const nestedError = data?.error;
        if (typeof nestedError === 'string' && nestedError.trim()) {
          errorText = nestedError.trim();
        } else if (nestedError && typeof nestedError === 'object' && typeof nestedError.message === 'string' && nestedError.message.trim()) {
          errorText = nestedError.message.trim();
          if (typeof nestedError.errorCode === 'string') errorCode = nestedError.errorCode.trim();
          if (typeof nestedError.code === 'string' && !errorCode) errorCode = nestedError.code.trim();
          if (typeof nestedError.requestId === 'string') requestId = nestedError.requestId.trim();
        } else if (typeof data?.message === 'string' && data.message.trim()) {
          errorText = data.message.trim();
        }
        if (!errorCode && typeof data?.errorCode === 'string') errorCode = data.errorCode.trim();
        if (!requestId && typeof data?.requestId === 'string') requestId = data.requestId.trim();
      } catch {
      }
      onEvent({
        error: errorText,
        errorCode: errorCode || undefined,
        requestId: requestId || undefined,
      });
      return;
    }

    if (!response.body) {
      onEvent({ error: 'No response stream returned by backend.' });
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          this._handleSseEvent(rawEvent, onEvent);
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (error: unknown) {
      if ((error as { name?: string })?.name === 'AbortError') {
        throw error;
      }
      throw error;
    } finally {
      reader.releaseLock();
    }

    if (buffer.trim()) {
      this._handleSseEvent(buffer, onEvent);
    }
  }

  private _handleSseEvent(rawEvent: string, onEvent: (event: ChatStreamEvent) => void): void {
    const dataLines = rawEvent
      .split('\n')
      .filter((line: string) => line.startsWith('data:'))
      .map((line: string) => line.slice(5).trim());
    if (dataLines.length === 0) return;

    const payload = dataLines.join('\n');
    if (payload === '[DONE]') {
      onEvent({ done: true });
      return;
    }

    try {
      const parsed = JSON.parse(payload) as ChatStreamEvent;
      onEvent(parsed);
    } catch {
    }
  }
}
