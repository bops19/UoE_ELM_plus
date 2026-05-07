import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { BackendApiService, SessionView } from '../../core/backend-api.service';
import { AttachmentService } from './services/attachment.service';
import { CatalogService } from './services/catalog.service';
import { ComputerService } from './services/computer.service';
import { SessionService } from './services/session.service';
import { VoiceService } from './services/voice.service';
import { ShellPageComponent } from './shell-page.component';

describe('ShellPageComponent', () => {
  let component: ShellPageComponent;
  let api: { streamChat: ReturnType<typeof vi.fn> };
  let sessionService: { loadSession: ReturnType<typeof vi.fn>; refreshSessions: ReturnType<typeof vi.fn>; error: () => string };
  let attachmentService: {
    upload: ReturnType<typeof vi.fn>;
    setAttachments: ReturnType<typeof vi.fn>;
    busyIds: { set: ReturnType<typeof vi.fn> };
    isAttachmentBusy: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    api = {
      streamChat: vi.fn(),
    };
    sessionService = {
      loadSession: vi.fn(),
      refreshSessions: vi.fn().mockResolvedValue([]),
      error: () => '',
    };
    attachmentService = {
      upload: vi.fn(),
      setAttachments: vi.fn(),
      busyIds: { set: vi.fn() },
      isAttachmentBusy: vi.fn(() => false),
    };

    await TestBed.configureTestingModule({
      imports: [ShellPageComponent],
      providers: [
        { provide: BackendApiService, useValue: api },
        {
          provide: Router,
          useValue: {
            events: of(),
            navigate: vi.fn(),
            url: '/app/chat-reasoning',
          },
        },
        {
          provide: ActivatedRoute,
          useValue: { data: of({ useCase: 'general' }) },
        },
        { provide: CatalogService, useValue: { catalogView: { set: vi.fn(), call: vi.fn() }, loadCatalog: vi.fn(), loadPromptPresets: vi.fn(), modelCatalog: { set: vi.fn() }, promptPresets: { set: vi.fn() } } },
        { provide: SessionService, useValue: sessionService },
        { provide: AttachmentService, useValue: attachmentService },
        { provide: VoiceService, useValue: { setRealtimeResources: vi.fn(), endSession: vi.fn(), realtimeConnected: { set: vi.fn() }, realtimeMuted: { set: vi.fn() } } },
        { provide: ComputerService, useValue: { model: { set: vi.fn() }, prompt: { set: vi.fn() }, startUrl: { set: vi.fn() }, status: { set: vi.fn() }, run: { set: vi.fn() } } },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellPageComponent);
    component = fixture.componentInstance;
  });

  it('creates', () => {
    expect(component).toBeTruthy();
  });

  it('sendMessage streams chat payload and clears sending state', async () => {
    component.selectedSessionId.set('session-1');
    component.messageInput.set('hello from test');
    api.streamChat.mockImplementation(async (_payload: unknown, onEvent: (event: { done?: boolean }) => void) => {
      onEvent({ done: true });
    });
    vi.spyOn(component, 'refreshSessions').mockResolvedValue();
    vi.spyOn(component, 'loadSession').mockResolvedValue();
    vi.spyOn(component, 'loadUsage').mockResolvedValue();

    await component.sendMessage();

    expect(api.streamChat).toHaveBeenCalled();
    expect(component.sending()).toBe(false);
    expect(component.messages().some((message) => message.role === 'user')).toBe(true);
  });

  it('loadSession sets selected session and title from service result', async () => {
    const view: SessionView = {
      id: 'session-2',
      title: 'Loaded Session',
      useCase: 'general',
      messages: [],
      messageCount: 0,
      attachments: [],
    };
    sessionService.loadSession.mockResolvedValue(view);
    vi.spyOn(component, 'loadUsage').mockResolvedValue();
    vi.spyOn(component, 'refreshCatalogView').mockImplementation(() => {});

    await component.loadSession('session-2');

    expect(sessionService.loadSession).toHaveBeenCalledWith('session-2');
    expect(component.selectedSessionId()).toBe('session-2');
    expect(component.title()).toBe('Loaded Session');
  });

  it('onFilesSelected uploads attachments and resets uploading state', async () => {
    const loadSessionSpy = vi.spyOn(component, 'loadSession').mockResolvedValue();
    const refreshSessionsSpy = vi.spyOn(component, 'refreshSessions').mockResolvedValue();
    component.selectedSessionId.set('session-3');
    attachmentService.upload.mockResolvedValue([
      {
        id: 'att-1',
        name: 'notes.txt',
        mimeType: 'text/plain',
        sizeBytes: 4,
        active: true,
        usable: true,
        statusLabel: 'Ready',
        displayMeta: '4 B',
        toggleTitle: 'Toggle',
      },
    ]);
    const input = {
      files: [new File(['test'], 'notes.txt', { type: 'text/plain' })],
      value: 'notes.txt',
    } as unknown as HTMLInputElement;

    component.onFilesSelected({ target: input } as unknown as Event);
    await Promise.resolve();
    await Promise.resolve();

    expect(attachmentService.upload).toHaveBeenCalled();
    expect(loadSessionSpy).toHaveBeenCalledWith('session-3');
    expect(refreshSessionsSpy).toHaveBeenCalled();
    expect(component.uploadingFiles()).toBe(false);
  });
});
