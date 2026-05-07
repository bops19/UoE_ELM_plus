import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BackendApiService, ComputerRunSnapshot, JsonObject } from '../../../core/backend-api.service';

@Injectable({ providedIn: 'root' })
export class ComputerService {
  readonly model = signal('computer-use-preview');
  readonly prompt = signal('');
  readonly startUrl = signal('');
  readonly run = signal<ComputerRunSnapshot | null>(null);
  readonly status = signal('');

  constructor(private readonly api: BackendApiService) {}

  async startRun(payload: {
    sessionId: string;
    userText: string;
    model: string;
    startUrl?: string;
  }): Promise<ComputerRunSnapshot> {
    const snapshot = await firstValueFrom(this.api.startComputerRun(payload));
    this.run.set(snapshot || null);
    return snapshot;
  }

  async stepRun(runId: string, acknowledgedSafetyChecks?: JsonObject[]): Promise<ComputerRunSnapshot> {
    const snapshot = await firstValueFrom(this.api.stepComputerRun(runId, acknowledgedSafetyChecks));
    this.run.set(snapshot || null);
    return snapshot;
  }

  async closeRun(runId: string): Promise<void> {
    await firstValueFrom(this.api.closeComputerRun(runId));
    this.run.set(null);
  }
}
