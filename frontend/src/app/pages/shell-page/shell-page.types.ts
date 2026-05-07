import { InjectionToken } from '@angular/core';
import type { WritableSignal } from '@angular/core';
import type {
  ComputerRunSnapshot,
  ImageProject,
  ModelCatalogPayload,
  UsageHistoryResponse,
  UsageScope,
  UsageView,
} from '../../core/backend-api.service';

export type ShellPageTokenHistoryTab = 'session' | 'today' | 'all_time';
export type ShellPageVoiceMode = 'realtime' | 'turn' | 'transcribe' | 'tts';
export type ShellPageImageActionPending = 'none' | 'regenerate' | 'refine' | 'variation';

export interface ShellPageImageActionSnapshot {
  prompt: string;
  model: string;
  moderation: 'auto' | 'low';
  style: 'photorealistic' | 'illustration' | '3d_render' | 'poster' | 'minimal';
  size: 'square' | 'portrait' | 'landscape';
  count: 1 | 2 | 4;
}

export interface ShellPagePromptHistoryItem {
  key: string;
  prompt: string;
  createdAt: number | null;
  favorite: boolean;
  snapshot: ShellPageImageActionSnapshot | null;
}

export interface ShellPageWorkspaceImage {
  key: string;
  messageId: number | null;
  b64: string;
  mime: string;
  prompt: string;
  model: string;
  moderation: string;
  style: string;
  size: string;
  outputIndex: number | null;
  outputTotal: number | null;
  generatedAt: number | null;
  createdAt: number;
  favorite: boolean;
  projectId: string | null;
}

export interface ComputerTabVm {
  settingsModelInput: WritableSignal<string>;
  settingsEffortInput: WritableSignal<string>;
  settingsStatus: WritableSignal<string>;
  saveSettings(): void;
  computerModel: WritableSignal<string>;
  computerStartUrl: WritableSignal<string>;
  computerPrompt: WritableSignal<string>;
  startComputerRun(): void;
  stepComputerRun(): void;
  closeComputerRun(): void;
  computerRun: WritableSignal<ComputerRunSnapshot | null>;
  loadUsageHistory(): void;
  loadModelCatalogRaw(): void;
  loadingUsageHistory: WritableSignal<boolean>;
  usageHistory: WritableSignal<UsageHistoryResponse | null>;
  modelCatalogRaw: WritableSignal<ModelCatalogPayload | null>;
  toolsStatus: WritableSignal<string>;
}

export interface EmbeddingsTabVm {
  embeddingModel: WritableSignal<string>;
  embedTextInput: WritableSignal<string>;
  runEmbedText(): void;
  selectedSessionId: WritableSignal<string>;
  runEmbedIndex(): void;
  embedQueryInput: WritableSignal<string>;
  embedTopK: WritableSignal<number>;
  runEmbedSearch(): void;
  toolsStatus: WritableSignal<string>;
  embedSearchResult: WritableSignal<string>;
}

