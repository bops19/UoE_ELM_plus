import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BackendApiService, SessionSummary, SessionView } from '../../../core/backend-api.service';

@Injectable({ providedIn: 'root' })
export class SessionService {
  readonly sessions = signal<SessionSummary[]>([]);
  readonly selectedSessionId = signal('');
  readonly sessionView = signal<SessionView | null>(null);
  readonly loadingSession = signal(false);
  readonly sessionBusyId = signal('');
  readonly openSessionMenuId = signal('');
  readonly showArchivedSessions = signal(false);
  readonly renamingSessionId = signal('');
  readonly renameDraft = signal('');
  readonly error = signal('');

  constructor(private readonly api: BackendApiService) {}

  async refreshSessions(): Promise<SessionSummary[]> {
    try {
      const payload = await firstValueFrom(this.api.getSessions());
      const list = payload?.sessions || [];
      this.sessions.set(list);
      return list;
    } catch {
      return this.sessions();
    }
  }

  async loadSession(sessionId: string): Promise<SessionView | null> {
    if (!sessionId) return null;
    this.loadingSession.set(true);
    this.error.set('');
    this.selectedSessionId.set(sessionId);
    try {
      const payload = await firstValueFrom(this.api.getVmSession(sessionId));
      const view = payload?.sessionView || null;
      this.sessionView.set(view);
      return view;
    } catch (error) {
      this.error.set(String((error as { message?: string })?.message || 'Failed to load session.'));
      return null;
    } finally {
      this.loadingSession.set(false);
    }
  }

  async renameSession(sessionId: string, title: string): Promise<SessionView | null> {
    const payload = await firstValueFrom(this.api.updateSessionTitle(sessionId, title));
    return payload?.sessionView || null;
  }

  async archiveSession(sessionId: string, archived: boolean): Promise<void> {
    await firstValueFrom(this.api.archiveSession(sessionId, archived));
  }

  async clearSession(sessionId: string): Promise<SessionView | null> {
    const payload = await firstValueFrom(this.api.clearSession(sessionId));
    return payload?.sessionView || null;
  }

  async deleteSession(sessionId: string): Promise<void> {
    await firstValueFrom(this.api.deleteSession(sessionId));
  }
}
