import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, HostListener, OnDestroy, OnInit, ViewChild, forwardRef, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { A11yModule } from '@angular/cdk/a11y';
import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { CdkFixedSizeVirtualScroll, CdkVirtualForOf, CdkVirtualScrollViewport } from '@angular/cdk/scrolling';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, firstValueFrom, forkJoin } from 'rxjs';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { ShellVisualTabComponent } from './components/visual-tab/visual-tab.component';
import { ShellUsagePanelComponent } from './components/usage-panel/usage-panel.component';
import { SHELL_PAGE_VM } from './shell-page.types';
import type {
  ShellPageImageActionSnapshot,
  ShellPagePromptHistoryItem,
  ShellPageVm,
  ShellPageWorkspaceImage,
} from './shell-page.types';
import { TextInputDialogComponent } from '../../shared/text-input-dialog/text-input-dialog.component';
import { AttachmentService } from './services/attachment.service';
import { CatalogService } from './services/catalog.service';
import { ComputerService } from './services/computer.service';
import { SessionService } from './services/session.service';
import { VisualService } from './services/visual.service';
import { VoiceService } from './services/voice.service';
import {
  AttachmentRecord,
  BackendApiService,
  ComputerRunSnapshot,
  DeepResearchMcpProfile,
  DeepResearchToolsSelection,
  ModelMetadataEntry,
  ModelCatalogPayload,
  PromptPreset,
  SessionMessage,
  SessionSummary,
  UsageMetrics,
  UsageScope,
  VmCatalogView,
  UsageHistoryResponse,
  UsageView,
} from '../../core/backend-api.service';

interface ThinkingLevelOption {
  key: string;
  label: string;
}

interface RealtimeTurnState {
  userLive: string;
  userFinal: string;
  assistantLive: string;
  assistantFinal: string;
  responseDone: boolean;
  persisting: boolean;
  persisted: boolean;
  audioPlaybackComplete: boolean;
  sawOutputAudioEvent: boolean;
  userUsage: UsageMetrics | null;
  assistantUsage: UsageMetrics | null;
  startedAtMs: number;
}

type ComposerMode = 'text' | 'image' | 'hidden';

interface UiPolicy {
  composerMode: ComposerMode;
  showExport: boolean;
  showClear: boolean;
}

type TokenHistoryTab = 'session' | 'today' | 'all_time';
type VoiceMode = 'realtime' | 'turn' | 'transcribe' | 'tts';
type MediaMode = 'image' | 'video';
type SidebarSectionKey = 'files' | 'history';
type WorkspaceLaneKey = 'left' | 'center' | 'right';
type RenderMathFn = (element: HTMLElement, options?: unknown) => void;

@Component({
  selector: 'app-shell-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    A11yModule,
    DragDropModule,
    CdkVirtualScrollViewport,
    CdkFixedSizeVirtualScroll,
    CdkVirtualForOf,
    ShellVisualTabComponent,
    ShellUsagePanelComponent,
    TextInputDialogComponent,
  ],
  templateUrl: './shell-page.component.html',
  styleUrls: [
    './shell-page.layout.css',
    './shell-page.sidebar.css',
    './shell-page.branding.css',
    './shell-page.messages.css',
    './shell-page.composer.css',
    './shell-page.voice.css',
    './shell-page.content.css',
    './shell-page.tools.css',
    './shell-page.responsive.css',
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    { provide: SHELL_PAGE_VM, useExisting: forwardRef(() => ShellPageComponent) },
  ],
})
export class ShellPageComponent implements OnInit, OnDestroy, ShellPageVm {
  private static readonly REASONING_WIDTH_MIN_PX = 180;
  private static readonly REASONING_WIDTH_MAX_PX = 420;
  private static readonly REASONING_WIDTH_STEP_PX = 8;
  private static readonly REASONING_WIDTH_STEP_LARGE_PX = 32;
  private static readonly SIDEBAR_SPLIT_MIN_PCT = 20;
  private static readonly SIDEBAR_SPLIT_MAX_PCT = 80;
  private static readonly SIDEBAR_SPLIT_STEP_PCT = 2;
  private static readonly SIDEBAR_SPLIT_STEP_LARGE_PCT = 8;
  private static readonly SCROLL_AFTER_LAYOUT_MS = 120;
  private static readonly SCROLL_AFTER_RENDER_MS = 600;
  private static readonly MATH_RENDER_DEBOUNCE_MS = 80;
  private static readonly CREATE_PROMPT_PRESET_OPTION = '__create_prompt_preset__';
  private static readonly MAX_VISIBLE_ACTIVE_SESSIONS = 10;
  private static readonly WEB_SEARCH_SELECTIONS_KEY = 'elm_web_search_by_use_case_v1';
  private static readonly HIDDEN_TOP_LEVEL_USE_CASES = new Set(['audio', 'transcription', 'tts', 'video']);
  private static readonly PREFERRED_USE_CASE_ORDER = [
    'general',
    'reasoning',
    'deep',
    'coding',
    'search',
    'computer',
    'voice',
    'image',
    'embeddings',
  ];

  private static readonly USE_CASE_LABEL_OVERRIDES: Record<string, string> = {
    general: 'Chat & Reasoning',
    reasoning: 'Pure Reasoning',
    deep: 'Deep research',
    coding: 'Coding',
    search: 'Search',
    computer: 'Computer agents',
    voice: 'Voice & Audio',
    image: 'Visual Media',
    embeddings: 'Embeddings',
  };

  private static readonly PROMPT_ENABLED_USE_CASES = new Set(['general', 'reasoning', 'deep', 'coding', 'voice', 'audio']);
  private static readonly RESPONSE_ACTION_USE_CASES = new Set(['general', 'reasoning', 'deep', 'coding', 'search', 'computer', 'transcription']);
  private static readonly DEEP_RESEARCH_DISABLED_TOOLS = new Set(['fileSearch', 'mcp']);
  private static readonly DEEP_RESEARCH_DISABLED_REASON = 'Disabled by University';
  private static readonly USE_CASE_ROUTE_MAP: Record<string, string> = {
    general: '/chat-reasoning',
    reasoning: '/pure-reasoning',
    deep: '/deep-research',
    coding: '/coding',
    search: '/search',
    computer: '/computer-agents',
    voice: '/voice-audio/realtime',
    image: '/visual-media',
    embeddings: '/embeddings',
  };
  private static readonly VOICE_MODE_ROUTE_MAP: Record<VoiceMode, string> = {
    realtime: '/voice-audio/realtime',
    turn: '/voice-audio/turn-based',
    transcribe: '/voice-audio/transcribe',
    tts: '/voice-audio/speech',
  };
  private readonly visualService = inject(VisualService);

  readonly loading = signal(true);
  readonly loadingSession = signal(false);
  readonly sending = signal(false);
  readonly stopRequested = signal(false);
  readonly error = signal('');
  readonly sessions = signal<SessionSummary[]>([]);
  readonly messages = signal<SessionMessage[]>([]);
  readonly attachments = signal<AttachmentRecord[]>([]);
  readonly selectedSessionId = signal('');
  readonly selectedUseCase = signal('general');
  readonly selectedTier = signal('standard');
  readonly selectedModel = signal('gpt-5.4-mini');
  readonly selectedThinkingLevel = signal('medium');
  readonly tiers = signal<string[]>([]);
  readonly useCases = signal<string[]>([]);
  readonly modelsForUseCase = signal<string[]>([]);
  readonly thinkingLevelsForModel = signal<ThinkingLevelOption[]>([]);
  readonly messageInput = signal('');
  readonly title = signal('Angular 21 Migration Chat');
  readonly promptPresets = signal<PromptPreset[]>([]);
  readonly promptText = signal('');
  readonly contextText = signal('');
  readonly promptPresetId = signal('');
  readonly promptDropdownValue = signal('');
  readonly showPromptPresetModal = signal(false);
  readonly promptPresetFormId = signal('');
  readonly promptPresetFormName = signal('');
  readonly promptPresetFormInstructions = signal('');
  readonly promptPresetFormContext = signal('');
  readonly promptPresetSaving = signal(false);
  readonly savingSetup = signal(false);
  readonly voiceMode = signal<VoiceMode>('realtime');
  readonly mediaMode = signal<MediaMode>('image');
  readonly usageView = signal<UsageView | null>(null);
  readonly loadingUsage = signal(false);
  readonly voiceStatus = signal('');
  readonly realtimeConnected = signal(false);
  readonly realtimeMuted = signal(false);
  readonly turnRecorderState = signal<'idle' | 'recording' | 'ready'>('idle');
  readonly transcribeRecorderState = signal<'idle' | 'recording'>('idle');
  readonly ttsText = signal('');
  readonly ttsModel = signal('gpt-4o-mini-tts');
  readonly ttsVoice = signal('alloy');
  readonly ttsAudioUrl = signal('');
  readonly ttsBusy = signal(false);
  readonly audioTurnModel = signal('gpt-audio-mini');
  readonly audioTurnVoice = signal('ash');
  readonly transcriptionModel = signal('gpt-4o-mini-transcribe');
  readonly settingsModelInput = signal('');
  readonly settingsEffortInput = signal('');
  readonly settingsStatus = signal('');
  readonly usageHistory = signal<UsageHistoryResponse | null>(null);
  readonly loadingUsageHistory = signal(false);
  readonly modelCatalogRaw = signal<ModelCatalogPayload | null>(null);
  readonly catalogView = signal<VmCatalogView | null>(null);
  readonly mcpProfiles = signal<DeepResearchMcpProfile[]>([]);
  readonly mcpProfilesLoading = signal(false);
  readonly mcpProfilesError = signal('');
  readonly deepResearchTools = signal<DeepResearchToolsSelection & { mcpProfileId: string }>({
    webSearch: true,
    codeInterpreter: true,
    fileSearch: false,
    mcp: false,
    mcpProfileId: '',
  });
  readonly toolsStatus = signal('');
  readonly embeddingModel = signal('text-embedding-3-large');
  readonly embedTextInput = signal('');
  readonly embedQueryInput = signal('');
  readonly embedTopK = signal(8);
  readonly embedSearchResult = signal('');
  readonly embedTextBusy = signal(false);
  readonly embedIndexBusy = signal(false);
  readonly embedSearchBusy = signal(false);
  readonly computerModel = signal('computer-use-preview');
  readonly computerPrompt = signal('');
  readonly computerStartUrl = signal('');
  readonly computerRun = signal<ComputerRunSnapshot | null>(null);
  readonly imagePrompt = this.visualService.imagePrompt;
  readonly imageEditInstruction = this.visualService.imageEditInstruction;
  readonly imageModel = this.visualService.imageModel;
  readonly imageModeration = this.visualService.imageModeration;
  readonly imageStyle = this.visualService.imageStyle;
  readonly imageSize = this.visualService.imageSize;
  readonly imageCount = this.visualService.imageCount;
  readonly imageStatus = this.visualService.imageStatus;
  readonly imageActionBusy = this.visualService.imageActionBusy;
  readonly imageActionPending = this.visualService.imageActionPending;
  readonly imageResults = this.visualService.imageResults;
  readonly imageProjects = this.visualService.imageProjects;
  readonly imageProjectName = this.visualService.imageProjectName;
  readonly imageProjectFilterId = this.visualService.imageProjectFilterId;
  readonly imageWorkspaceItems = this.visualService.imageWorkspaceItems;
  readonly selectedWorkspaceKey = this.visualService.selectedWorkspaceKey;
  readonly imagePromptHistoryItems = this.visualService.imagePromptHistoryItems;
  readonly showArchivedSessions = signal(false);
  readonly renamingSessionId = signal('');
  readonly renameDraft = signal('');
  readonly uploadingFiles = signal(false);
  readonly sessionBusyId = signal('');
  readonly attachmentBusyIds = signal<Record<string, boolean>>({});
  readonly collapsedAssistant = signal<Record<string, boolean>>({});
  readonly collapsedReasoningPane = signal<Record<string, boolean>>({});
  readonly copyFeedback = signal<Record<string, boolean>>({});
  readonly activeResponseDownloadMenuKey = signal('');
  readonly runtimeAttribution = signal('');
  readonly showTokenHistoryModal = signal(false);
  readonly tokenHistoryTab = signal<TokenHistoryTab>('session');
  readonly openSessionMenuId = signal('');
  readonly sidebarSections = signal<SidebarSectionKey[]>(['files', 'history']);
  readonly workspaceLanes = signal<WorkspaceLaneKey[]>(['left', 'center', 'right']);
  readonly layoutLocked = signal(true);
  readonly autoArchiving = signal(false);
  readonly filesPanelCollapsed = signal(false);
  readonly historyPanelCollapsed = signal(false);
  readonly filesSectionHeightPct = signal(35);
  readonly usagePanelCollapsed = signal(false);
  readonly sidebarCollapsed = signal(false);
  readonly showArchivedChatsModal = signal(false);
  readonly showTextInputDialog = signal(false);
  readonly textInputDialogTitle = signal('');
  readonly textInputDialogPlaceholder = signal('');
  readonly textInputDialogConfirmLabel = signal('OK');
  readonly textInputDialogValue = signal('');
  readonly assistantReasoningWidthPx = signal(280);
  readonly thinkingDots = signal('.');
  @ViewChild('shellRoot', { static: true }) private shellRootRef?: ElementRef<HTMLElement>;
  @ViewChild('messagesContainer') private messagesContainerRef?: ElementRef<HTMLDivElement>;
  @ViewChild(CdkVirtualScrollViewport) private messagesViewport?: CdkVirtualScrollViewport;

  private _catalog: ModelCatalogPayload = {};
  private _thinkingEnabledUseCases = new Set<string>();
  private _thinkingDefaultLevels: ThinkingLevelOption[] = [];
  private _thinkingLevelsByPrefix: Record<string, ThinkingLevelOption[]> = {};
  private _thinkingSelectionByUseCase: Record<string, string> = {};
  private _selectedTierByScope: Record<string, string> = {};
  private _selectedModelByScope: Record<string, string> = {};
  private _selectedSessionIdByScope: Record<string, string> = {};
  private _composerDraftByScope: Record<string, string> = {};
  private _showArchivedByScope: Record<string, boolean> = {};
  private _includeWebSearchByUseCase: Record<string, boolean> = {};
  private _reasoningResizeActive = false;
  private _reasoningResizeStartX = 0;
  private _reasoningResizeStartWidth = 280;
  private _reasoningResizeMaxWidth = 420;
  private _sidebarResizeActive = false;
  private _sidebarResizeStartY = 0;
  private _sidebarResizeStartTopPct = 35;
  private _sidebarResizeTopSection: SidebarSectionKey = 'files';
  private _sidebarResizeContainerHeight = 1;
  private _realtimeMicStream: MediaStream | null = null;
  private _realtimePc: RTCPeerConnection | null = null;
  private _realtimeDc: RTCDataChannel | null = null;
  private _realtimeRemoteAudio: HTMLAudioElement | null = null;
  private _realtimeTranscriptionModel = 'gpt-4o-mini-transcribe';
  private _realtimeTurn: RealtimeTurnState = this._blankRealtimeTurn();
  private _activeRecorder: MediaRecorder | null = null;
  private _activeRecorderMode: 'turn' | 'transcribe' | null = null;
  private _recordedChunks: Blob[] = [];
  private _pendingTurnRecordingFile: File | null = null;
  private _activeChatAbortController: AbortController | null = null;
  private _activeStreamToken: symbol | null = null;
  private _thinkingTicker: ReturnType<typeof setInterval> | null = null;
  private _stopFeedbackTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly _scrollTimeouts: ReturnType<typeof setTimeout>[] = [];
  private readonly _renderMath$ = new Subject<HTMLElement>();
  private _renderMathInElement: RenderMathFn | null = null;
  private _renderMathLoader: Promise<void> | null = null;
  private readonly destroyRef = inject(DestroyRef);
  private readonly catalogService = inject(CatalogService);
  private readonly sessionService = inject(SessionService);
  private readonly attachmentService = inject(AttachmentService);
  private readonly voiceService = inject(VoiceService);
  private readonly computerService = inject(ComputerService);
  private _textInputDialogMode: '' | 'create_project' | 'rename_project' = '';
  private _textInputDialogRenameProjectId = '';

  constructor(
    private readonly api: BackendApiService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this._includeWebSearchByUseCase = this._loadWebSearchByUseCase();
    this._renderMath$
      .pipe(debounceTime(ShellPageComponent.MATH_RENDER_DEBOUNCE_MS), takeUntilDestroyed(this.destroyRef))
      .subscribe((root) => {
        void this._renderMathInAssistantResponses(root);
      });
    this._loadInitial();
    this.route.data.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((data) => {
      const routeUseCase = this._normalizeTopLevelUseCase(String(data?.['useCase'] || this.selectedUseCase() || 'general'));
      const routeVoiceMode = String(data?.['voiceMode'] || '').trim();
      this._applyRouteContext(routeUseCase, routeVoiceMode);
    });
    this.router.events.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((event) => {
      if (!(event instanceof NavigationEnd)) return;
      const activeUseCase = this.selectedUseCase();
      if (activeUseCase === 'deep') {
        void this.loadMcpProfiles();
      } else if (activeUseCase === 'image' && this.imageProjects().length === 0) {
        void this.loadImageProjects();
      }
    });
    this._scheduleDeferredMessagesScrollToEnd();
  }

  ngOnDestroy(): void {
    this._scrollTimeouts.forEach((timeoutId) => clearTimeout(timeoutId));
    this._scrollTimeouts.length = 0;
    this._clearStopFeedbackTimer();
    this.stopResponse();
    this.endRealtimeSession();
    this._stopActiveRecorder(false);
  }

  private _scheduleDeferredMessagesScrollToEnd(): void {
    this._scrollTimeouts.push(
      setTimeout(() => this._scheduleMessagesScrollToEnd(), ShellPageComponent.SCROLL_AFTER_LAYOUT_MS),
      setTimeout(() => this._scheduleMessagesScrollToEnd(), ShellPageComponent.SCROLL_AFTER_RENDER_MS),
    );
  }

