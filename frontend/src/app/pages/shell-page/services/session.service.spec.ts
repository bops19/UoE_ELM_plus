import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { BackendApiService, SessionSummary, SessionView } from '../../../core/backend-api.service';
import { SessionService } from './session.service';

describe('SessionService', () => {
  let service: SessionService;
  let api: {
    getSessions: ReturnType<typeof vi.fn>;
    getVmSession: ReturnType<typeof vi.fn>;
    updateSessionTitle: ReturnType<typeof vi.fn>;
    archiveSession: ReturnType<typeof vi.fn>;
    clearSession: ReturnType<typeof vi.fn>;
    deleteSession: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    api = {
      getSessions: vi.fn(),
      getVmSession: vi.fn(),
      updateSessionTitle: vi.fn(),
      archiveSession: vi.fn(),
      clearSession: vi.fn(),
      deleteSession: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [SessionService, { provide: BackendApiService, useValue: api }],
    });

    service = TestBed.inject(SessionService);
  });

  it('refreshSessions sets sessions from API response', async () => {
    const sessions: SessionSummary[] = [
      {
        id: 's1',
        title: 'Test Session',
        useCase: 'chat',
        archivedAt: null,
        createdAt: 1,
        updatedAt: 2,
        messageCount: 1,
        attachmentCount: 0,
      },
    ];
    api.getSessions.mockReturnValue(of({ sessions }));

    const result = await service.refreshSessions();

    expect(result).toEqual(sessions);
    expect(service.sessions()).toEqual(sessions);
  });

  it('refreshSessions falls back to current sessions on failure', async () => {
    const fallback: SessionSummary = {
      id: 'existing',
      title: 'Existing',
      useCase: 'chat',
      archivedAt: null,
      createdAt: 1,
      updatedAt: 1,
      messageCount: 0,
      attachmentCount: 0,
    };
    service.sessions.set([fallback]);
    api.getSessions.mockReturnValue(throwError(() => new Error('down')));

    const result = await service.refreshSessions();

    expect(result).toEqual([fallback]);
    expect(service.sessions()).toEqual([fallback]);
  });

  it('loadSession updates loading and selected session state on success', async () => {
    const view: SessionView = {
      id: 's1',
      title: 'Loaded',
      useCase: 'chat',
      messages: [],
      messageCount: 0,
    };
    api.getVmSession.mockImplementation(() => {
      expect(service.loadingSession()).toBe(true);
      return of({ sessionView: view });
    });

    const result = await service.loadSession('s1');

    expect(result).toEqual(view);
    expect(service.selectedSessionId()).toBe('s1');
    expect(service.sessionView()).toEqual(view);
    expect(service.loadingSession()).toBe(false);
    expect(service.error()).toBe('');
  });

  it('loadSession records error and clears loading on failure', async () => {
    api.getVmSession.mockReturnValue(throwError(() => new Error('cannot load')));

    const result = await service.loadSession('broken');

    expect(result).toBe(null);
    expect(service.selectedSessionId()).toBe('broken');
    expect(service.loadingSession()).toBe(false);
    expect(service.error()).toContain('cannot load');
  });

  it('proxies rename/archive/clear/delete calls to backend API', async () => {
    const view: SessionView = {
      id: 's1',
      title: 'Renamed',
      useCase: 'chat',
      messages: [],
      messageCount: 0,
    };
    api.updateSessionTitle.mockReturnValue(of({ sessionView: view }));
    api.archiveSession.mockReturnValue(of({ ok: true, archivedAt: 123 }));
    api.clearSession.mockReturnValue(of({ ok: true, sessionView: view }));
    api.deleteSession.mockReturnValue(of({ ok: true }));

    const renamed = await service.renameSession('s1', 'Renamed');
    await service.archiveSession('s1', true);
    const cleared = await service.clearSession('s1');
    await service.deleteSession('s1');

    expect(renamed).toEqual(view);
    expect(cleared).toEqual(view);
    expect(api.updateSessionTitle).toHaveBeenCalledWith('s1', 'Renamed');
    expect(api.archiveSession).toHaveBeenCalledWith('s1', true);
    expect(api.clearSession).toHaveBeenCalledWith('s1');
    expect(api.deleteSession).toHaveBeenCalledWith('s1');
  });
});
