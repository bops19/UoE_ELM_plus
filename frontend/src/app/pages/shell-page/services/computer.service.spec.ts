import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { BackendApiService, ComputerRunSnapshot } from '../../../core/backend-api.service';
import { ComputerService } from './computer.service';

describe('ComputerService', () => {
  let service: ComputerService;
  let api: {
    startComputerRun: ReturnType<typeof vi.fn>;
    stepComputerRun: ReturnType<typeof vi.fn>;
    closeComputerRun: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    api = {
      startComputerRun: vi.fn(),
      stepComputerRun: vi.fn(),
      closeComputerRun: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [ComputerService, { provide: BackendApiService, useValue: api }],
    });

    service = TestBed.inject(ComputerService);
  });

  it('startRun stores run snapshot', async () => {
    const snapshot: ComputerRunSnapshot = {
      runId: 'run-1',
      status: 'running',
      timeline: [],
    };
    api.startComputerRun.mockReturnValue(of(snapshot));

    const result = await service.startRun({
      sessionId: 's1',
      userText: 'open page',
      model: 'computer-use-preview',
      startUrl: 'https://example.com',
    });

    expect(result).toEqual(snapshot);
    expect(service.run()).toEqual(snapshot);
  });

  it('stepRun updates run snapshot', async () => {
    const stepSnapshot: ComputerRunSnapshot = {
      runId: 'run-1',
      status: 'awaiting_input',
      timeline: [],
    };
    api.stepComputerRun.mockReturnValue(of(stepSnapshot));

    const result = await service.stepRun('run-1', [{ decision: 'allow' }]);

    expect(result).toEqual(stepSnapshot);
    expect(service.run()).toEqual(stepSnapshot);
    expect(api.stepComputerRun).toHaveBeenCalledWith('run-1', [{ decision: 'allow' }]);
  });

  it('closeRun clears run state', async () => {
    service.run.set({ runId: 'run-1', status: 'running', timeline: [] });
    api.closeComputerRun.mockReturnValue(of({ ok: true, runId: 'run-1', status: 'closed' }));

    await service.closeRun('run-1');

    expect(service.run()).toBe(null);
    expect(api.closeComputerRun).toHaveBeenCalledWith('run-1');
  });
});