  private _scheduleMessagesScrollToEnd(): void {
    requestAnimationFrame(() => {
      const totalMessages = this.messages().length;
      if (this.messagesViewport && totalMessages > 0) {
        this.messagesViewport.scrollToIndex(totalMessages - 1, 'auto');
      }
      const node = this.messagesContainerRef?.nativeElement;
      if (!node) return;
      node.scrollTop = node.scrollHeight;
      this._scheduleMathRender(node);
    });
  }

  trackByMessageId = (_index: number, message: SessionMessage): number | string => message.id;

  private _scheduleMathRender(root: HTMLElement): void {
    this._renderMath$.next(root);
  }

  private _scheduleMathRenderForMessagesContainer(): void {
    const node = this.messagesContainerRef?.nativeElement;
    if (!node) return;
    this._scheduleMathRender(node);
  }

  private async _ensureRenderMathInElement(): Promise<RenderMathFn | null> {
    if (this._renderMathInElement) return this._renderMathInElement;
    if (!this._renderMathLoader) {
      this._renderMathLoader = import('katex/contrib/auto-render')
        .then((module) => {
          this._renderMathInElement = (module?.default || null) as RenderMathFn | null;
        })
        .catch(() => {
          this._renderMathInElement = null;
        })
        .finally(() => {
          this._renderMathLoader = null;
        });
    }
    await this._renderMathLoader;
    return this._renderMathInElement;
  }