export interface UsagePanelVm {
  usagePanelCollapsed: WritableSignal<boolean>;
  showTokenHistoryAction(): boolean;
  openTokenHistory(): void;
  toggleUsagePanel(event?: Event): void;
  loadingUsage: WritableSignal<boolean>;
  showStandardUsagePanel(): boolean;
  usageView: WritableSignal<UsageView | null>;
  contextWindowDisplay(): string;
  hasContextWindowMetrics(): boolean;
  contextUsedPct(): number;
  currentResponseTotal(): number | null;
  contextWindow(): number;
  totalChatContextPct(): number;
  totalChatContextBarPct(): number;
  isVoiceTab(): boolean;
  selectedModelInputPriceStr(): string;
  selectedModelOutputPriceStr(): string;
  voicePrimaryAudioInputPriceLabel(): string;
  voicePrimaryAudioInputPriceStr(): string;
  voicePrimaryAudioOutputPriceLabel(): string;
  voicePrimaryAudioOutputPriceStr(): string;
  isTranscribeVoiceMode(): boolean;
  voiceTranscriptionInputPriceStr(): string;
  voiceTranscriptionOutputPriceStr(): string;
  voicePricingFooter(): string;
  isVideoMediaMode(): boolean;
  selectedModel: WritableSignal<string>;
  isSpeechVoiceMode(): boolean;
  ttsUsesCharacterPricing(): boolean;
  ttsSpeechGenerationPriceStr(): string;
  ttsTextInputPriceStr(): string;
  ttsAudioOutputPriceStr(): string;
  ttsPricingFooter(): string;
  showTokenHistoryModal: WritableSignal<boolean>;
  closeTokenHistory(event?: Event): void;
  isTokenHistoryTab(tab: ShellPageTokenHistoryTab): boolean;
  setTokenHistoryTab(tab: ShellPageTokenHistoryTab): void;
  tokenHistoryTab: WritableSignal<ShellPageTokenHistoryTab>;
  tokenHistoryScopeTitle(tab: ShellPageTokenHistoryTab): string;
  tokenHistoryScope(tab: ShellPageTokenHistoryTab): UsageScope;
  tokenHistoryScopeTotalDisplay(tab: ShellPageTokenHistoryTab): string;
  tokenHistoryEmptyMessage(tab: ShellPageTokenHistoryTab): string;
}

export interface VoiceTabVm {
  isVoiceModeActive(mode: ShellPageVoiceMode): boolean;
  bootstrapRealtimeVoice(): void;
  audioTurnModel: WritableSignal<string>;
  onAudioTurnModelChange(model: string): void;
  audioTurnVoice: WritableSignal<string>;
  onAudioTurnFileSelected(event: Event): void;
  transcriptionModel: WritableSignal<string>;
  onTranscriptionModelChange(model: string): void;
  onTranscriptionFileSelected(event: Event): void;
  ttsModel: WritableSignal<string>;
  onTtsModelChange(model: string): void;
  ttsVoice: WritableSignal<string>;
  ttsText: WritableSignal<string>;
  runTts(): void;
  ttsAudioUrl: WritableSignal<string>;
  voiceStatus: WritableSignal<string>;
}

export interface VisualTabVm {
  isImageMediaMode(): boolean;
  selectedWorkspaceImage(): ShellPageWorkspaceImage | null;
  imageControlDisabled(): boolean;
  regenerateSelectedWorkspaceImage(): void;
  imageActionPending: WritableSignal<ShellPageImageActionPending>;
  imageActionBusy: WritableSignal<boolean>;
  refineSelectedWorkspaceImage(): void;
  downloadSelectedWorkspaceImage(): void;
  createVariationFromSelectedImage(): void;
  visualCanvasAspectRatio(item: ShellPageWorkspaceImage | null): string;
  imageProjects: WritableSignal<ImageProject[]>;
  openCreateProjectDialog(): void;
  imagePromptHistoryItems: WritableSignal<ShellPagePromptHistoryItem[]>;
  copyImagePromptHistoryPrompt(item: ShellPagePromptHistoryItem): void;
  loadImagePromptHistory(item: ShellPagePromptHistoryItem): void;
  sending: WritableSignal<boolean>;
  imageWorkspaceItems: WritableSignal<ShellPageWorkspaceImage[]>;
  selectWorkspaceImage(item: ShellPageWorkspaceImage): void;
  toggleWorkspaceImageFavorite(item: ShellPageWorkspaceImage, event?: Event): void;
  assignProjectToSelectedWorkspaceImage(projectId: string): void;
  isVisualMediaTab(): boolean;
  isVideoMediaMode(): boolean;
}

export interface ShellPageVm extends ComputerTabVm, EmbeddingsTabVm, UsagePanelVm, VoiceTabVm, VisualTabVm {}

export const SHELL_PAGE_VM = new InjectionToken<ShellPageVm>('SHELL_PAGE_VM');