  private async _renderMathInAssistantResponses(root: HTMLElement): Promise<void> {
    const renderMathInElement = await this._ensureRenderMathInElement();
    if (typeof renderMathInElement !== 'function') return;
    const responseNodes = root.querySelectorAll<HTMLElement>('.assistant-response-main .message-content');
    responseNodes.forEach((element) => {
      renderMathInElement(element, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false },
          { left: '$', right: '$', display: false },
        ],
        throwOnError: false,
      });
    });
  }

  async sendMessage(): Promise<void> {
    const policy = this.uiPolicy();
    if (policy.composerMode === 'hidden') return;
    const text = this.messageInput().trim();
    if (!text || this.interactionLocked()) return;
    if (policy.composerMode === 'image') {
      this.imagePrompt.set(text);
      this.messageInput.set('');
      this._composerDraftByScope[this._scopeKey()] = '';
      this.runImageGenerate();
      return;
    }
    this.error.set('');
    this.stopRequested.set(false);
    this._clearStopFeedbackTimer();
    this.sending.set(true);
    this._startThinkingTicker();
    const streamToken = Symbol('chat-stream');
    this._activeStreamToken = streamToken;
    this._activeChatAbortController = new AbortController();
    const abortController = this._activeChatAbortController;

    const sessionId = this._ensureSessionId();
    const scopeKey = this._scopeKey();

    const optimisticMessages = [...this.messages()];
    optimisticMessages.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      msgType: 'text',
      status: 'complete',
    });
    optimisticMessages.push({
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      msgType: 'text',
      status: 'pending',
      reasoningStatus: 'pending',
    });
    this.messages.set(optimisticMessages);
    this._scheduleMessagesScrollToEnd();
    this.messageInput.set('');

    const assistantIndex = optimisticMessages.length - 1;
    try {
      await this.api.streamChat(
        {
          sessionId,
          userText: text,
          model: this.selectedModel(),
          useCase: scopeKey,
          effort: this.effectiveThinkingEffort(),
          includeWebSearch: this.includeWebSearchPayloadValue(),
          deepResearchTools: scopeKey === 'deep' ? this._deepResearchSelectionPayload() : undefined,
          deepResearchMcpProfileId: scopeKey === 'deep' ? this._deepResearchMcpProfilePayload() : undefined,
        },
        (event) => {
          if (this._activeStreamToken !== streamToken || abortController.signal.aborted) return;
          if (event.error) {
            this.error.set(event.error);
            return;
          }
          if (typeof event.content === 'string') {
            const nextMessages = [...this.messages()];
            const target = nextMessages[assistantIndex];
            if (target) {
              target.content = `${target.content || ''}${event.content}`;
              target.status = 'streaming';
            }
            this.messages.set(nextMessages);
            this._scheduleMessagesScrollToEnd();
          }
          if (event.reasoning && typeof event.reasoning === 'object') {
            const nextMessages = [...this.messages()];
            const target = nextMessages[assistantIndex];
            if (target) {
              if (typeof event.reasoning.summary === 'string') target.reasoningSummary = event.reasoning.summary;
              if (typeof event.reasoning.status === 'string') target.reasoningStatus = event.reasoning.status;
            }
            this.messages.set(nextMessages);
            this._scheduleMessagesScrollToEnd();
          }
          if (event.usageView) {
            this.usageView.set(event.usageView);
          }
          if (event.done) {
            const nextMessages = [...this.messages()];
            const target = nextMessages[assistantIndex];
            if (target && !target.content) {
              target.content = '[No content returned]';
            }
            if (target) {
              target.status = 'complete';
              if (!target.reasoningStatus) target.reasoningStatus = 'complete';
            }
            this.messages.set(nextMessages);
            this._scheduleMessagesScrollToEnd();
          }
        },
        abortController.signal,
      );
      if (this._activeStreamToken !== streamToken || abortController.signal.aborted) {
        return;
      }
      this._composerDraftByScope[scopeKey] = '';
      await this.refreshSessions();
      await this.loadSession(sessionId);
      await this.loadUsage();
    } catch (error) {
      if ((error as { name?: string })?.name === 'AbortError') return;
      this.error.set(this._errorMessage(error));
    } finally {
      if (this._activeStreamToken === streamToken) {
        this._activeStreamToken = null;
        this._activeChatAbortController = null;
        this.sending.set(false);
        this._stopThinkingTicker();
      }
    }
  }

  stopResponse(event?: Event): void {
    event?.stopPropagation();
    if (!this.sending()) return;
    this.stopRequested.set(true);
    this._clearStopFeedbackTimer();
    this._stopFeedbackTimer = setTimeout(() => {
      this.stopRequested.set(false);
      this._stopFeedbackTimer = null;
    }, 1200);
    const nextMessages = [...this.messages()];
    for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
      const message = nextMessages[index];
      if (message.role !== 'assistant') continue;
      if (message.status === 'pending' || message.status === 'streaming') {
        message.status = 'interrupted';
        if (!message.content?.trim()) {
          message.content = '[Response stopped]';
        }
        if (!message.reasoningStatus || message.reasoningStatus === 'pending' || message.reasoningStatus === 'streaming') {
          message.reasoningStatus = 'unavailable';
        }
      }
      break;
    }
    this.messages.set(nextMessages);
    this._scheduleMessagesScrollToEnd();
    this._activeStreamToken = null;
    this._activeChatAbortController?.abort();
    this._activeChatAbortController = null;
    this.sending.set(false);
    this._stopThinkingTicker();
  }

  async startNewSession(): Promise<void> {
    const scopeKey = this._scopeKey();
    this.selectedSessionId.set('');
    this._selectedSessionIdByScope[scopeKey] = '';
    this.messages.set([]);
    this._refreshImageWorkspaceItems();
    this.attachments.set([]);
    this.title.set('New chat');
    this.error.set('');
    this.usageView.set(null);
    this.promptText.set('');
    this.contextText.set('');
    this.promptPresetId.set('');
    this._syncPromptDropdownValue();
    this.messageInput.set(this._composerDraftByScope[scopeKey] || '');
    this.renamingSessionId.set('');
    this.renameDraft.set('');
    this.collapsedAssistant.set({});
    this.collapsedReasoningPane.set({});
    this.activeResponseDownloadMenuKey.set('');
  }

  async loadSession(sessionId: string, options?: { syncRoute?: boolean }): Promise<void> {
    if (!sessionId) return;
    this.closeSessionMenu();
    this.loadingSession.set(true);
    this.error.set('');
    this.selectedSessionId.set(sessionId);
    const shouldSyncRoute = options?.syncRoute === true;
    const view = await this.sessionService.loadSession(sessionId);
    if (view) {
        const normalizedUseCase = this._normalizeTopLevelUseCase(view?.useCase || this.selectedUseCase());
        const nextVoiceMode = normalizedUseCase === 'voice' ? this._voiceModeForUseCase(view?.useCase || 'voice') : this.voiceMode();
        const sessionScopeKey = this._scopeKeyFromUseCase(view?.useCase || this._effectiveUseCaseKey());
        this.title.set(view?.title || 'Untitled chat');
        this.messages.set(view?.messages || []);
        this._scheduleMessagesScrollToEnd();
        this.attachments.set(view?.attachments || []);
        this.attachmentService.setAttachments(view?.attachments || []);
        this._selectedSessionIdByScope[sessionScopeKey] = sessionId;
        if (!shouldSyncRoute && sessionScopeKey === this._scopeKey()) {
          this.selectedSessionId.set(sessionId);
        }
        if (shouldSyncRoute) {
          this.selectedUseCase.set(normalizedUseCase);
          if (normalizedUseCase === 'voice') this.voiceMode.set(nextVoiceMode);
        }
        this.promptText.set(view?.prompt || '');
        this.contextText.set(view?.context || '');
        this.promptPresetId.set(view?.promptPresetId || '');
        this._syncPromptDropdownValue();
        this._refreshImageWorkspaceItems();
        this._syncModelsForUseCase();
        if (shouldSyncRoute) {
          this._navigateToUseCase(normalizedUseCase, normalizedUseCase === 'voice' ? nextVoiceMode : undefined);
        }
        this.loadingSession.set(false);
        this.closeResponseDownloadMenu();
        void this.loadUsage();
        this.refreshCatalogView();
        return;
    }
    this.error.set(this.sessionService.error() || `Failed to load session ${sessionId}.`);
    this.loadingSession.set(false);
  }

  onUseCaseChange(): void {
    const normalized = this._normalizeTopLevelUseCase(this.selectedUseCase());
    const mode = normalized === 'voice' && this._isVoiceMode(this.voiceMode()) ? this.voiceMode() : 'realtime';
    this._navigateToUseCase(normalized, mode);
  }

  onTierChange(tier: string): void {
    this.selectedTier.set(tier);
    const scopeKey = this._scopeKey();
    this._selectedTierByScope[scopeKey] = tier;
    this._selectedModelByScope[scopeKey] = '';
    this._syncModelsForUseCase();
    this._rememberModelSelectionForScope();
    this._updateThinkingLevelsForModel();
    this._rememberThinkingSelectionForUseCase();
    void this.loadUsage();
    this.refreshCatalogView();
  }

  showThinkingControl(): boolean {
    return this.selectedUseCase() === 'deep' || this._thinkingEnabledUseCases.has(this.selectedUseCase());
  }

  showDeepResearchToolControl(): boolean {
    return this.selectedUseCase() === 'deep';
  }

  showDeepResearchMcpProfileControl(): boolean {
    return this.showDeepResearchToolControl() && !!this.deepResearchTools().mcp;
  }

  deepResearchToolControlDisabled(): boolean {
    return this.interactionLocked();
  }

  deepResearchDataSourceSelected(): boolean {
    return !!this.deepResearchTools().webSearch || !!this.deepResearchTools().fileSearch || !!this.deepResearchTools().mcp;
  }

  deepResearchToolHint(): string {
    if (!this.showDeepResearchToolControl()) return '';
    if (!this.deepResearchDataSourceSelected()) {
      if (this.isDeepResearchToolBlocked('fileSearch') && this.isDeepResearchToolBlocked('mcp')) {
        return 'Select at least one data source: Web. Files and MCP are disabled by University.';
      }
      return 'Select at least one data source: Web, Files, or MCP.';
    }
    return 'Choose which tools deep research can use for this request.';
  }

  isDeepResearchToolBlocked(key: keyof DeepResearchToolsSelection): boolean {
    return ShellPageComponent.DEEP_RESEARCH_DISABLED_TOOLS.has(key);
  }

  deepResearchToolDisabled(key: keyof DeepResearchToolsSelection): boolean {
    if (this.deepResearchToolControlDisabled()) return true;
    return this.isDeepResearchToolBlocked(key);
  }

  deepResearchToolTitle(key: keyof DeepResearchToolsSelection): string {
    if (this.isDeepResearchToolBlocked(key)) return ShellPageComponent.DEEP_RESEARCH_DISABLED_REASON;
    return '';
  }

  deepResearchMcpProfileHint(): string {
    if (!this.showDeepResearchMcpProfileControl()) return '';
    if (this.mcpProfilesLoading()) return 'Loading MCP profiles...';
    if (this.mcpProfiles().length === 0) return 'No MCP profiles configured on server.';
    return 'Select which MCP profile (Python script server) to use.';
  }

  toggleDeepResearchTool(key: keyof DeepResearchToolsSelection, event?: Event): void {
    if (event) event.stopPropagation();
    if (!this.showDeepResearchToolControl() || this.deepResearchToolDisabled(key)) return;
    const next = { ...this.deepResearchTools(), [key]: !this.deepResearchTools()[key] };
    if (key === 'mcp' && next.mcp) this._ensureDeepResearchMcpProfileSelection(next);
    this.deepResearchTools.set(next);
  }

  onDeepResearchMcpProfileChange(profileId: string): void {
    const next = { ...this.deepResearchTools(), mcpProfileId: String(profileId || '').trim() };
    this._ensureDeepResearchMcpProfileSelection(next);
    this.deepResearchTools.set(next);
  }

  onThinkingChange(level: string): void {
    this.selectedThinkingLevel.set(String(level || '').trim());
    this._clampThinkingLevel();
    this._rememberThinkingSelectionForUseCase();
  }

  showPromptControl(): boolean {
    return this._supportsPromptSetupForUseCase(this.selectedUseCase());
  }

  selectedPromptPreset(): PromptPreset | null {
    const target = this.promptPresetId();
    if (!target) return null;
    return this.promptPresets().find((preset) => preset.id === target) || null;
  }

  hasSelectedPromptPreset(): boolean {
    return !!this.selectedPromptPreset();
  }

  promptModalTitle(): string {
    return this.promptPresetFormId() ? 'Edit prompt' : 'Create prompt';
  }

  canSavePromptPresetForm(): boolean {
    const name = String(this.promptPresetFormName() || '').trim();
    const instructions = String(this.promptPresetFormInstructions() || '').trim();
    const context = String(this.promptPresetFormContext() || '').trim();
    return !this.promptPresetSaving() && !this.requestPending() && !!name && !!(instructions || context);
  }

  onPromptPresetChange(value: string): void {
    if (this.requestPending()) return;
    if (!this.showPromptControl()) return;
    if (value === ShellPageComponent.CREATE_PROMPT_PRESET_OPTION) {
      this.openCreatePromptPresetModal();
      return;
    }
    this.promptPresetId.set(String(value || '').trim());
    this._syncPromptDropdownValue();
    if (this.selectedSessionId()) this.savePromptSetup();
  }

  openCreatePromptPresetModal(event?: Event): void {
    if (event) event.stopPropagation();
    if (this.requestPending()) return;
    this.showPromptPresetModal.set(true);
    this.promptPresetFormId.set('');
    this.promptPresetFormName.set('');
    this.promptPresetFormInstructions.set('');
    this.promptPresetFormContext.set('');
    this._syncPromptDropdownValue();
  }

  openEditPromptPresetModal(event?: Event): void {
    if (event) event.stopPropagation();
    if (this.requestPending()) return;
    const preset = this.selectedPromptPreset();
    if (!preset) return;
    this.showPromptPresetModal.set(true);
    this.promptPresetFormId.set(preset.id);
    this.promptPresetFormName.set(preset.name);
    this.promptPresetFormInstructions.set(preset.instructions);
    this.promptPresetFormContext.set(preset.context || '');
    this._syncPromptDropdownValue();
  }

  closePromptPresetModal(event?: Event): void {
    if (event) event.stopPropagation();
    this.showPromptPresetModal.set(false);
    this.promptPresetFormId.set('');
    this.promptPresetFormName.set('');
    this.promptPresetFormInstructions.set('');
    this.promptPresetFormContext.set('');
    this._syncPromptDropdownValue();
  }

  savePromptPreset(event?: Event): void {
    if (event) event.stopPropagation();
    if (!this.canSavePromptPresetForm()) return;
    const name = String(this.promptPresetFormName() || '').trim();
    const instructions = String(this.promptPresetFormInstructions() || '').trim();
    const context = String(this.promptPresetFormContext() || '').trim();
    this.promptPresetSaving.set(true);
    const presetId = this.promptPresetFormId();
    const request$ = presetId
      ? this.api.updatePromptPreset(presetId, { name, instructions, context })
      : this.api.createPromptPreset({ name, instructions, context });
    request$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        const preset = payload?.preset;
        if (!preset?.id) {
          this.promptPresetSaving.set(false);
          return;
        }
        const next = [
          ...this.promptPresets().filter((item) => item.id !== preset.id),
          preset,
        ].sort((a, b) => a.name.localeCompare(b.name));
        this.promptPresets.set(next);
        this.promptPresetId.set(preset.id);
        this.promptPresetSaving.set(false);
        this.closePromptPresetModal();
        if (this.selectedSessionId()) this.savePromptSetup();
      },
      error: (error: unknown) => {
        this.promptPresetSaving.set(false);
        this.error.set(this._errorMessage(error));
      },
    });
  }

  deletePromptPreset(event?: Event): void {
    if (event) event.stopPropagation();
    const presetId = this.promptPresetFormId();
    if (!presetId || this.promptPresetSaving()) return;
    this.promptPresetSaving.set(true);
    this.api.deletePromptPreset(presetId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.promptPresetSaving.set(false);
        this.promptPresets.set(this.promptPresets().filter((item) => item.id !== presetId));
        if (this.promptPresetId() === presetId) {
          this.promptPresetId.set('');
          if (this.selectedSessionId()) this.savePromptSetup();
        }
        this.closePromptPresetModal();
      },
      error: (error: unknown) => {
        this.promptPresetSaving.set(false);
        this.error.set(this._errorMessage(error));
      },
    });
  }

  onModelChange(model: string): void {
    this.selectedModel.set(model);
    this._rememberModelSelectionForScope();
    this._syncVoiceActionModelsFromSelected();
    this._syncVoiceOptionsForSelectedModel();
    this._updateThinkingLevelsForModel();
    this._rememberThinkingSelectionForUseCase();
    void this.loadUsage();
    this.refreshCatalogView();
  }

  onVoiceModeChange(mode: string): void {
    const next = this._isVoiceMode(mode) ? mode : 'realtime';
    this._navigateToUseCase('voice', next);
  }

  onAudioTurnModelChange(model: string): void {
    const normalized = String(model || '').trim();
    this.audioTurnModel.set(normalized || 'gpt-audio-mini');
    if (this._effectiveUseCaseKey() !== 'audio') return;
    this.selectedModel.set(this.audioTurnModel());
    this._syncVoiceOptionsForSelectedModel();
    void this.loadUsage();
    this.refreshCatalogView();
  }

  onTranscriptionModelChange(model: string): void {
    const normalized = String(model || '').trim();
    this.transcriptionModel.set(normalized || 'gpt-4o-mini-transcribe');
    if (this._effectiveUseCaseKey() !== 'transcription') return;
    this.selectedModel.set(this.transcriptionModel());
    void this.loadUsage();
    this.refreshCatalogView();
  }

  onTtsModelChange(model: string): void {
    const normalized = String(model || '').trim();
    this.ttsModel.set(normalized || 'gpt-4o-mini-tts');
    if (this._effectiveUseCaseKey() !== 'tts') return;
    this.selectedModel.set(this.ttsModel());
    this._syncVoiceOptionsForSelectedModel();
    void this.loadUsage();
    this.refreshCatalogView();
  }

  refreshCatalogView(): void {
    void this.catalogService
      .refreshCatalogView(this.effectiveModelForPricing(), this.voiceMode())
      .then(() => this.catalogView.set(this.catalogService.catalogView()));
  }

  savePromptSetup(): void {
    const sessionId = this.selectedSessionId();
    if (!sessionId || this.savingSetup()) return;
    this.error.set('');
    this.savingSetup.set(true);
    this.api
      .updateSessionSetup(sessionId, {
        useCase: this.selectedUseCase(),
        prompt: this.promptText(),
        context: this.contextText(),
        promptPresetId: this.promptPresetId(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          const view = payload?.sessionView;
          this.promptText.set(view?.prompt || '');
          this.contextText.set(view?.context || '');
          this.promptPresetId.set(view?.promptPresetId || '');
          this._syncPromptDropdownValue();
          this.savingSetup.set(false);
        },
        error: (error: unknown) => {
          this.error.set(this._errorMessage(error));
          this.savingSetup.set(false);
        },
      });
  }

  private _loadInitial(): void {
    forkJoin({
      sessions: this.api.getSessions(),
      catalog: this.api.getVmCatalog(this.selectedModel(), this.voiceMode()),
      presets: this.api.getPromptPresets(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: async ({ sessions, catalog, presets }) => {
        const developerLabel = String(catalog?.developerLabel || '').trim();
        if (!developerLabel) {
          this.error.set('Developer label missing from backend payload.');
          this.loading.set(false);
          return;
        }
        this.runtimeAttribution.set(developerLabel);
        this._catalog = catalog?.catalog || {};
        this._applyThinkingPolicy();
        this.catalogView.set(catalog?.catalogView || null);
        this.catalogService.modelCatalog.set(catalog?.catalog || null);
        this.catalogService.catalogView.set(catalog?.catalogView || null);
        const map = this._catalog.modelMap || {};
        const useCases = this._orderUseCases(Object.keys(map));
        this.useCases.set(useCases);
        const sortedPresets = (presets?.presets || []).sort((a, b) => a.name.localeCompare(b.name));
        this.promptPresets.set(sortedPresets);
        this.catalogService.promptPresets.set(sortedPresets);
        this._syncPromptDropdownValue();

        const defaultUseCase = String(this._catalog.defaults?.useCase || 'general');
        const routeUseCase = this._normalizeTopLevelUseCase(String(this.route.snapshot?.data?.['useCase'] || ''));
        const routeStart = routeUseCase || this.selectedUseCase();
        const startUseCase = this._normalizeTopLevelUseCase(routeStart || defaultUseCase || (useCases[0] || 'general'));
        this.selectedUseCase.set(useCases.includes(startUseCase) ? startUseCase : (useCases[0] || 'general'));
        this._syncModelsForUseCase(catalog?.catalogView?.selectedModel);
        this._syncVoiceOptionsForSelectedModel();
        this._applyThinkingSelectionForUseCase(this.selectedUseCase());
        this.refreshCatalogView();

        const sessionList = sessions?.sessions || [];
        this.sessions.set(sessionList);
        this.sessionService.sessions.set(sessionList);
        await this.enforceActiveSessionWindow();
        this.settingsModelInput.set(this.selectedModel());
        const initialSessions = this.visibleSessions();
        if (initialSessions.length > 0) {
          const remembered = this._selectedSessionIdByScope[this._scopeKey()];
          const candidate = remembered && initialSessions.some((session) => session.id === remembered)
            ? remembered
            : initialSessions[0].id;
          this.selectedSessionId.set(candidate);
          this._selectedSessionIdByScope[this._scopeKey()] = candidate;
          void this.loadSession(candidate);
        } else {
          this.messageInput.set(this._composerDraftByScope[this._scopeKey()] || '');
          void this.loadUsage();
        }
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.error.set(this._errorMessage(error));
        this.loading.set(false);
      },
    });
  }

  async refreshSessions(skipWindowEnforcement = false): Promise<void> {
    const sessions = await this.sessionService.refreshSessions();
    this.sessions.set(sessions || []);
    if (!skipWindowEnforcement && !this.autoArchiving()) {
      await this.enforceActiveSessionWindow();
    }
  }

  async refreshSessionList(): Promise<void> {
    if (this.loadingSession()) return;
    await this.refreshSessions();
    const sessionId = this.selectedSessionId();
    const scopedVisible = this.visibleSessions();
    const scopedSelected = sessionId && scopedVisible.some((session) => session.id === sessionId) ? sessionId : '';
    if (!scopedSelected && scopedVisible.length > 0) {
      const nextId = scopedVisible[0].id;
      this.selectedSessionId.set(nextId);
      this._selectedSessionIdByScope[this._scopeKey()] = nextId;
      await this.loadSession(nextId);
      return;
    }
    if (sessionId) {
      await this.loadSession(sessionId);
      return;
    }
    await this.loadUsage();
  }

  visibleSessions(): SessionSummary[] {
    const includeArchived = this.showArchivedSessions();
    const scopeKey = this._scopeKey();
    const scoped = this.sessions()
      .filter((session) => this._scopeKeyFromUseCase(session.useCase) === scopeKey)
      .slice()
      .sort((a, b) => {
        if ((b.updatedAt || 0) !== (a.updatedAt || 0)) return (b.updatedAt || 0) - (a.updatedAt || 0);
        return (b.createdAt || 0) - (a.createdAt || 0);
      });
    if (includeArchived) return scoped;
    return scoped
      .filter((session) => !session.archivedAt)
      .slice(0, ShellPageComponent.MAX_VISIBLE_ACTIVE_SESSIONS);
  }

  toggleArchivedSessions(): void {
    const next = !this.showArchivedSessions();
    this.showArchivedSessions.set(next);
    this._showArchivedByScope[this._scopeKey()] = next;
    this.closeSessionMenu();
  }

  @HostListener('document:keydown.escape')
  onDocumentEscape(): void {
    this.closeSessionMenu();
    this.closeResponseDownloadMenu();
    this.closeArchivedChatsModal();
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.closeSessionMenu();
    this.closeResponseDownloadMenu();
  }

  openArchivedChatsModal(event?: Event): void {
    event?.stopPropagation();
    this.showArchivedChatsModal.set(true);
  }

  closeArchivedChatsModal(event?: Event): void {
    event?.stopPropagation();
    this.showArchivedChatsModal.set(false);
  }

  archivedSessions(): SessionSummary[] {
    const scopeKey = this._scopeKey();
    return this.sessions()
      .filter((session) => this._scopeKeyFromUseCase(session.useCase) === scopeKey && !!session.archivedAt)
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  }

  activateArchivedSession(session: SessionSummary, event?: Event): void {
    event?.stopPropagation();
    if (this.interactionLocked()) return;
    this.sessionBusyId.set(session.id);
    void this.sessionService.archiveSession(session.id, false)
      .then(() => {
        this.sessionBusyId.set('');
        this.showArchivedChatsModal.set(false);
        void this.refreshSessions().then(() => this.loadSession(session.id));
      })
      .catch((error: unknown) => {
        this.sessionBusyId.set('');
        this.error.set(this._errorMessage(error));
      });
  }

  @HostListener('document:mousemove', ['$event'])
  onDocumentMouseMove(event: MouseEvent): void {
    if (this._reasoningResizeActive) {
      const deltaX = event.clientX - this._reasoningResizeStartX;
      const nextWidth = this._reasoningResizeStartWidth - deltaX;
      const maxWidth = Math.max(
        ShellPageComponent.REASONING_WIDTH_MIN_PX,
        Math.min(this._reasoningResizeMaxWidth, ShellPageComponent.REASONING_WIDTH_MAX_PX),
      );
      this._setAssistantReasoningWidth(nextWidth, maxWidth);
      event.preventDefault();
      return;
    }
    if (this._sidebarResizeActive) {
      const deltaY = event.clientY - this._sidebarResizeStartY;
      const deltaPct = (deltaY / Math.max(1, this._sidebarResizeContainerHeight)) * 100;
      const nextTopPct = this._sidebarResizeStartTopPct + deltaPct;
      this._setSidebarTopSectionPct(nextTopPct);
      event.preventDefault();
    }
  }

  @HostListener('document:mouseup')
  onDocumentMouseUp(): void {
    this.stopReasoningResize();
    this.stopSidebarResize();
  }

  toggleSessionMenu(sessionId: string, event?: Event): void {
    if (event) event.stopPropagation();
    this.openSessionMenuId.set(this.openSessionMenuId() === sessionId ? '' : sessionId);
  }

  closeSessionMenu(event?: Event): void {
    if (event) event.stopPropagation();
    if (!this.openSessionMenuId()) return;
    this.openSessionMenuId.set('');
  }

  isSessionMenuOpen(sessionId: string): boolean {
    return this.openSessionMenuId() === sessionId;
  }

  triggerUpload(input: HTMLInputElement): void {
    input.click();
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    if (files.length === 0 || this.interactionLocked()) return;
    const sessionId = this._ensureSessionId();
    this.uploadingFiles.set(true);
    void this.attachmentService.upload(sessionId, this._scopeKey(), files)
      .then(() => {
        this.uploadingFiles.set(false);
        input.value = '';
        void this.loadSession(sessionId);
        void this.refreshSessions();
      })
      .catch((error: unknown) => {
        this.uploadingFiles.set(false);
        this.error.set(this._errorMessage(error));
      });
  }

  toggleAttachment(attachment: AttachmentRecord, event?: Event): void {
    if (event) event.stopPropagation();
    const sessionId = this.selectedSessionId();
    if (!sessionId || !attachment.usable || this.isAttachmentBusy(attachment.id) || this.interactionLocked()) return;
    this._setAttachmentBusy(attachment.id, true);
    void this.attachmentService.toggle(sessionId, attachment)
      .then(() => {
        this._setAttachmentBusy(attachment.id, false);
        void this.loadSession(sessionId);
      })
      .catch((error: unknown) => {
        this._setAttachmentBusy(attachment.id, false);
        this.error.set(this._errorMessage(error));
      });
  }

  removeAttachment(attachment: AttachmentRecord, event?: Event): void {
    if (event) event.stopPropagation();
    const sessionId = this.selectedSessionId();
    if (!sessionId || this.isAttachmentBusy(attachment.id) || this.interactionLocked()) return;
    this._setAttachmentBusy(attachment.id, true);
    void this.attachmentService.remove(sessionId, attachment.id)
      .then(() => {
        this._setAttachmentBusy(attachment.id, false);
        void this.loadSession(sessionId);
      })
      .catch((error: unknown) => {
        this._setAttachmentBusy(attachment.id, false);
        this.error.set(this._errorMessage(error));
      });
  }

  fileIcon(mimeType: string, fileName: string): string {
    const lowerName = String(fileName || '').toLowerCase();
    const mime = String(mimeType || '').toLowerCase();
    if (lowerName.endsWith('.fig')) return 'bi-filetype-m';
    if (mime.startsWith('image/')) return 'bi-file-image';
    if (mime.startsWith('audio/')) return 'bi-file-music';
    if (mime.startsWith('video/')) return 'bi-file-play';
    if (mime === 'application/pdf') return 'bi-file-pdf';
    if (mime.includes('spreadsheet') || mime.includes('excel')) return 'bi-file-spreadsheet';
    if (mime.includes('word') || mime.includes('document')) return 'bi-file-word';
    if (mime.startsWith('text/')) return 'bi-file-text';
    return 'bi-file-earmark';
  }

  beginRename(session: SessionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    this.closeSessionMenu();
    this.renamingSessionId.set(session.id);
    this.renameDraft.set(session.title || '');
  }

  cancelRename(event?: Event): void {
    if (event) event.stopPropagation();
    this.renamingSessionId.set('');
    this.renameDraft.set('');
  }

  commitRename(session: SessionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    const title = this.renameDraft().trim();
    if (!title || this.interactionLocked()) return;
    this.sessionBusyId.set(session.id);
    void this.sessionService.renameSession(session.id, title)
      .then(() => {
        this.sessionBusyId.set('');
        this.renamingSessionId.set('');
        this.renameDraft.set('');
        void this.refreshSessions();
        if (this.selectedSessionId() === session.id) {
          this.title.set(title);
        }
      })
      .catch((error: unknown) => {
        this.sessionBusyId.set('');
        this.error.set(this._errorMessage(error));
      });
  }

  toggleSessionArchive(session: SessionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    if (this.interactionLocked()) return;
    this.closeSessionMenu();
    const shouldArchive = !session.archivedAt;
    this.sessionBusyId.set(session.id);
    void this.sessionService.archiveSession(session.id, shouldArchive)
      .then(() => {
        this.sessionBusyId.set('');
        void this.refreshSessions();
      })
      .catch((error: unknown) => {
        this.sessionBusyId.set('');
        this.error.set(this._errorMessage(error));
      });
  }

  clearSessionMessages(session: SessionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    if (this.interactionLocked()) return;
    this.sessionBusyId.set(session.id);
    void this.sessionService.clearSession(session.id)
      .then(() => {
        this.sessionBusyId.set('');
        void this.refreshSessions();
        if (this.selectedSessionId() === session.id) {
          void this.loadSession(session.id);
        }
      })
      .catch((error: unknown) => {
        this.sessionBusyId.set('');
        this.error.set(this._errorMessage(error));
      });
  }

  deleteSessionItem(session: SessionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    if (this.interactionLocked()) return;
    this.closeSessionMenu();
    this.sessionBusyId.set(session.id);
    void this.sessionService.deleteSession(session.id)
      .then(() => {
        this.sessionBusyId.set('');
        const wasSelected = this.selectedSessionId() === session.id;
        void this.refreshSessions().then(() => {
          if (!wasSelected) return;
          const next = this.visibleSessions()[0];
          if (next) {
            void this.loadSession(next.id);
          } else {
            void this.startNewSession();
          }
        });
      })
      .catch((error: unknown) => {
        this.sessionBusyId.set('');
        this.error.set(this._errorMessage(error));
      });
  }

  assistantMessageKey(message: SessionMessage): string {
    return `m-${String(message.id)}`;
  }

  responseDownloadMenuKey(message: SessionMessage): string {
    return this.assistantMessageKey(message);
  }

  isAssistantText(message: SessionMessage): boolean {
    return message.role === 'assistant' && (message.msgType || 'text') === 'text';
  }

  showResponseActions(message: SessionMessage): boolean {
    return this.isAssistantText(message) && ShellPageComponent.RESPONSE_ACTION_USE_CASES.has(this._effectiveUseCaseKey());
  }

  shouldShowReasoningPane(message: SessionMessage): boolean {
    return this.showResponseActions(message) && !this.isTranscriptMessage(message);
  }

  thinkingProgressLabel(): string {
    return `Thinking${this.thinkingDots()}`;
  }

  shouldShowThinkingProgress(message: SessionMessage): boolean {
    if (!message || message.role !== 'assistant') return false;
    if (String(message.content || '').trim()) return false;
    const status = String(message.status || '').trim();
    return this.sending() && (status === 'pending' || status === 'streaming' || !status);
  }

  reasoningSummaryText(message: SessionMessage): string {
    const summary = String(message.reasoningSummary || '').trim();
    if (summary) return summary;
    const status = String(message.reasoningStatus || '').trim();
    if (status === 'pending' || status === 'streaming') return this.thinkingProgressLabel();
    if (status === 'unavailable') return 'Reasoning summary unavailable for this turn.';
    if (status === 'error') return 'Reasoning summary failed for this turn.';
    return 'No reasoning summary available.';
  }

  private _startThinkingTicker(): void {
    this._stopThinkingTicker();
    const frames = ['.', '..', '...'];
    let index = 0;
    this.thinkingDots.set(frames[index]);
    this._thinkingTicker = setInterval(() => {
      index = (index + 1) % frames.length;
      this.thinkingDots.set(frames[index]);
    }, 420);
  }

  private _stopThinkingTicker(): void {
    if (this._thinkingTicker) {
      clearInterval(this._thinkingTicker);
      this._thinkingTicker = null;
    }
    this.thinkingDots.set('.');
  }

  toggleResponseCollapse(message: SessionMessage, event?: Event): void {
    if (event) event.stopPropagation();
    const key = this.assistantMessageKey(message);
    const map = { ...this.collapsedAssistant() };
    map[key] = !map[key];
    this.collapsedAssistant.set(map);
    if (!map[key]) this._scheduleMathRenderForMessagesContainer();
    this.closeResponseDownloadMenu();
  }

  isResponseCollapsed(message: SessionMessage): boolean {
    return !!this.collapsedAssistant()[this.assistantMessageKey(message)];
  }

  toggleReasoningPane(message: SessionMessage, event?: Event): void {
    if (event) event.stopPropagation();
    const key = this.assistantMessageKey(message);
    const map = { ...this.collapsedReasoningPane() };
    map[key] = !map[key];
    this.collapsedReasoningPane.set(map);
    this.closeResponseDownloadMenu();
  }

  isReasoningPaneCollapsed(message: SessionMessage): boolean {
    return !!this.collapsedReasoningPane()[this.assistantMessageKey(message)];
  }

  startReasoningResize(event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const handle = event.target as HTMLElement | null;
    const pane = handle?.closest('.assistant-response-pane') as HTMLElement | null;
    if (!pane) return;
    const paneWidth = pane.getBoundingClientRect().width;
    this._reasoningResizeStartX = event.clientX;
    this._reasoningResizeStartWidth = this.assistantReasoningWidthPx();
    this._reasoningResizeMaxWidth = Math.max(220, Math.floor(paneWidth * 0.75));
    this._reasoningResizeActive = true;
  }

  stopReasoningResize(): void {
    if (!this._reasoningResizeActive) return;
    this._reasoningResizeActive = false;
  }

  reasoningResizeAriaValueNow(): number {
    return this.assistantReasoningWidthPx();
  }

  onReasoningResizeKey(event: KeyboardEvent): void {
    const step = event.shiftKey ? ShellPageComponent.REASONING_WIDTH_STEP_LARGE_PX : ShellPageComponent.REASONING_WIDTH_STEP_PX;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      this._setAssistantReasoningWidth(this.assistantReasoningWidthPx() - step, ShellPageComponent.REASONING_WIDTH_MAX_PX);
      return;
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      this._setAssistantReasoningWidth(this.assistantReasoningWidthPx() + step, ShellPageComponent.REASONING_WIDTH_MAX_PX);
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      this._setAssistantReasoningWidth(ShellPageComponent.REASONING_WIDTH_MIN_PX, ShellPageComponent.REASONING_WIDTH_MAX_PX);
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      this._setAssistantReasoningWidth(ShellPageComponent.REASONING_WIDTH_MAX_PX, ShellPageComponent.REASONING_WIDTH_MAX_PX);
    }
  }

  toggleResponseDownloadMenu(message: SessionMessage, event?: Event): void {
    if (event) event.stopPropagation();
    if (!this.showResponseActions(message)) return;
    const key = this.responseDownloadMenuKey(message);
    this.activeResponseDownloadMenuKey.set(this.activeResponseDownloadMenuKey() === key ? '' : key);
  }

  isResponseDownloadMenuOpen(message: SessionMessage): boolean {
    return this.activeResponseDownloadMenuKey() === this.responseDownloadMenuKey(message);
  }

  closeResponseDownloadMenu(): void {
    if (!this.activeResponseDownloadMenuKey()) return;
    this.activeResponseDownloadMenuKey.set('');
  }

  async copyAssistantMessage(message: SessionMessage, event?: Event): Promise<void> {
    if (event) event.stopPropagation();
    if (!this.isAssistantText(message)) return;
    this.closeResponseDownloadMenu();
    const text = String(message.content || '');
    try {
      await navigator.clipboard.writeText(text);
      const key = this.assistantMessageKey(message);
      const map = { ...this.copyFeedback(), [key]: true };
      this.copyFeedback.set(map);
      setTimeout(() => {
        const next = { ...this.copyFeedback() };
        delete next[key];
        this.copyFeedback.set(next);
      }, 1200);
    } catch {
      if (this._legacyCopyToClipboard(text)) {
        const key = this.assistantMessageKey(message);
        const map = { ...this.copyFeedback(), [key]: true };
        this.copyFeedback.set(map);
        setTimeout(() => {
          const next = { ...this.copyFeedback() };
          delete next[key];
          this.copyFeedback.set(next);
        }, 1200);
        return;
      }
      this.error.set('Could not copy message.');
    }
  }

  isCopyFeedbackVisible(message: SessionMessage): boolean {
    return !!this.copyFeedback()[this.assistantMessageKey(message)];
  }

  isTranscriptMessage(message: SessionMessage): boolean {
    if (!this.isAssistantText(message)) return false;
    const payload = message.payload;
    if (!payload || typeof payload !== 'object') return false;
    const segments = payload['transcriptSegments'];
    const timestampsAvailable = payload['timestampsAvailable'];
    return Array.isArray(segments) || typeof timestampsAvailable === 'boolean';
  }

  transcriptSegments(message: SessionMessage): Array<{ startSec: number; endSec: number; text: string }> {
    const payload = message.payload;
    if (!payload || typeof payload !== 'object' || !Array.isArray(payload['transcriptSegments'])) return [];
    return payload['transcriptSegments']
      .map((segment) => ({
        startSec: Number((segment as Record<string, unknown>)['startSec'] || 0),
        endSec: Number((segment as Record<string, unknown>)['endSec'] || 0),
        text: String((segment as Record<string, unknown>)['text'] || ''),
      }))
      .filter((segment) => segment.text.trim().length > 0);
  }

  transcriptHasTimestamps(message: SessionMessage): boolean {
    const payload = message.payload;
    if (!payload || typeof payload !== 'object') return false;
    return payload['hasSegmentTimestamps'] === true && this.transcriptSegments(message).length > 0;
  }

  transcriptTimingNote(message: SessionMessage): string {
    if (this.transcriptHasTimestamps(message)) return '';
    if (this.isTranscriptMessage(message)) return 'Segment timestamps are unavailable for this transcription model.';
    return '';
  }

  formatTranscriptTime(secondsValue: number): string {
    const totalSeconds = Math.max(0, Math.floor(Number(secondsValue) || 0));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const minuteLabel = minutes < 10 ? `0${minutes}` : String(minutes);
    const secondLabel = seconds < 10 ? `0${seconds}` : String(seconds);
    if (hours > 0) return `${hours}:${minuteLabel}:${secondLabel}`;
    return `${minuteLabel}:${secondLabel}`;
  }

  messageCostDisplay(message: SessionMessage): string {
    const value = Number(message.usageCost);
    if (!Number.isFinite(value) || value <= 0) return '';
    return `$${value.toFixed(6)}`;
  }

  thinkingTimerDisplay(message: SessionMessage): string {
    const status = String(message.status || '').toLowerCase();
    if (status === 'pending' || status === 'streaming') {
      const createdAt = Number(message.createdAt);
      const startedAtMs = Number.isFinite(createdAt) && createdAt > 0
        ? createdAt
        : this._assistantMessageTimestampFallback(message);
      if (!Number.isFinite(startedAtMs) || startedAtMs <= 0) return '';
      const elapsed = Math.max(0, (Date.now() - startedAtMs) / 1000);
      return `${elapsed.toFixed(1)}s`;
    }
    const elapsedSec = Number(message.elapsedSec);
    if (!Number.isFinite(elapsedSec) || elapsedSec < 0) return '';
    return `${elapsedSec.toFixed(1)}s`;
  }

  messageElapsedDisplay(message: SessionMessage): string {
    const value = Number(message.elapsedSec);
    if (!Number.isFinite(value) || value < 0) return '—';
    return `${value.toFixed(1)}s`;
  }

  messageUsageValue(message: SessionMessage, key: keyof UsageMetrics): number | null {
    const usage = message.usage;
    if (!usage || typeof usage !== 'object') return null;
    const value = Number(usage[key]);
    if (!Number.isFinite(value) || value < 0) return null;
    return Math.floor(value);
  }

  private _assistantMessageTimestampFallback(message: SessionMessage): number {
    const messageId = String(message.id || '');
    const match = messageId.match(/assistant-(\d{10,})$/);
    if (!match) return 0;
    const timestamp = Number(match[1]);
    return Number.isFinite(timestamp) ? timestamp : 0;
  }

  isSessionBusy(session: SessionSummary): boolean {
    return this.sessionBusyId() === session.id;
  }

  isAttachmentBusy(attachmentId: string): boolean {
    return this.attachmentBusyIds()[attachmentId] === true || this.attachmentService.isAttachmentBusy(attachmentId);
  }

  interactionLocked(): boolean {
    return this.loadingSession() || this.sending() || this.uploadingFiles() || this.savingSetup();
  }

  showComposerWebSearchToggle(): boolean {
    const useCase = this._effectiveUseCaseKey();
    return useCase === 'general' || useCase === 'reasoning';
  }

  includeWebSearch(): boolean {
    if (!this.showComposerWebSearchToggle()) return false;
    const useCase = this._effectiveUseCaseKey();
    return this._includeWebSearchByUseCase[useCase] === true;
  }

  setIncludeWebSearch(value: boolean): void {
    if (!this.showComposerWebSearchToggle()) return;
    const useCase = this._effectiveUseCaseKey();
    this._includeWebSearchByUseCase[useCase] = value === true;
    this._persistWebSearchByUseCase();
  }

  webSearchToggleDisabled(): boolean {
    return this.interactionLocked();
  }

  webSearchToggleHint(): string {
    if (!this.showComposerWebSearchToggle()) return '';
    return 'When enabled, this request can use live web results.';
  }

  uiPolicy(): UiPolicy {
    const useCase = this._effectiveUseCaseKey();
    const mode = this.voiceMode();
    const rootUseCase = (useCase === 'audio' || useCase === 'transcription' || useCase === 'tts') ? 'voice' : useCase;
    const isVoice = rootUseCase === 'voice';
    const isVideo = rootUseCase === 'video';
    const isImage = rootUseCase === 'image';
    const isTranscribeFlow = useCase === 'transcription' || (isVoice && mode === 'transcribe');
    const composerMode: ComposerMode = isVideo || isVoice ? 'hidden' : (isImage ? 'image' : 'text');
    return {
      composerMode,
      showExport: !isVideo && !isTranscribeFlow,
      showClear: !isVideo,
    };
  }

  showTextComposer(): boolean {
    return this.uiPolicy().composerMode !== 'hidden';
  }

  onSidebarSectionDrop(event: CdkDragDrop<SidebarSectionKey[]>): void {
    if (event.previousIndex === event.currentIndex) return;
    const next = [...this.sidebarSections()];
    moveItemInArray(next, event.previousIndex, event.currentIndex);
    this.sidebarSections.set(next);
  }

  onWorkspaceLaneDrop(event: CdkDragDrop<WorkspaceLaneKey[]>): void {
    if (event.previousIndex === event.currentIndex) return;
    const next = [...this.workspaceLanes()];
    moveItemInArray(next, event.previousIndex, event.currentIndex);
    this.workspaceLanes.set(next);
  }

  workspaceLaneOrder(lane: WorkspaceLaneKey): number {
    const index = this.workspaceLanes().indexOf(lane);
    return index >= 0 ? index : 0;
  }

  toggleFilesPanel(event?: Event): void {
    event?.stopPropagation();
    this.filesPanelCollapsed.set(!this.filesPanelCollapsed());
  }

  toggleHistoryPanel(event?: Event): void {
    event?.stopPropagation();
    this.historyPanelCollapsed.set(!this.historyPanelCollapsed());
  }

  toggleUsagePanel(event?: Event): void {
    event?.stopPropagation();
    this.usagePanelCollapsed.set(!this.usagePanelCollapsed());
  }

  toggleSidebarCollapsed(event?: Event): void {
    event?.stopPropagation();
    this.sidebarCollapsed.set(!this.sidebarCollapsed());
  }

  sidebarSectionBasisPct(section: SidebarSectionKey): number {
    const filesPct = this.filesSectionHeightPct();
    return section === 'files' ? filesPct : (100 - filesPct);
  }

  sidebarResizeAriaValueNow(): number {
    const topSection = this.sidebarSections()[0] || 'files';
    return Math.round(this.sidebarSectionBasisPct(topSection));
  }

  startSidebarResize(event: MouseEvent): void {
    if (this.filesPanelCollapsed() || this.historyPanelCollapsed() || this.sidebarCollapsed()) return;
    const container = (event.currentTarget as HTMLElement)?.closest('.sidebar-drop-list') as HTMLElement | null;
    const height = container?.getBoundingClientRect().height || 0;
    if (height <= 0) return;
    const topSection = this.sidebarSections()[0] || 'files';
    this._sidebarResizeTopSection = topSection;
    this._sidebarResizeStartY = event.clientY;
    this._sidebarResizeContainerHeight = height;
    this._sidebarResizeStartTopPct = this.sidebarSectionBasisPct(topSection);
    this._sidebarResizeActive = true;
    event.preventDefault();
    event.stopPropagation();
  }

  onSidebarResizeKey(event: KeyboardEvent): void {
    if (this.filesPanelCollapsed() || this.historyPanelCollapsed() || this.sidebarCollapsed()) return;
    const step = event.shiftKey ? ShellPageComponent.SIDEBAR_SPLIT_STEP_LARGE_PCT : ShellPageComponent.SIDEBAR_SPLIT_STEP_PCT;
    const topSection = this.sidebarSections()[0] || 'files';
    const current = this.sidebarSectionBasisPct(topSection);
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      this._setSidebarTopSectionPct(current - step);
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this._setSidebarTopSectionPct(current + step);
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      this._setSidebarTopSectionPct(ShellPageComponent.SIDEBAR_SPLIT_MIN_PCT);
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      this._setSidebarTopSectionPct(ShellPageComponent.SIDEBAR_SPLIT_MAX_PCT);
    }
  }

  stopSidebarResize(): void {
    this._sidebarResizeActive = false;
  }

  private _setAssistantReasoningWidth(nextWidth: number, maxWidth: number): void {
    const clamped = Math.max(
      ShellPageComponent.REASONING_WIDTH_MIN_PX,
      Math.min(maxWidth, nextWidth),
    );
    this.assistantReasoningWidthPx.set(Math.round(clamped));
  }

  private _setSidebarTopSectionPct(nextTopPct: number): void {
    const clampedTopPct = Math.max(
      ShellPageComponent.SIDEBAR_SPLIT_MIN_PCT,
      Math.min(ShellPageComponent.SIDEBAR_SPLIT_MAX_PCT, nextTopPct),
    );
    if (this._sidebarResizeTopSection === 'files') {
      this.filesSectionHeightPct.set(Math.round(clampedTopPct));
      return;
    }
    this.filesSectionHeightPct.set(Math.round(100 - clampedTopPct));
  }

  composerPlaceholder(): string {
    return this.uiPolicy().composerMode === 'image'
      ? 'Describe the image. Be specific about subject, style, and lighting.'
      : 'Type your message...';
  }

  composerPrimaryActionLabel(): string {
    if (this.stopRequested()) return 'Stopping...';
    if (this.sending()) return 'Stop';
    return this.uiPolicy().composerMode === 'image' ? 'Generate' : 'Send';
  }

  private _clearStopFeedbackTimer(): void {
    if (!this._stopFeedbackTimer) return;
    clearTimeout(this._stopFeedbackTimer);
    this._stopFeedbackTimer = null;
  }

  isImageComposerMode(): boolean {
    return this.uiPolicy().composerMode === 'image';
  }

  canSubmitComposer(): boolean {
    if (this.sending()) return true;
    const text = this.messageInput().trim();
    if (!text) return false;
    if (this.interactionLocked()) return false;
    if (this.uiPolicy().composerMode === 'hidden') return false;
    if (this.uiPolicy().composerMode === 'image') {
      if (this.imageActionBusy()) return false;
      return text.length <= 4000;
    }
    return true;
  }

  onComposerInputChange(value: string): void {
    const next = String(value || '');
    this.messageInput.set(next);
    this._composerDraftByScope[this._scopeKey()] = next;
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    if (!this.canSubmitComposer()) return;
    void this.sendMessage();
  }

  showSessionExportAction(): boolean {
    return this.uiPolicy().showExport;
  }

  tierLabel(tier: string): string {
    if (!tier) return '';
    return tier.charAt(0).toUpperCase() + tier.slice(1);
  }

  showClearSessionAction(): boolean {
    return this.uiPolicy().showClear;
  }

  showTokenHistoryAction(): boolean {
    return !this.isSpeechVoiceMode() && !this.isVideoMediaMode();
  }

  showStandardUsagePanel(): boolean {
    return !this.isSpeechVoiceMode() && !this.isVideoMediaMode();
  }

  openTokenHistory(): void {
    if (!this.showTokenHistoryAction()) return;
    this.showTokenHistoryModal.set(true);
    void this.loadUsage();
  }

  closeTokenHistory(event?: Event): void {
    if (event) event.stopPropagation();
    this.showTokenHistoryModal.set(false);
  }

  private async enforceActiveSessionWindow(): Promise<void> {
    if (this.autoArchiving()) return;
    const scopeKey = this._scopeKey();
    const activeSessions = this.sessions()
      .filter((session) => this._scopeKeyFromUseCase(session.useCase) === scopeKey)
      .filter((session) => !session.archivedAt)
      .slice()
      .sort((a, b) => {
        if (b.updatedAt !== a.updatedAt) return b.updatedAt - a.updatedAt;
        return b.createdAt - a.createdAt;
      });
    if (activeSessions.length <= ShellPageComponent.MAX_VISIBLE_ACTIVE_SESSIONS) return;

    const keepIds = new Set(
      activeSessions
        .slice(0, ShellPageComponent.MAX_VISIBLE_ACTIVE_SESSIONS)
        .map((session) => session.id),
    );
    const selectedSessionId = this.selectedSessionId();
    if (selectedSessionId) {
      const selectedActive = activeSessions.find((session) => session.id === selectedSessionId);
      if (selectedActive) keepIds.add(selectedSessionId);
    }
    const overflow = activeSessions.filter((session) => !keepIds.has(session.id));
    if (overflow.length === 0) return;

    this.autoArchiving.set(true);
    try {
      for (const session of overflow) {
        await firstValueFrom(this.api.archiveSession(session.id, true));
      }
      await this.refreshSessions(true);
    } catch (error: unknown) {
      this.error.set(this._errorMessage(error));
    } finally {
      this.autoArchiving.set(false);
    }
  }

  setTokenHistoryTab(tab: TokenHistoryTab): void {
    this.tokenHistoryTab.set(tab);
  }

  isTokenHistoryTab(tab: TokenHistoryTab): boolean {
    return this.tokenHistoryTab() === tab;
  }

  tokenHistoryScope(tab: TokenHistoryTab): UsageScope {
    const usage = this.usageView();
    if (tab === 'session') return usage?.activeSession || this.emptyUsageScope();
    if (tab === 'today') return usage?.today || this.emptyUsageScope();
    return usage?.allTime || this.emptyUsageScope();
  }

  tokenHistoryScopeTitle(tab: TokenHistoryTab): string {
    if (tab === 'session') return 'Active session by model';
    if (tab === 'today') return 'Today by model';
    return 'All-time by model';
  }

  tokenHistoryEmptyMessage(tab: TokenHistoryTab): string {
    if (tab === 'session') return 'No token usage recorded in this session yet.';
    if (tab === 'today') return 'No usage records found for today yet.';
    return 'No usage records found yet.';
  }

  tokenHistoryScopeTotalDisplay(tab: TokenHistoryTab): string {
    return this.tokenHistoryScope(tab).totals.costDisplay || '$0.000000';
  }

  isVideoMediaMode(): boolean {
    return this._effectiveUseCaseKey() === 'video';
  }

  isSpeechVoiceMode(): boolean {
    return this._effectiveUseCaseKey() === 'tts';
  }

  currentResponseInput(): number | null {
    return this.usageMetricValue(this.usageView()?.lastResponse?.usage, 'input');
  }

  currentResponseOutput(): number | null {
    return this.usageMetricValue(this.usageView()?.lastResponse?.usage, 'output');
  }

  currentResponseReasoning(): number | null {
    return this.usageMetricValue(this.usageView()?.lastResponse?.usage, 'reasoning');
  }

  currentResponseTotal(): number | null {
    return this.usageMetricValue(this.usageView()?.lastResponse?.usage, 'total');
  }

  currentResponseElapsedDisplay(): string {
    return this.usageView()?.lastResponse?.elapsedDisplay || '—';
  }

  currentResponseCostDisplay(): string {
    return this.usageView()?.lastResponse?.costDisplay || '—';
  }

  contextWindow(): number {
    const useCase = this._effectiveUseCaseKey();
    if (useCase === 'image' || useCase === 'video' || useCase === 'tts') return 0;
    const meta = this.selectedModelMetadata();
    return Number(meta?.contextWindow || 0);
  }

  hasContextWindowMetrics(): boolean {
    return this.contextWindow() > 0;
  }

  contextWindowDisplay(): string {
    const value = this.contextWindow();
    if (value > 0) return value.toLocaleString();
    const useCase = this._effectiveUseCaseKey();
    if (useCase === 'image' || useCase === 'video' || useCase === 'tts') return 'N/A (non-token)';
    return '—';
  }

  contextUsedPct(): number {
    const windowSize = this.contextWindow();
    const total = this.currentResponseTotal();
    if (!windowSize || !total) return 0;
    return Math.min(100, (total / windowSize) * 100);
  }

  totalChatContextPct(): number {
    const windowSize = this.contextWindow();
    const total = Number(this.usageView()?.activeSession?.totals?.total || 0);
    if (!windowSize) return 0;
    return (total / windowSize) * 100;
  }

  totalChatContextBarPct(): number {
    return Math.max(0, Math.min(100, this.totalChatContextPct()));
  }

  selectedModelInputPriceStr(): string {
    return this.catalogView()?.selectedModelInputPriceStr || '—';
  }

  selectedModelOutputPriceStr(): string {
    return this.catalogView()?.selectedModelOutputPriceStr || '—';
  }

  isVoiceTab(): boolean {
    return this.selectedUseCase() === 'voice';
  }

  isTranscribeVoiceMode(): boolean {
    return this.isVoiceTab() && this.voiceMode() === 'transcribe';
  }

  voicePrimaryAudioInputPriceLabel(): string {
    const fallback = this.isTranscribeVoiceMode()
      ? 'Transcribe in / 1M'
      : (this.voiceMode() === 'turn' ? 'Audio model in / 1M' : 'Realtime audio in / 1M');
    return this.catalogView()?.voicePrimaryAudioInputPriceLabel || fallback;
  }

  voicePrimaryAudioOutputPriceLabel(): string {
    const fallback = this.isTranscribeVoiceMode()
      ? 'Transcribe out / 1M'
      : (this.voiceMode() === 'turn' ? 'Audio model out / 1M' : 'Realtime audio out / 1M');
    return this.catalogView()?.voicePrimaryAudioOutputPriceLabel || fallback;
  }

  voicePrimaryAudioInputPriceStr(): string {
    return this.catalogView()?.voicePrimaryAudioInputPriceStr || '—';
  }

  voicePrimaryAudioOutputPriceStr(): string {
    return this.catalogView()?.voicePrimaryAudioOutputPriceStr || '—';
  }

  voiceTranscriptionInputPriceStr(): string {
    return this.catalogView()?.voiceTranscriptionInputPriceStr || '—';
  }

  voiceTranscriptionOutputPriceStr(): string {
    return this.catalogView()?.voiceTranscriptionOutputPriceStr || '—';
  }

  voicePricingFooter(): string {
    const fallback = this.voiceMode() === 'turn'
      ? 'Totals include both the turn-based audio reply and gpt-4o-mini-transcribe transcript cost.'
      : 'Totals include both the realtime reply and gpt-4o-mini-transcribe transcript cost.';
    return this.catalogView()?.voicePricingFooter || fallback;
  }

  ttsUsesCharacterPricing(): boolean {
    return this.catalogView()?.ttsUsesCharacterPricing === true;
  }

  ttsSpeechGenerationPriceStr(): string {
    return this.catalogView()?.ttsSpeechGenerationPriceStr || '—';
  }

  ttsTextInputPriceStr(): string {
    return this.catalogView()?.ttsTextInputPriceStr || '—';
  }

  ttsAudioOutputPriceStr(): string {
    return this.catalogView()?.ttsAudioOutputPriceStr || '—';
  }

  ttsPricingFooter(): string {
    return this.catalogView()?.ttsPricingFooter || '';
  }

  voiceUsageUpdateNote(): string {
    if (this.isTranscribeVoiceMode()) return 'Updates after each completed transcription job finishes.';
    return 'Updates after each completed voice turn finishes, including transcription + audio response.';
  }

  hasClearableSessionContent(): boolean {
    return this.messages().length > 0
      || this.attachments().length > 0
      || !!this.promptText().trim()
      || !!this.contextText().trim()
      || !!this.promptPresetId().trim();
  }

  clearCurrentSession(event?: Event): void {
    if (event) event.stopPropagation();
    const sessionId = this.selectedSessionId();
    if (!sessionId || this.interactionLocked()) return;
    const session = this.sessions().find((item) => item.id === sessionId);
    if (!session) return;
    this.clearSessionMessages(session);
  }

  async downloadAssistantMessage(message: SessionMessage, format: 'md' | 'txt', event?: Event): Promise<void> {
    if (event) event.stopPropagation();
    this.closeResponseDownloadMenu();
    const sessionId = this.selectedSessionId();
    if (!sessionId || typeof message.id !== 'number') return;
    const url = `/sessions/${encodeURIComponent(sessionId)}/messages/${message.id}/export?format=${format}`;
    await this._downloadFromEndpoint(url, `assistant-response.${format}`);
  }

  async downloadChat(format: 'md' | 'txt' = 'md'): Promise<void> {
    const sessionId = this.selectedSessionId();
    if (!sessionId) return;
    const url = `/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`;
    await this._downloadFromEndpoint(url, `chat-export.${format}`);
  }

  async loadUsage(): Promise<void> {
    this.loadingUsage.set(true);
    const sessionId = this.selectedSessionId();
    this.api.getVmUsage(sessionId, this.effectiveModelForPricing(), this.voiceMode()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.usageView.set(payload?.usageView || null);
        this.loadingUsage.set(false);
      },
      error: () => {
        this.loadingUsage.set(false);
      },
    });
  }

  onAudioTurnFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files[0];
    if (!file) return;
    this._submitTurnAudioFile(file);
    input.value = '';
  }

  onTranscriptionFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files[0];
    if (!file) return;
    this._submitTranscriptionAudioFile(file, 'uploaded');
    input.value = '';
  }

  runTts(): void {
    const text = this.ttsText().trim();
    if (!text || this.ttsBusy()) return;
    const sessionId = this._ensureSessionId();
    this.ttsBusy.set(true);
    this.voiceStatus.set('Generating speech...');
    this.api
      .textToSpeech({
        sessionId,
        useCase: 'tts',
        model: this.ttsModel(),
        text,
        voice: this.ttsVoice(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.ttsBusy.set(false);
          this.voiceStatus.set('TTS complete.');
          this.ttsAudioUrl.set(`data:${payload.audioMime};base64,${payload.audio}`);
          if (payload.sessionView) {
            this.messages.set(payload.sessionView.messages || []);
            this._refreshImageWorkspaceItems();
          }
          if (payload.usageView) this.usageView.set(payload.usageView);
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.ttsBusy.set(false);
          this.voiceStatus.set('TTS failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  bootstrapRealtimeVoice(): void {
    const sessionId = this._ensureSessionId();
    this.voiceStatus.set('Bootstrapping realtime voice...');
    this.api.bootstrapVoiceSession({
      sessionId,
      model: this.selectedModel() || 'gpt-realtime-mini',
      useCase: 'voice',
      voice: this.audioTurnVoice(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.voiceStatus.set(`Realtime bootstrap ready (${payload.model}, ${payload.voice}).`);
      },
      error: (error: unknown) => {
        this.voiceStatus.set('Realtime bootstrap failed.');
        this.error.set(this._errorMessage(error));
      },
    });
  }

  async connectRealtimeSession(): Promise<void> {
    if (this.interactionLocked() || this.realtimeConnected()) return;
    if (!navigator?.mediaDevices?.getUserMedia) {
      this.voiceStatus.set('Microphone is not supported in this browser.');
      return;
    }
    try {
      this.endRealtimeSession();
      this.voiceStatus.set('Connecting realtime voice...');
      const sessionId = this._ensureSessionId();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this._realtimeMicStream = stream;
      const bootstrap = await firstValueFrom(this.api.bootstrapVoiceSession({
        sessionId,
        model: this.selectedModel() || 'gpt-realtime-mini',
        useCase: 'voice',
        voice: this.audioTurnVoice() || 'ash',
      }));
      if (!bootstrap?.clientSecret) throw new Error('Realtime bootstrap did not return a client secret.');
      this._realtimeTranscriptionModel = String(bootstrap.transcriptionModel || 'gpt-4o-mini-transcribe');
      this._ensureRealtimeRemoteAudio();

      this._realtimePc = new RTCPeerConnection();
      this._realtimePc.ontrack = (event: RTCTrackEvent): void => {
        if (!this._realtimeRemoteAudio) this._ensureRealtimeRemoteAudio();
        if (this._realtimeRemoteAudio) {
          this._realtimeRemoteAudio.srcObject = event.streams[0];
          void this._realtimeRemoteAudio.play().catch((): void => undefined);
        }
      };
      this._realtimePc.onconnectionstatechange = (): void => {
        const state = this._realtimePc ? this._realtimePc.connectionState : '';
        if (state === 'failed') {
          this.voiceStatus.set('Realtime voice connection failed.');
          this.endRealtimeSession();
          return;
        }
        if (state === 'disconnected' || state === 'closed') {
          this.endRealtimeSession();
        }
      };

      for (const track of stream.getTracks()) {
        this._realtimePc.addTrack(track, stream);
      }

      this._realtimeDc = this._realtimePc.createDataChannel('oai-events');
      this._realtimeDc.onopen = (): void => {
        this.realtimeConnected.set(true);
        this.realtimeMuted.set(false);
        this.voiceStatus.set('Realtime voice connected.');
      };
      this._realtimeDc.onmessage = (event: MessageEvent): void => this._handleRealtimeServerEvent(String(event.data || ''), sessionId);
      this._realtimeDc.onerror = (): void => {
        this.voiceStatus.set('Realtime event channel failed.');
      };

      const offer = await this._realtimePc.createOffer();
      await this._realtimePc.setLocalDescription(offer);

      const sdpResponse = await fetch('https://api.openai.com/v1/realtime/calls', {
        method: 'POST',
        body: offer.sdp || '',
        headers: {
          Authorization: `Bearer ${bootstrap.clientSecret}`,
          'Content-Type': 'application/sdp',
        },
      });
      if (!sdpResponse.ok) {
        const detail = (await sdpResponse.text()) || `Realtime session failed (${sdpResponse.status})`;
        throw new Error(detail);
      }
      const answerSdp = await sdpResponse.text();
      await this._realtimePc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
    } catch (error: unknown) {
      this.voiceStatus.set('Microphone connection failed.');
      this.error.set(this._errorMessage(error));
      this.endRealtimeSession();
    }
  }

  toggleRealtimeMute(): void {
    if (!this.realtimeConnected() || !this._realtimeMicStream) return;
    const nextMuted = !this.realtimeMuted();
    for (const track of this._realtimeMicStream.getAudioTracks()) {
      track.enabled = !nextMuted;
    }
    this.realtimeMuted.set(nextMuted);
    this.voiceStatus.set(nextMuted ? 'Microphone muted.' : 'Microphone unmuted.');
  }

  endRealtimeSession(): void {
    this._closeRealtimeResources();
    this._realtimeTurn = this._blankRealtimeTurn();
    this.realtimeConnected.set(false);
    this.realtimeMuted.set(false);
    if (this.selectedUseCase() === 'voice' && this.voiceMode() === 'realtime') {
      this.voiceStatus.set('Realtime session ended.');
    }
  }

  private _blankRealtimeTurn(): RealtimeTurnState {
    return {
      userLive: '',
      userFinal: '',
      assistantLive: '',
      assistantFinal: '',
      responseDone: false,
      persisting: false,
      persisted: false,
      audioPlaybackComplete: false,
      sawOutputAudioEvent: false,
      userUsage: null,
      assistantUsage: null,
      startedAtMs: 0,
    };
  }

  private _ensureRealtimeRemoteAudio(): void {
    if (this._realtimeRemoteAudio) return;
    this._realtimeRemoteAudio = document.createElement('audio');
    this._realtimeRemoteAudio.autoplay = true;
    this._realtimeRemoteAudio.style.display = 'none';
    document.body.appendChild(this._realtimeRemoteAudio);
  }

  private _closeRealtimeResources(): void {
    this.voiceService.setRealtimeResources({
      dataChannel: this._realtimeDc,
      peerConnection: this._realtimePc,
      mediaStream: this._realtimeMicStream,
      remoteAudio: this._realtimeRemoteAudio,
    });
    this.voiceService.endSession();
    if (this._realtimeDc) {
      try { this._realtimeDc.close(); } catch {}
      this._realtimeDc = null;
    }
    if (this._realtimePc) {
      try { this._realtimePc.close(); } catch {}
      this._realtimePc = null;
    }
    if (this._realtimeMicStream) {
      for (const track of this._realtimeMicStream.getTracks()) track.stop();
      this._realtimeMicStream = null;
    }
    if (this._realtimeRemoteAudio) {
      this._realtimeRemoteAudio.pause();
      this._realtimeRemoteAudio.srcObject = null;
      if (this._realtimeRemoteAudio.parentNode) {
        this._realtimeRemoteAudio.parentNode.removeChild(this._realtimeRemoteAudio);
      }
      this._realtimeRemoteAudio = null;
    }
  }

  private _normalizeRealtimeUsage(raw: unknown, source: 'transcription' | 'realtime'): UsageMetrics | null {
    if (!raw || typeof raw !== 'object') return null;
    const value = raw as Record<string, unknown>;
    const input = Number(value['input'] ?? value['input_tokens']) || 0;
    const output = Number(value['output'] ?? value['output_tokens']) || 0;
    const total = Number(value['total'] ?? value['total_tokens']) || (input + output);
    const reasoning = Number(value['reasoning']) || 0;
    if (!input && !output && !total && !reasoning) return null;
    return {
      input,
      output: source === 'transcription' ? Math.max(output, 0) : output,
      total: Math.max(total, input + output),
      reasoning,
    };
  }

  private _prepareRealtimeTurnForInput(): void {
    if (this._realtimeTurn.persisting) return;
    const hasCompletedTurn = !!(
      this._realtimeTurn.responseDone
      || this._realtimeTurn.userFinal
      || this._realtimeTurn.assistantFinal
      || this._realtimeTurn.assistantLive
    );
    if (hasCompletedTurn) {
      this._realtimeTurn = this._blankRealtimeTurn();
    }
  }

  private _handleRealtimeServerEvent(raw: string, sessionId: string): void {
    let event: Record<string, unknown> | null = null;
    try {
      event = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(event?.['type'] || '');
    switch (type) {
      case 'session.created':
        this.realtimeConnected.set(true);
        this.voiceStatus.set('Realtime voice connected.');
        break;
      case 'input_audio_buffer.speech_started':
        this._prepareRealtimeTurnForInput();
        this._realtimeTurn.startedAtMs = Date.now();
        this.voiceStatus.set('Listening...');
        break;
      case 'input_audio_buffer.speech_stopped':
        this.voiceStatus.set('Processing response...');
        break;
      case 'output_audio_buffer.started':
        this._realtimeTurn.sawOutputAudioEvent = true;
        this._realtimeTurn.audioPlaybackComplete = false;
        break;
      case 'output_audio_buffer.stopped':
      case 'output_audio_buffer.cleared':
        this._realtimeTurn.sawOutputAudioEvent = true;
        this._realtimeTurn.audioPlaybackComplete = true;
        this._maybePersistRealtimeTurn(sessionId);
        break;
      case 'conversation.item.input_audio_transcription.delta':
        this._realtimeTurn.userLive += String(event?.['delta'] || '');
        break;
      case 'conversation.item.input_audio_transcription.completed':
        this._realtimeTurn.userFinal = String(event?.['transcript'] || '').trim();
        this._realtimeTurn.userUsage = this._normalizeRealtimeUsage(event?.['usage'], 'transcription');
        this._maybePersistRealtimeTurn(sessionId);
        break;
      case 'response.output_audio_transcript.delta':
        this._realtimeTurn.assistantLive += String(event?.['delta'] || '');
        this.voiceStatus.set('Responding...');
        break;
      case 'response.output_audio_transcript.done':
        this._realtimeTurn.assistantFinal = String(event?.['transcript'] || '').trim();
        this._maybePersistRealtimeTurn(sessionId);
        break;
      case 'response.done': {
        const responseObj = (event?.['response'] && typeof event['response'] === 'object')
          ? (event['response'] as Record<string, unknown>)
          : null;
        this._realtimeTurn.assistantUsage = this._normalizeRealtimeUsage(responseObj?.['usage'], 'realtime');
        this._realtimeTurn.responseDone = true;
        if (!this._realtimeTurn.sawOutputAudioEvent) {
          this._realtimeTurn.audioPlaybackComplete = true;
        }
        this._maybePersistRealtimeTurn(sessionId);
        break;
      }
      case 'error':
        this.voiceStatus.set(String((event?.['error'] as Record<string, unknown> | undefined)?.['message'] || 'Realtime voice reported an error.'));
        break;
      default:
        break;
    }
  }

  private _maybePersistRealtimeTurn(sessionId: string): void {
    if (!sessionId || this._realtimeTurn.persisting || !this._realtimeTurn.responseDone || !this._realtimeTurn.audioPlaybackComplete) return;
    const userText = (this._realtimeTurn.userFinal || this._realtimeTurn.userLive || '').trim();
    const assistantText = (this._realtimeTurn.assistantFinal || this._realtimeTurn.assistantLive || '').trim();
    if (!userText || !assistantText) return;

    const elapsedSec = this._realtimeTurn.startedAtMs > 0
      ? Math.max(0, (Date.now() - this._realtimeTurn.startedAtMs) / 1000)
      : undefined;

    this._realtimeTurn.persisting = true;
    this.api.persistRealtimeVoiceTurn(sessionId, {
      userText,
      assistantText,
      model: this.selectedModel() || 'gpt-realtime-mini',
      useCase: 'voice',
      userUsage: this._realtimeTurn.userUsage || undefined,
      assistantUsage: this._realtimeTurn.assistantUsage || undefined,
      userUsageModel: this._realtimeTranscriptionModel,
      elapsedSec,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        if (result?.sessionView) {
          this.messages.set(result.sessionView.messages || []);
          this._refreshImageWorkspaceItems();
        }
        if (result?.usageView) this.usageView.set(result.usageView);
        this.voiceStatus.set('Realtime turn complete.');
        void this.refreshSessions();
        this._realtimeTurn = this._blankRealtimeTurn();
      },
      error: (error: unknown) => {
        this.error.set(this._errorMessage(error));
      },
      complete: () => {
        this._realtimeTurn.persisting = false;
      },
    });
  }

  async startTurnRecording(): Promise<void> {
    if (this.interactionLocked() || this.turnRecorderState() !== 'idle') return;
    const started = await this._startRecorder('turn');
    if (started) {
      this.turnRecorderState.set('recording');
      this.voiceStatus.set('Recording turn...');
    }
  }

  cancelTurnRecording(): void {
    if (this.turnRecorderState() === 'idle') return;
    this._pendingTurnRecordingFile = null;
    this._stopActiveRecorder(false);
    this.turnRecorderState.set('idle');
    this.voiceStatus.set('Recording canceled.');
  }

  sendTurnRecording(): void {
    if (this.turnRecorderState() !== 'ready' || !this._pendingTurnRecordingFile) return;
    const file = this._pendingTurnRecordingFile;
    this._pendingTurnRecordingFile = null;
    this.turnRecorderState.set('idle');
    this._submitTurnAudioFile(file);
  }

  async toggleTranscribeRecording(): Promise<void> {
    if (this.interactionLocked()) return;
    if (this.transcribeRecorderState() !== 'recording') {
      const started = await this._startRecorder('transcribe');
      if (started) {
        this.transcribeRecorderState.set('recording');
        this.voiceStatus.set('Recording transcription audio...');
      }
      return;
    }
    this._stopActiveRecorder(true);
  }

  saveSettings(): void {
    const model = this.settingsModelInput().trim();
    const effort = this.settingsEffortInput().trim();
    if (!model && !effort) return;
    this.settingsStatus.set('Saving settings...');
    this.api.updateSettings({ model: model || undefined, effort: effort || undefined }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.settingsStatus.set('Settings saved.');
      },
      error: (error: unknown) => {
        this.settingsStatus.set('Settings save failed.');
        this.error.set(this._errorMessage(error));
      },
    });
  }

  loadUsageHistory(): void {
    this.loadingUsageHistory.set(true);
    this.api.getUsageHistory(this.selectedSessionId() || undefined).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.usageHistory.set(payload || null);
        this.loadingUsageHistory.set(false);
      },
      error: () => {
        this.loadingUsageHistory.set(false);
      },
    });
  }

  loadModelCatalogRaw(): void {
    this.api.getModelCatalog().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.modelCatalogRaw.set(payload || null);
      },
      error: () => {},
    });
  }

  loadMcpProfiles(): void {
    this.mcpProfilesLoading.set(true);
    this.mcpProfilesError.set('');
    this.api.getDeepResearchMcpProfiles().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.mcpProfiles.set(payload?.profiles || []);
        const next = { ...this.deepResearchTools() };
        if (!next.mcpProfileId && payload?.defaultProfileId && !this.isDeepResearchToolBlocked('mcp')) {
          next.mcpProfileId = String(payload.defaultProfileId || '').trim();
        }
        this._ensureDeepResearchMcpProfileSelection(next);
        this.deepResearchTools.set(next);
        this.mcpProfilesLoading.set(false);
        this.mcpProfilesError.set('');
      },
      error: (error: unknown) => {
        this.mcpProfiles.set([]);
        this.mcpProfilesLoading.set(false);
        this.mcpProfilesError.set(this._errorMessage(error) || 'Could not load MCP profiles.');
      },
    });
  }

  runEmbedText(): void {
    const text = this.embedTextInput().trim();
    if (!text || this.embedTextBusy()) return;
    const sessionId = this._ensureSessionId();
    this.embedTextBusy.set(true);
    this.toolsStatus.set('Generating embedding...');
    this.api
      .embedText({
        sessionId,
        useCase: 'embeddings',
        model: this.selectedModel(),
        text,
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.embedTextBusy.set(false);
          this.toolsStatus.set(`Embed complete (${payload.dimensions} dims).`);
          this.embedSearchResult.set(this._prettyJson(payload));
          this.embedTextInput.set('');
          void this.loadSession(sessionId);
          void this.loadUsage();
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.embedTextBusy.set(false);
          this.toolsStatus.set('Embed failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  runEmbedIndex(): void {
    const sessionId = this.selectedSessionId();
    if (!sessionId || this.embedIndexBusy()) return;
    this.embedIndexBusy.set(true);
    this.toolsStatus.set('Indexing attachment embeddings...');
    this.api
      .embedIndex({
        sessionId,
        model: this.selectedModel(),
        includeInactive: false,
        rebuild: true,
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.embedIndexBusy.set(false);
          this.toolsStatus.set(`Index complete (${payload.indexedFiles} files / ${payload.indexedChunks} chunks).`);
          this.embedSearchResult.set(this._prettyJson(payload));
        },
        error: (error: unknown) => {
          this.embedIndexBusy.set(false);
          this.toolsStatus.set('Embed indexing failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  runEmbedSearch(): void {
    const sessionId = this.selectedSessionId();
    const query = this.embedQueryInput().trim();
    if (!sessionId || !query || this.embedSearchBusy()) return;
    this.embedSearchBusy.set(true);
    this.toolsStatus.set('Searching indexed embeddings...');
    this.api
      .embedSearch({
        sessionId,
        model: this.selectedModel(),
        query,
        topK: this.embedTopK(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.embedSearchBusy.set(false);
          this.toolsStatus.set(`Embedding search complete (${payload.matches.length} matches).`);
          this.embedSearchResult.set(this._prettyJson(payload));
        },
        error: (error: unknown) => {
          this.embedSearchBusy.set(false);
          this.toolsStatus.set('Embedding search failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  startComputerRun(): void {
    const sessionId = this._ensureSessionId();
    const userText = this.computerPrompt().trim();
    if (!userText) return;
    this.toolsStatus.set('Starting computer run...');
    void this.computerService
      .startRun({
        sessionId,
        userText,
        model: this.computerModel(),
        startUrl: this.computerStartUrl().trim() || undefined,
      })
      .then((payload) => {
          this.computerRun.set(payload || null);
          this.toolsStatus.set(`Computer run started (${payload.status}).`);
          void this.refreshSessions();
          void this.loadSession(sessionId);
      })
      .catch((error: unknown) => {
          this.toolsStatus.set('Computer run start failed.');
          this.error.set(this._errorMessage(error));
      });
  }

  stepComputerRun(): void {
    const runId = this.computerRun()?.runId;
    if (!runId) return;
    this.toolsStatus.set('Stepping computer run...');
    void this.computerService.stepRun(runId).then((payload) => {
        this.computerRun.set(payload || null);
        this.toolsStatus.set(`Computer run status: ${payload.status}.`);
        const sessionId = this.selectedSessionId();
        if (sessionId) {
          void this.loadSession(sessionId);
          void this.loadUsage();
        }
    }).catch((error: unknown) => {
        this.toolsStatus.set('Computer run step failed.');
        this.error.set(this._errorMessage(error));
    });
  }

  closeComputerRun(): void {
    const runId = this.computerRun()?.runId;
    if (!runId) return;
    this.toolsStatus.set('Closing computer run...');
    void this.computerService.closeRun(runId).then(() => {
        this.computerRun.set(null);
        this.toolsStatus.set('Computer run closed.');
        const sessionId = this.selectedSessionId();
        if (sessionId) {
          void this.loadSession(sessionId);
          void this.loadUsage();
        }
    }).catch((error: unknown) => {
        this.toolsStatus.set('Computer run close failed.');
        this.error.set(this._errorMessage(error));
    });
  }

  runImageGenerate(): void {
    const prompt = this.imagePrompt().trim();
    if (!prompt || this.imageActionBusy()) return;
    const sessionId = this._ensureSessionId();
    this.imageActionBusy.set(true);
    this.imageStatus.set('Generating image...');
    this.api
      .generateImage({
        sessionId,
        useCase: 'image',
        model: this.imageModel(),
        prompt,
        moderation: this.imageModeration(),
        style: this.imageStyle(),
        size: this.imageSize(),
        count: this.imageCount(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.imageActionBusy.set(false);
          this.imageActionPending.set('none');
          this.imageStatus.set(`Generated ${payload.images.length} image(s).`);
          this.imageResults.set(payload.images || []);
          void this.loadSession(sessionId);
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.imageActionBusy.set(false);
          this.imageActionPending.set('none');
          this.imageStatus.set('Image generation failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  onImageEditFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files[0];
    const instruction = this.imageEditInstruction().trim();
    if (!file || !instruction || this.imageActionBusy()) return;
    const sessionId = this._ensureSessionId();
    this.imageActionBusy.set(true);
    this.imageStatus.set('Editing image...');
    this.api
      .editImage({
        sessionId,
        useCase: 'image',
        model: this.imageModel(),
        instruction,
        moderation: this.imageModeration(),
        style: this.imageStyle(),
        size: this.imageSize(),
        count: this.imageCount(),
        file,
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.imageActionBusy.set(false);
          this.imageActionPending.set('none');
          this.imageStatus.set(`Edited image (${payload.images.length} output).`);
          this.imageResults.set(payload.images || []);
          input.value = '';
          void this.loadSession(sessionId);
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.imageActionBusy.set(false);
          this.imageActionPending.set('none');
          this.imageStatus.set('Image edit failed.');
          this.error.set(this._errorMessage(error));
          input.value = '';
        },
      });
  }

  loadImageProjects(): void {
    this.api.getImageProjects().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        this.imageProjects.set(payload?.projects || []);
        const current = this.imageProjectFilterId();
        const known = (payload?.projects || []).some((project) => project.id === current);
        if (current !== '__all__' && !known) {
          this.imageProjectFilterId.set('__all__');
          this._refreshImageWorkspaceItems();
        }
      },
      error: () => {},
    });
  }

  createImageProject(): void {
    const name = this.imageProjectName().trim();
    if (!name) return;
    this.api.createImageProject(name).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageProjectName.set('');
        this.imageStatus.set('Image project created.');
        this.loadImageProjects();
      },
      error: (error: unknown) => {
        this.imageStatus.set('Image project creation failed.');
        this.error.set(this._errorMessage(error));
      },
    });
  }

  onImageCountChange(value: number): void {
    this.visualService.onImageCountChange(value);
  }

  selectedWorkspaceImage(): ShellPageWorkspaceImage | null {
    return this.visualService.selectedWorkspaceImage();
  }

  selectWorkspaceImage(item: ShellPageWorkspaceImage): void {
    this.visualService.selectWorkspaceImage(item);
  }

  toggleWorkspaceImageFavorite(item: ShellPageWorkspaceImage, event?: Event): void {
    if (event) event.stopPropagation();
    const sessionId = this.selectedSessionId();
    if (!item || !sessionId || !item.messageId || this.imageControlDisabled()) return;
    const nextFavorite = !item.favorite;
    this._updateImagePayloadMetaLocal(item.messageId, { favorite: nextFavorite });
    this._refreshImageWorkspaceItems();
    this.api.updateImageMessageMeta(sessionId, item.messageId, { favorite: nextFavorite }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageStatus.set(nextFavorite ? 'Saved to favorites.' : 'Removed from favorites.');
      },
      error: (error: unknown) => {
        this._updateImagePayloadMetaLocal(item.messageId as number, { favorite: item.favorite });
        this._refreshImageWorkspaceItems();
        this.error.set(this._errorMessage(error));
      },
    });
  }

  visualCanvasAspectRatio(item: ShellPageWorkspaceImage | null): string {
    return this.visualService.visualCanvasAspectRatio(item);
  }

  onImageProjectFilterChange(projectId: string): void {
    if (this.imageControlDisabled()) return;
    this.imageProjectFilterId.set(projectId || '__all__');
    this._refreshImageWorkspaceItems();
  }

  downloadSelectedWorkspaceImage(): void {
    const selected = this.selectedWorkspaceImage();
    if (!selected?.b64) return;
    this._downloadDataUrl(`data:${selected.mime};base64,${selected.b64}`, this._imageFilename(selected));
  }

  toggleSelectedWorkspaceImageFavorite(): void {
    const selected = this.selectedWorkspaceImage();
    const sessionId = this.selectedSessionId();
    if (!selected || !sessionId || !selected.messageId || this.imageControlDisabled()) return;
    const nextFavorite = !selected.favorite;
    this._updateImagePayloadMetaLocal(selected.messageId, { favorite: nextFavorite });
    this._refreshImageWorkspaceItems();
    this.api.updateImageMessageMeta(sessionId, selected.messageId, { favorite: nextFavorite }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageStatus.set(nextFavorite ? 'Saved to favorites.' : 'Removed from favorites.');
      },
      error: (error: unknown) => {
        this._updateImagePayloadMetaLocal(selected.messageId as number, { favorite: selected.favorite });
        this._refreshImageWorkspaceItems();
        this.error.set(this._errorMessage(error));
      },
    });
  }

  hideSelectedWorkspaceImage(): void {
    const selected = this.selectedWorkspaceImage();
    const sessionId = this.selectedSessionId();
    if (!selected || !sessionId || !selected.messageId || this.imageControlDisabled()) return;
    const previousKey = selected.key;
    this._updateImagePayloadMetaLocal(selected.messageId, { hiddenInWorkspace: true });
    this._refreshImageWorkspaceItems();
    if (this.selectedWorkspaceKey() === previousKey) {
      this.selectedWorkspaceKey.set(this.imageWorkspaceItems()[0]?.key || '');
    }
    this.api.updateImageMessageMeta(sessionId, selected.messageId, { hiddenInWorkspace: true }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageStatus.set('Image hidden from workspace.');
      },
      error: (error: unknown) => {
        this._updateImagePayloadMetaLocal(selected.messageId as number, { hiddenInWorkspace: false });
        this._refreshImageWorkspaceItems();
        this.error.set(this._errorMessage(error));
      },
    });
  }

  assignProjectToSelectedWorkspaceImage(projectId: string): void {
    const selected = this.selectedWorkspaceImage();
    const sessionId = this.selectedSessionId();
    if (!selected || !sessionId || !selected.messageId || this.imageControlDisabled()) return;
    const normalizedProjectId = (projectId || '').trim() || null;
    const previousProjectId = selected.projectId;
    this._updateImagePayloadMetaLocal(selected.messageId, { projectId: normalizedProjectId });
    this._refreshImageWorkspaceItems();
    this.api.updateImageMessageMeta(sessionId, selected.messageId, { projectId: normalizedProjectId }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageStatus.set(normalizedProjectId ? 'Image assigned to project.' : 'Project assignment cleared.');
      },
      error: (error: unknown) => {
        this._updateImagePayloadMetaLocal(selected.messageId as number, { projectId: previousProjectId });
        this._refreshImageWorkspaceItems();
        this.error.set(this._errorMessage(error));
      },
    });
  }

  createAndAssignProjectToSelectedWorkspaceImage(name: string): void {
    const selected = this.selectedWorkspaceImage();
    const sessionId = this.selectedSessionId();
    const normalizedName = String(name || '').trim();
    if (!selected || !sessionId || !selected.messageId || this.imageControlDisabled() || !normalizedName) return;
    this.api.createImageProject(normalizedName).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (payload) => {
        const project = payload?.project;
        if (!project?.id) {
          this.imageStatus.set('Image project creation failed.');
          return;
        }
        const nextProjects = [
          ...this.imageProjects().filter((item) => item.id !== project.id),
          project,
        ].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
        this.imageProjects.set(nextProjects);
        this.assignProjectToSelectedWorkspaceImage(project.id);
      },
      error: (error: unknown) => {
        this.imageStatus.set('Image project creation failed.');
        this.error.set(this._errorMessage(error));
      },
    });
  }

  openCreateProjectDialog(): void {
    if (this.imageControlDisabled()) return;
    this._textInputDialogMode = 'create_project';
    this._textInputDialogRenameProjectId = '';
    this.textInputDialogTitle.set('Create new project');
    this.textInputDialogPlaceholder.set('Project name');
    this.textInputDialogConfirmLabel.set('Create');
    this.textInputDialogValue.set('');
    this.showTextInputDialog.set(true);
  }

  closeTextInputDialog(event?: Event): void {
    event?.stopPropagation();
    this.showTextInputDialog.set(false);
    this._textInputDialogMode = '';
    this._textInputDialogRenameProjectId = '';
    this.textInputDialogValue.set('');
  }

  submitTextInputDialog(name: string): void {
    if (!name) return;
    const mode = this._textInputDialogMode;
    const renameProjectId = this._textInputDialogRenameProjectId;
    this.closeTextInputDialog();
    if (mode === 'create_project') {
      this.createAndAssignProjectToSelectedWorkspaceImage(name);
      return;
    }
    if (mode === 'rename_project' && renameProjectId) {
      this.api.renameImageProject(renameProjectId, name).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          const nextProject = payload?.project;
          if (!nextProject) return;
          this.imageProjects.set(
            this.imageProjects().map((project) => (project.id === nextProject.id ? nextProject : project)),
          );
          this.imageStatus.set('Image project renamed.');
        },
        error: (error: unknown) => {
          this.error.set(this._errorMessage(error));
        },
      });
    }
  }

  renameSelectedWorkspaceImageProject(): void {
    if (this.imageControlDisabled()) return;
    const selected = this.selectedWorkspaceImage();
    const projectId = selected?.projectId || '';
    if (!projectId) return;
    const existing = this.imageProjects().find((project) => project.id === projectId);
    this._textInputDialogMode = 'rename_project';
    this._textInputDialogRenameProjectId = projectId;
    this.textInputDialogTitle.set('Rename project');
    this.textInputDialogPlaceholder.set('Project name');
    this.textInputDialogConfirmLabel.set('Rename');
    this.textInputDialogValue.set(existing?.name || '');
    this.showTextInputDialog.set(true);
  }

  deleteSelectedWorkspaceImageProject(): void {
    if (this.imageControlDisabled()) return;
    const selected = this.selectedWorkspaceImage();
    const projectId = selected?.projectId || '';
    if (!projectId) return;
    this.api.deleteImageProject(projectId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.imageProjects.set(this.imageProjects().filter((project) => project.id !== projectId));
        if (this.imageProjectFilterId() === projectId) {
          this.imageProjectFilterId.set('__all__');
        }
        this._updateImagePayloadProjectForAll(projectId, null);
        this._refreshImageWorkspaceItems();
        this.imageStatus.set('Image project deleted.');
      },
      error: (error: unknown) => {
        this.error.set(this._errorMessage(error));
      },
    });
  }

  regenerateSelectedWorkspaceImage(): void {
    const selected = this.selectedWorkspaceImage();
    if (!selected || this.imageControlDisabled()) return;
    const snapshot = this._snapshotFromWorkspaceItem(selected);
    if (!snapshot) return;
    this.imageActionPending.set('regenerate');
    this._applyImageSnapshot(snapshot, true);
    this.runImageGenerate();
  }

  createVariationFromSelectedImage(): void {
    const selected = this.selectedWorkspaceImage();
    if (!selected || this.imageControlDisabled()) return;
    const snapshot = this._snapshotFromWorkspaceItem(selected);
    if (!snapshot) return;
    this.imageActionPending.set('variation');
    this._applyImageSnapshot({
      ...snapshot,
      prompt: `${snapshot.prompt}\n\nVariation request: Generate a variation of this concept/composition with fresh details while preserving the core intent and overall style direction.`.trim(),
      count: 1,
    }, true);
    this.runImageGenerate();
  }

  refineSelectedWorkspaceImage(): void {
    const selected = this.selectedWorkspaceImage();
    if (!selected || this.imageControlDisabled()) return;
    const snapshot = this._snapshotFromWorkspaceItem(selected);
    if (!snapshot) return;
    this.imageActionPending.set('refine');
    this._applyImageSnapshot(snapshot, true);
    this.runImageGenerate();
  }

  retryImageGeneration(message: SessionMessage, event?: Event): void {
    if (event) event.stopPropagation();
    if (!this.showImageRetryAction(message) || this.imageControlDisabled()) return;
    const snapshot = this._imageRetrySnapshotFromMessage(message);
    if (!snapshot) return;
    this._applyImageSnapshot(snapshot, true);
    this.runImageGenerate();
  }

  showImageRetryAction(message: SessionMessage): boolean {
    return this.visualService.showImageRetryAction(message);
  }

  copySelectedImagePrompt(): void {
    const selected = this.selectedWorkspaceImage();
    if (!selected) return;
    const prompt = String(selected.prompt || '').trim();
    if (!prompt) return;
    this._copyText(prompt, () => this.imageStatus.set('Prompt copied.'));
  }

  copyImagePromptHistoryPrompt(item: ShellPagePromptHistoryItem): void {
    const prompt = String(item?.prompt || '').trim();
    if (!prompt) return;
    this._copyText(prompt, () => this.imageStatus.set('Prompt copied.'));
  }

  loadImagePromptHistory(item: ShellPagePromptHistoryItem): void {
    if (this.imageControlDisabled()) return;
    if (item.snapshot) {
      this.visualService.applyImageSnapshot(item.snapshot, true);
      this.imageStatus.set('Prompt and settings loaded.');
      return;
    }
    const prompt = String(item.prompt || '').trim();
    if (!prompt) return;
    this.imagePrompt.set(prompt);
    this.imageStatus.set('Prompt loaded.');
  }

  imageControlDisabled(): boolean {
    return this.interactionLocked() || this.imageActionBusy();
  }

  private usageMetricValue(usage: UsageMetrics | null | undefined, key: keyof UsageMetrics): number | null {
    if (!usage) return null;
    const value = usage[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (key === 'total') {
      const input = typeof usage.input === 'number' ? usage.input : 0;
      const output = typeof usage.output === 'number' ? usage.output : 0;
      const total = input + output;
      return total > 0 ? total : null;
    }
    return null;
  }

  private selectedModelMetadata(): ModelMetadataEntry | null {
    const metadata = this._catalog.modelMetadata || {};
    const selected = String(this.selectedModel() || '').trim();
    if (!selected) return null;

    const direct = metadata[selected];
    if (direct) {
      const canonical = String(direct.canonicalModelId || '').trim();
      if (canonical && metadata[canonical]) return metadata[canonical];
      return direct;
    }

    for (const [prefix, meta] of Object.entries(metadata)) {
      if (!selected.startsWith(prefix)) continue;
      const canonical = String(meta.canonicalModelId || '').trim();
      if (canonical && metadata[canonical]) return metadata[canonical];
      return meta;
    }
    return null;
  }

  private emptyUsageScope(): UsageScope {
    return {
      totals: {
        input: 0,
        output: 0,
        total: 0,
        reasoning: 0,
        cost: 0,
        costDisplay: '$0.000000',
      },
      rows: [],
    };
  }

  private _defaultSelectionForScope(scopeKey: string): { tier: string; model: string } {
    const normalizedScope = this._scopeKeyFromUseCase(scopeKey);
    const modelMap = this._catalog.modelMap || {};
    const tierMap = modelMap[normalizedScope] || {};
    const availableTiers = ['premium', 'standard', 'budget', 'cheapest'].filter((tier) => (tierMap[tier] || []).length > 0);

    let preferredTier = String(this._catalog.defaults?.tier || 'standard');
    if ((normalizedScope === 'voice' || normalizedScope === 'audio') && availableTiers.includes('budget')) {
      preferredTier = 'budget';
    }

    const resolvedTier = availableTiers.includes(preferredTier)
      ? preferredTier
      : (availableTiers[0] || 'standard');
    const models = Array.isArray(tierMap[resolvedTier]) ? tierMap[resolvedTier] : [];

    return {
      tier: resolvedTier,
      model: typeof models[0] === 'string' ? models[0] : '',
    };
  }

  private _sanitizeSelectionForScope(
    scopeKey: string,
    selection?: { tier?: string; model?: string },
  ): { tier: string; model: string } {
    const normalizedScope = this._scopeKeyFromUseCase(scopeKey);
    const defaults = this._defaultSelectionForScope(normalizedScope);
    const modelMap = this._catalog.modelMap || {};
    const tierMap = modelMap[normalizedScope] || {};
    const availableTiers = ['premium', 'standard', 'budget', 'cheapest'].filter((tier) => (tierMap[tier] || []).length > 0);
    const resolvedTier = selection?.tier && availableTiers.includes(selection.tier)
      ? selection.tier
      : defaults.tier;
    const models = Array.isArray(tierMap[resolvedTier]) ? tierMap[resolvedTier].filter((item): item is string => typeof item === 'string' && !!item.trim()) : [];
    const resolvedModel = selection?.model && models.includes(selection.model)
      ? selection.model
      : (models[0] || '');

    return {
      tier: resolvedTier,
      model: resolvedModel,
    };
  }

  private _syncModelsForUseCase(preferredModel?: string): void {
    const scopeKey = this._scopeKey();
    const modelMap = this._catalog.modelMap || {};
    const tierMap = modelMap[this._effectiveUseCaseKey()] || {};
    const availableTiers = ['premium', 'standard', 'budget', 'cheapest'].filter((tier) => (tierMap[tier] || []).length > 0);
    this.tiers.set(availableTiers);
    const existingSelection = this._sanitizeSelectionForScope(scopeKey, {
      tier: this._selectedTierByScope[scopeKey],
      model: this._selectedModelByScope[scopeKey],
    });
    const resolvedTier = existingSelection.tier;
    this.selectedTier.set(resolvedTier);
    const ordered: string[] = [];
    for (const model of tierMap[resolvedTier] || []) {
      if (typeof model === 'string' && model.trim() && !ordered.includes(model)) ordered.push(model);
    }
    this.modelsForUseCase.set(ordered);
    const pick = (preferredModel && ordered.includes(preferredModel))
      ? preferredModel
      : (ordered.includes(existingSelection.model) ? existingSelection.model : (ordered[0] || ''));
    if (pick) {
      this.selectedModel.set(pick);
      this._rememberModelSelectionForScope();
      this._syncVoiceActionModelsFromSelected();
    }
    this._updateThinkingLevelsForModel();
  }

  private _rememberModelSelectionForScope(scopeKey?: string): void {
    const key = scopeKey || this._scopeKey();
    this._selectedTierByScope[key] = this.selectedTier();
    this._selectedModelByScope[key] = this.selectedModel();
  }

  private _syncVoiceActionModelsFromSelected(): void {
    const selected = this.selectedModel();
    const mode = this._effectiveUseCaseKey();
    if (!selected) return;
    if (mode === 'image' || mode === 'video') {
      this.imageModel.set(selected);
      return;
    }
    if (mode === 'audio') {
      this.audioTurnModel.set(selected);
      return;
    }
    if (mode === 'transcription') {
      this.transcriptionModel.set(selected);
      return;
    }
    if (mode === 'tts') {
      this.ttsModel.set(selected);
    }
  }

  assistantVoiceOptions(): string[] {
    const meta = this.selectedModelMetadata();
    const configured = Array.isArray(meta?.assistantVoices)
      ? meta!.assistantVoices.map((voice) => String(voice || '').trim()).filter((voice) => !!voice)
      : [];
    if (configured.length > 0) return configured;
    return ['ash'];
  }

  ttsVoiceOptions(): string[] {
    const meta = this.selectedModelMetadata();
    const configured = Array.isArray(meta?.ttsVoices)
      ? meta!.ttsVoices.map((voice) => String(voice || '').trim()).filter((voice) => !!voice)
      : [];
    if (configured.length > 0) return configured;
    return ['alloy'];
  }

  private _syncVoiceOptionsForSelectedModel(): void {
    const assistantVoices = this.assistantVoiceOptions();
    const ttsVoices = this.ttsVoiceOptions();
    if (!assistantVoices.includes(this.audioTurnVoice())) {
      this.audioTurnVoice.set(assistantVoices.includes('ash') ? 'ash' : assistantVoices[0]);
    }
    if (!ttsVoices.includes(this.ttsVoice())) {
      this.ttsVoice.set(ttsVoices.includes('alloy') ? 'alloy' : ttsVoices[0]);
    }
  }

  private _syncPromptDropdownValue(): void {
    this.promptDropdownValue.set(this.promptPresetId() || '');
  }

  private effectiveModelForPricing(): string {
    const useCase = this._effectiveUseCaseKey();
    if (useCase === 'audio') return this.audioTurnModel() || this.selectedModel();
    if (useCase === 'transcription') return this.transcriptionModel() || this.selectedModel();
    if (useCase === 'tts') return this.ttsModel() || this.selectedModel();
    return this.selectedModel();
  }

  useCaseRoute(useCase: string): string {
    return ShellPageComponent.USE_CASE_ROUTE_MAP[this._normalizeTopLevelUseCase(useCase)] || '/chat-reasoning';
  }

  voiceModeRoute(mode: VoiceMode): string {
    return ShellPageComponent.VOICE_MODE_ROUTE_MAP[mode];
  }

  navigateUseCase(useCase: string, event?: Event): void {
    if (event) event.preventDefault();
    if (this.requestPending()) return;
    const normalized = this._normalizeTopLevelUseCase(useCase);
    const mode = normalized === 'voice' ? (this._isVoiceMode(this.voiceMode()) ? this.voiceMode() : 'realtime') : undefined;
    this._navigateToUseCase(normalized, mode);
  }

  navigateVoiceMode(mode: string, event?: Event): void {
    if (event) event.preventDefault();
    if (this.requestPending()) return;
    const normalized = this._isVoiceMode(mode) ? mode : 'realtime';
    this._navigateToUseCase('voice', normalized);
  }

  requestPending(): boolean {
    return this.sending()
      || this.loadingSession()
      || this.imageActionBusy()
      || this.ttsBusy()
      || this.embedTextBusy()
      || this.embedIndexBusy()
      || this.embedSearchBusy();
  }

  toggleLayoutLock(event?: Event): void {
    event?.stopPropagation();
    this.layoutLocked.update((value) => !value);
  }

  layoutLockLabel(): string {
    return this.layoutLocked() ? 'Unlock section layout' : 'Lock section layout';
  }

  isUseCaseActive(useCase: string): boolean {
    return this.selectedUseCase() === this._normalizeTopLevelUseCase(useCase);
  }

  isVoiceModeActive(mode: VoiceMode): boolean {
    return this.selectedUseCase() === 'voice' && this.voiceMode() === mode;
  }

  isCoreTab(): boolean {
    const useCase = this.selectedUseCase();
    return useCase === 'general' || useCase === 'reasoning' || useCase === 'deep' || useCase === 'coding' || useCase === 'search';
  }

  isComputerTab(): boolean {
    return this.selectedUseCase() === 'computer';
  }

  isVisualMediaTab(): boolean {
    return this.selectedUseCase() === 'image';
  }

  isImageMediaMode(): boolean {
    return this.isVisualMediaTab() && this.mediaMode() === 'image';
  }

  setMediaMode(mode: string): void {
    this.mediaMode.set(mode === 'video' ? 'video' : 'image');
  }

  isEmbeddingsTab(): boolean {
    return this.selectedUseCase() === 'embeddings';
  }

  isDeepResearchTab(): boolean {
    return this.selectedUseCase() === 'deep';
  }

  shouldSwapUserAssistantOrientation(): boolean {
    const useCase = this.selectedUseCase();
    return useCase === 'general' || useCase === 'reasoning' || useCase === 'deep' || useCase === 'coding';
  }

  useCaseLabel(useCase: string): string {
    return ShellPageComponent.USE_CASE_LABEL_OVERRIDES[useCase] || useCase;
  }

  private _navigateToUseCase(useCase: string, voiceMode?: VoiceMode): void {
    const normalizedUseCase = this._normalizeTopLevelUseCase(useCase);
    if (normalizedUseCase === 'voice') {
      const modeCandidate = voiceMode || this.voiceMode();
      const normalizedMode: VoiceMode = this._isVoiceMode(modeCandidate) ? modeCandidate : 'realtime';
      void this.router.navigateByUrl(this.voiceModeRoute(normalizedMode));
      return;
    }
    void this.router.navigateByUrl(this.useCaseRoute(normalizedUseCase));
  }

  private _applyRouteContext(useCase: string, voiceMode: string): void {
    const previousScopeKey = this._scopeKey();
    this._rememberScopeState(previousScopeKey);
    const normalizedUseCase = this._normalizeTopLevelUseCase(useCase);
    const normalizedVoiceMode = this._isVoiceMode(voiceMode) ? voiceMode : 'realtime';
    const useCaseChanged = this.selectedUseCase() !== normalizedUseCase;
    const voiceModeChanged = normalizedUseCase === 'voice' && this.voiceMode() !== normalizedVoiceMode;

    this.selectedUseCase.set(normalizedUseCase);
    if (normalizedUseCase !== 'image') {
      this.mediaMode.set('image');
    }
    if (normalizedUseCase !== 'voice') {
      this.endRealtimeSession();
      this._stopActiveRecorder(false);
      this.turnRecorderState.set('idle');
      this.transcribeRecorderState.set('idle');
      this._pendingTurnRecordingFile = null;
    }
    if (normalizedUseCase === 'voice') {
      this.voiceMode.set(normalizedVoiceMode);
    }
    if (normalizedUseCase === 'deep' && !this.deepResearchDataSourceSelected()) {
      this.deepResearchTools.set({
        ...this.deepResearchTools(),
        webSearch: true,
      });
    }
    if (!this.showPromptControl()) {
      this.closePromptPresetModal();
    } else {
      this._syncPromptDropdownValue();
    }
    this._syncModelsForUseCase();
    this._syncVoiceActionModelsFromSelected();
    this._syncVoiceOptionsForSelectedModel();
    this._applyThinkingSelectionForUseCase(normalizedUseCase);
    const nextScopeKey = this._scopeKey();
    this._restoreScopeState(nextScopeKey);
    this.closeResponseDownloadMenu();

    if (useCaseChanged || voiceModeChanged) {
      const scopedSelectedSession = this._selectedSessionIdByScope[nextScopeKey] || '';
      if (scopedSelectedSession && this.sessions().some((session) => session.id === scopedSelectedSession)) {
        this.selectedSessionId.set(scopedSelectedSession);
        void this.loadSession(scopedSelectedSession);
      } else {
        const fallback = this.visibleSessions()[0];
        if (fallback) {
          this.selectedSessionId.set(fallback.id);
          this._selectedSessionIdByScope[nextScopeKey] = fallback.id;
          void this.loadSession(fallback.id);
        } else {
          void this.startNewSession();
        }
      }
      void this.loadUsage();
      this.refreshCatalogView();
    }
  }

  private _orderUseCases(useCases: string[]): string[] {
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const key of ShellPageComponent.PREFERRED_USE_CASE_ORDER) {
      if (useCases.includes(key) && !seen.has(key)) {
        seen.add(key);
        ordered.push(key);
      }
    }
    const remaining = useCases
      .filter((key) => !seen.has(key) && !ShellPageComponent.HIDDEN_TOP_LEVEL_USE_CASES.has(key))
      .sort((a, b) => a.localeCompare(b));
    return [...ordered, ...remaining];
  }

  private _normalizeTopLevelUseCase(useCase: string): string {
    const normalized = String(useCase || '').trim();
    if (normalized === 'video') return 'image';
    if (ShellPageComponent.HIDDEN_TOP_LEVEL_USE_CASES.has(normalized)) return 'voice';
    return normalized || 'general';
  }

  private _isVoiceMode(mode: string): mode is VoiceMode {
    return mode === 'realtime' || mode === 'turn' || mode === 'transcribe' || mode === 'tts';
  }

  private _voiceModeForUseCase(useCase: string): VoiceMode {
    if (useCase === 'audio') return 'turn';
    if (useCase === 'transcription') return 'transcribe';
    if (useCase === 'tts') return 'tts';
    return 'realtime';
  }

  private _effectiveUseCaseKey(): string {
    const useCase = this.selectedUseCase();
    if (useCase === 'image' && this.mediaMode() === 'video') return 'video';
    if (useCase !== 'voice') return useCase;
    const mode = this.voiceMode();
    if (mode === 'turn') return 'audio';
    if (mode === 'transcribe') return 'transcription';
    if (mode === 'tts') return 'tts';
    return 'voice';
  }

  private _scopeKey(): string {
    return this._scopeKeyFromUseCase(this._effectiveUseCaseKey());
  }

  private _scopeKeyFromUseCase(useCase: string): string {
    const normalized = String(useCase || '').trim();
    if (normalized === 'video') return 'image';
    return normalized || 'general';
  }

  private async _startRecorder(mode: 'turn' | 'transcribe'): Promise<boolean> {
    if (!navigator?.mediaDevices?.getUserMedia) {
      this.voiceStatus.set('Microphone is not supported in this browser.');
      return false;
    }
    if (this._activeRecorder) this._stopActiveRecorder(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      this._recordedChunks = [];
      this._activeRecorder = recorder;
      this._activeRecorderMode = mode;
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) this._recordedChunks.push(event.data);
      };
      recorder.onerror = () => {
        this.voiceStatus.set('Recording failed.');
      };
      recorder.onstop = () => {
        const chunks = [...this._recordedChunks];
        this._recordedChunks = [];
        const mime = chunks[0]?.type || 'audio/webm';
        const blob = new Blob(chunks, { type: mime });
        for (const track of stream.getTracks()) track.stop();
        this._activeRecorder = null;
        this._activeRecorderMode = null;
        if (!chunks.length || blob.size === 0) return;
        if (mode === 'turn') {
          this._pendingTurnRecordingFile = new File([blob], 'turn-recording.webm', { type: mime });
          this.turnRecorderState.set('ready');
          this.voiceStatus.set('Recording ready. Press Send.');
          return;
        }
        this.transcribeRecorderState.set('idle');
        const file = new File([blob], 'transcription-recording.webm', { type: mime });
        this._submitTranscriptionAudioFile(file, 'recorded');
      };
      recorder.start();
      return true;
    } catch (error: unknown) {
      this.error.set(this._errorMessage(error));
      this.voiceStatus.set('Recording start failed.');
      return false;
    }
  }

  private _stopActiveRecorder(keepData: boolean): void {
    const recorder = this._activeRecorder;
    const mode = this._activeRecorderMode;
    if (!recorder) return;
    if (!keepData) this._recordedChunks = [];
    if (recorder.state !== 'inactive') recorder.stop();
    if (!keepData) {
      const stream = recorder.stream;
      for (const track of stream.getTracks()) track.stop();
      this._activeRecorder = null;
      this._activeRecorderMode = null;
      if (mode === 'turn') this.turnRecorderState.set('idle');
      if (mode === 'transcribe') this.transcribeRecorderState.set('idle');
    }
  }

  private _submitTurnAudioFile(file: File): void {
    const sessionId = this._ensureSessionId();
    this.voiceStatus.set('Processing audio turn...');
    this.api
      .createAudioTurn({
        sessionId,
        model: this.audioTurnModel(),
        useCase: 'audio',
        voice: this.audioTurnVoice(),
        file,
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.voiceStatus.set('Audio turn complete.');
          if (payload.sessionView) {
            this.messages.set(payload.sessionView.messages || []);
            this._refreshImageWorkspaceItems();
          }
          if (payload.usageView) this.usageView.set(payload.usageView);
          if (payload.audio && payload.audioMime) {
            this.ttsAudioUrl.set(`data:${payload.audioMime};base64,${payload.audio}`);
          }
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.voiceStatus.set('Audio turn failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  private _submitTranscriptionAudioFile(file: File, sourceKind: 'uploaded' | 'recorded'): void {
    const sessionId = this._ensureSessionId();
    this.voiceStatus.set('Transcribing audio...');
    this.api
      .createTranscriptionTurn({
        sessionId,
        model: this.transcriptionModel(),
        useCase: 'transcription',
        sourceKind,
        file,
      })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (payload) => {
          this.voiceStatus.set(payload.timestampsAvailable ? 'Transcription complete (timestamps available).' : 'Transcription complete.');
          if (payload.sessionView) {
            this.messages.set(payload.sessionView.messages || []);
            this._refreshImageWorkspaceItems();
          }
          if (payload.usageView) this.usageView.set(payload.usageView);
          void this.refreshSessions();
        },
        error: (error: unknown) => {
          this.voiceStatus.set('Transcription failed.');
          this.error.set(this._errorMessage(error));
        },
      });
  }

  private _rememberScopeState(scopeKey: string): void {
    if (!scopeKey) return;
    this._selectedSessionIdByScope[scopeKey] = this.selectedSessionId();
    this._composerDraftByScope[scopeKey] = this.messageInput();
    this._showArchivedByScope[scopeKey] = this.showArchivedSessions();
    this._rememberModelSelectionForScope(scopeKey);
  }

  private includeWebSearchPayloadValue(): boolean | undefined {
    if (!this.showComposerWebSearchToggle()) return undefined;
    return this.includeWebSearch() ? true : undefined;
  }

  private _restoreScopeState(scopeKey: string): void {
    if (!scopeKey) return;
    this.showArchivedSessions.set(this._showArchivedByScope[scopeKey] === true);
    this.messageInput.set(this._composerDraftByScope[scopeKey] || '');
    this.selectedSessionId.set(this._selectedSessionIdByScope[scopeKey] || '');
  }

  private _supportsPromptSetupForUseCase(useCase: string): boolean {
    return ShellPageComponent.PROMPT_ENABLED_USE_CASES.has(String(useCase || '').trim());
  }

  private effectiveThinkingEffort(): string | undefined {
    if (!this.showThinkingControl()) return undefined;
    const selected = String(this.selectedThinkingLevel() || '').trim();
    if (!selected || selected === 'none') return undefined;
    return selected;
  }

  private _deepResearchSelectionPayload(): DeepResearchToolsSelection {
    const value = this.deepResearchTools();
    return {
      webSearch: !!value.webSearch,
      codeInterpreter: !!value.codeInterpreter,
      fileSearch: !!value.fileSearch,
      mcp: !!value.mcp,
    };
  }

  private _deepResearchMcpProfilePayload(): string | undefined {
    const value = this.deepResearchTools();
    if (!value.mcp) return undefined;
    const profileId = String(value.mcpProfileId || '').trim();
    return profileId || undefined;
  }

  private _ensureDeepResearchMcpProfileSelection(nextState?: DeepResearchToolsSelection & { mcpProfileId: string }): void {
    const next = nextState || { ...this.deepResearchTools() };
    const selectedId = String(next.mcpProfileId || '').trim();
    const valid = !!selectedId && this.mcpProfiles().some((profile) => profile.id === selectedId);
    if (valid) return;
    const fallback = this.mcpProfiles().find((profile) => profile.isDefault) || this.mcpProfiles()[0];
    next.mcpProfileId = fallback ? String(fallback.id || '').trim() : '';
  }

  private _normalizeThinkingLevels(levels: Array<{ key?: string; label?: string }> | null | undefined): ThinkingLevelOption[] {
    const normalized: ThinkingLevelOption[] = [];
    for (const level of levels || []) {
      const key = String(level?.key || '').trim();
      if (!key || normalized.some((item) => item.key === key)) continue;
      normalized.push({
        key,
        label: String(level?.label || key).trim() || key,
      });
    }
    return normalized;
  }

  private _applyThinkingPolicy(): void {
    const policy = this._catalog?.thinkingPolicy || {};
    this._thinkingEnabledUseCases = new Set(
      (Array.isArray(policy.enabledUseCases) ? policy.enabledUseCases : []).map((useCase) => this._normalizeTopLevelUseCase(useCase)),
    );
    this._thinkingDefaultLevels = this._normalizeThinkingLevels(policy.defaultLevels);
    if (this._thinkingDefaultLevels.length === 0) {
      this._thinkingDefaultLevels = [
        { key: 'none', label: 'None' },
        { key: 'low', label: 'Low' },
        { key: 'medium', label: 'Medium' },
        { key: 'high', label: 'High' },
      ];
    }
    this._thinkingLevelsByPrefix = {};
    const overrides = policy.overridesByModelPrefix || {};
    for (const [prefix, levels] of Object.entries(overrides)) {
      const normalizedPrefix = String(prefix || '').trim();
      const normalizedLevels = this._normalizeThinkingLevels(levels);
      if (!normalizedPrefix || normalizedLevels.length === 0) continue;
      this._thinkingLevelsByPrefix[normalizedPrefix] = normalizedLevels;
    }
  }

  private _thinkingLevelsOverrideForModel(model: string): ThinkingLevelOption[] | null {
    const selectedModel = String(model || '').trim();
    if (!selectedModel) return null;
    for (const prefix of Object.keys(this._thinkingLevelsByPrefix)) {
      if (selectedModel.startsWith(prefix)) return this._thinkingLevelsByPrefix[prefix];
    }
    return null;
  }

  private _updateThinkingLevelsForModel(model?: string): void {
    const selectedModel = String(model || this.selectedModel() || '').trim();
    const levels = this._thinkingLevelsOverrideForModel(selectedModel) || this._thinkingDefaultLevels;
    this.thinkingLevelsForModel.set(levels);
    this._clampThinkingLevel();
  }

  private _defaultThinkingKey(): string {
    const requested = String(this._catalog?.defaults?.thinking || 'medium').trim() || 'medium';
    const allowed = this.thinkingLevelsForModel().map((level) => level.key);
    if (allowed.includes(requested)) return requested;
    return allowed[0] || 'medium';
  }

  private _clampThinkingLevel(): void {
    const valid = this.thinkingLevelsForModel().map((level) => level.key);
    if (valid.length === 0) {
      this.selectedThinkingLevel.set('medium');
      return;
    }
    const current = String(this.selectedThinkingLevel() || '').trim();
    if (!valid.includes(current)) {
      this.selectedThinkingLevel.set(this._defaultThinkingKey());
    }
  }

  private _rememberThinkingSelectionForUseCase(useCase?: string): void {
    const key = this._normalizeTopLevelUseCase(useCase || this.selectedUseCase());
    this._thinkingSelectionByUseCase[key] = String(this.selectedThinkingLevel() || '').trim();
  }

  private _applyThinkingSelectionForUseCase(useCase: string): void {
    const normalizedUseCase = this._normalizeTopLevelUseCase(useCase);
    this._updateThinkingLevelsForModel();
    const remembered = String(this._thinkingSelectionByUseCase[normalizedUseCase] || '').trim();
    if (remembered) this.selectedThinkingLevel.set(remembered);
    else this.selectedThinkingLevel.set(this._defaultThinkingKey());
    this._clampThinkingLevel();
    this._rememberThinkingSelectionForUseCase(normalizedUseCase);
  }

  private _errorMessage(error: unknown): string {
    const payload = error as {
      status?: number;
      statusText?: string;
      message?: string;
      error?: unknown;
    };
    const nested = payload?.error as {
      error?: string;
      message?: string;
      code?: string;
      errorCode?: string;
      requestId?: string;
    } | null;

    const fromNestedError = typeof nested?.error === 'string' ? nested.error.trim() : '';
    if (fromNestedError) return fromNestedError;

    const fromNestedMessage = typeof nested?.message === 'string' ? nested.message.trim() : '';
    if (fromNestedMessage) return fromNestedMessage;

    if (typeof payload?.error === 'string' && payload.error.trim()) {
      return payload.error.trim();
    }

    const status = Number(payload?.status || 0);
    const statusText = String(payload?.statusText || '').trim();
    const genericMessage = String(payload?.message || '').trim();
    const code = typeof nested?.code === 'string'
      ? nested.code.trim()
      : (typeof nested?.errorCode === 'string' ? nested.errorCode.trim() : '');
    const requestId = typeof nested?.requestId === 'string'
      ? nested.requestId.trim()
      : (typeof (payload as { requestId?: unknown })?.requestId === 'string'
        ? String((payload as { requestId?: string }).requestId).trim()
        : '');
    const statusLabel = status > 0 ? `HTTP ${status}${statusText ? ` ${statusText}` : ''}` : '';
    const tail = [code ? `code: ${code}` : '', requestId ? `request: ${requestId}` : ''].filter(Boolean).join(' · ');

    if (statusLabel || genericMessage) {
      const base = [statusLabel, genericMessage].filter(Boolean).join(' — ');
      return tail ? `${base} (${tail})` : base;
    }
    return 'Request failed in Angular migration shell.';
  }

  private _loadWebSearchByUseCase(): Record<string, boolean> {
    try {
      const raw = localStorage.getItem(ShellPageComponent.WEB_SEARCH_SELECTIONS_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      return {
        general: parsed?.['general'] === true,
        reasoning: parsed?.['reasoning'] === true,
      };
    } catch {
      return {};
    }
  }

  private _persistWebSearchByUseCase(): void {
    try {
      localStorage.setItem(
        ShellPageComponent.WEB_SEARCH_SELECTIONS_KEY,
        JSON.stringify({
          general: this._includeWebSearchByUseCase['general'] === true,
          reasoning: this._includeWebSearchByUseCase['reasoning'] === true,
        }),
      );
    } catch {}
  }

  private _prettyJson(value: unknown): string {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  private _ensureSessionId(): string {
    const scopeKey = this._scopeKey();
    let sessionId = this.selectedSessionId() || this._selectedSessionIdByScope[scopeKey] || '';
    if (!sessionId) {
      const randomUuid = globalThis.crypto?.randomUUID;
      if (typeof randomUuid !== 'function') {
        throw new Error('Session ID generation requires browser support for crypto.randomUUID().');
      }
      sessionId = randomUuid.call(globalThis.crypto).replace(/[^a-zA-Z0-9_-]/g, '');
      this.selectedSessionId.set(sessionId);
      this._selectedSessionIdByScope[scopeKey] = sessionId;
    }
    return sessionId;
  }

  private _refreshImageWorkspaceItems(): void {
    this.visualService.refreshWorkspaceItems(this.messages());
  }

  private _updateImagePayloadMetaLocal(
    messageId: number,
    patch: { favorite?: boolean; hiddenInWorkspace?: boolean; projectId?: string | null },
  ): void {
    this.messages.set(this.visualService.updateImagePayloadMetaLocal(this.messages(), messageId, patch));
  }

  private _updateImagePayloadProjectForAll(projectId: string, nextProjectId: string | null): void {
    this.messages.set(this.visualService.updateImagePayloadProjectForAll(this.messages(), projectId, nextProjectId));
  }

  private _snapshotFromWorkspaceItem(selected: ShellPageWorkspaceImage): ShellPageImageActionSnapshot | null {
    return this.visualService.snapshotFromWorkspaceItem(selected);
  }

  private _applyImageSnapshot(snapshot: ShellPageImageActionSnapshot, includePrompt: boolean): void {
    this.visualService.applyImageSnapshot(snapshot, includePrompt);
  }

  private _imageRetrySnapshotFromMessage(message: SessionMessage): ShellPageImageActionSnapshot | null {
    return this.visualService.imageRetrySnapshotFromMessage(message);
  }

  private _setAttachmentBusy(attachmentId: string, busy: boolean): void {
    const next = { ...this.attachmentBusyIds() };
    if (busy) {
      next[attachmentId] = true;
    } else {
      delete next[attachmentId];
    }
    this.attachmentBusyIds.set(next);
    this.attachmentService.busyIds.set(next);
  }

  private _copyText(value: string, onSuccess?: () => void): void {
    const text = String(value || '');
    if (!text) return;
    const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (!clipboard || typeof clipboard.writeText !== 'function') {
      if (this._legacyCopyToClipboard(text)) {
        if (onSuccess) onSuccess();
        return;
      }
      this.error.set('Clipboard is unavailable.');
      return;
    }
    void clipboard.writeText(text).then(
      () => {
        if (onSuccess) onSuccess();
      },
      () => {
        if (this._legacyCopyToClipboard(text)) {
          if (onSuccess) onSuccess();
          return;
        }
        this.error.set('Could not copy prompt.');
      },
    );
  }

  private _legacyCopyToClipboard(text: string): boolean {
    if (typeof document === 'undefined') return false;
    const value = String(text || '');
    if (!value) return false;
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', 'true');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch {
      copied = false;
    } finally {
      document.body.removeChild(textarea);
    }
    return copied;
  }

  private _imageFilename(selected: ShellPageWorkspaceImage): string {
    return this.visualService.imageFilename(selected);
  }

  private _downloadDataUrl(dataUrl: string, filename: string): void {
    const anchor = document.createElement('a');
    anchor.href = dataUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  private async _downloadFromEndpoint(url: string, fallbackFilename: string): Promise<void> {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        this.error.set(`Download failed (${response.status})`);
        return;
      }
      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const nameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
      const fileName = (nameMatch && nameMatch[1]) || fallbackFilename;
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      this.error.set('Download failed.');
    }
  }
}
