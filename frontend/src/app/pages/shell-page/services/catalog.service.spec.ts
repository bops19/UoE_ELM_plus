import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { BackendApiService, PromptPreset, VmCatalogResponse } from '../../../core/backend-api.service';
import { CatalogService } from './catalog.service';

describe('CatalogService', () => {
  let service: CatalogService;
  let api: {
    getVmCatalog: ReturnType<typeof vi.fn>;
    getPromptPresets: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    api = {
      getVmCatalog: vi.fn(),
      getPromptPresets: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [CatalogService, { provide: BackendApiService, useValue: api }],
    });

    service = TestBed.inject(CatalogService);
  });

  it('loads catalog and updates signals', async () => {
    const payload: VmCatalogResponse = {
      catalog: { defaults: { useCase: 'chat' } },
      catalogView: { selectedModel: 'gpt-5' },
    };
    api.getVmCatalog.mockReturnValue(of(payload));

    await service.loadCatalog('gpt-5', 'realtime');

    expect(api.getVmCatalog).toHaveBeenCalledWith('gpt-5', 'realtime');
    expect(service.modelCatalog()).toEqual(payload.catalog);
    expect(service.catalogView()).toEqual(payload.catalogView);
    expect(service.loading()).toBe(false);
    expect(service.error()).toBe('');
  });

  it('serves repeated loadCatalog calls from cache', async () => {
    const payload: VmCatalogResponse = {
      catalog: { defaults: { useCase: 'chat' } },
      catalogView: { selectedModel: 'cached-model' },
    };
    api.getVmCatalog.mockReturnValue(of(payload));

    await service.loadCatalog('cached-model', 'off');
    await service.loadCatalog('cached-model', 'off');

    expect(api.getVmCatalog).toHaveBeenCalledTimes(1);
    expect(service.catalogView()?.selectedModel).toBe('cached-model');
  });

  it('records an error when catalog load fails', async () => {
    api.getVmCatalog.mockReturnValue(throwError(() => new Error('network down')));

    await service.loadCatalog();

    expect(service.modelCatalog()).toBe(null);
    expect(service.catalogView()).toBe(null);
    expect(service.loading()).toBe(false);
    expect(service.error()).toContain('network down');
  });

  it('loads prompt presets sorted by name', async () => {
    const presets: PromptPreset[] = [
      { id: '2', name: 'Zulu', instructions: 'z', context: '' },
      { id: '1', name: 'Alpha', instructions: 'a', context: '' },
    ];
    api.getPromptPresets.mockReturnValue(of({ presets }));

    await service.loadPromptPresets();

    expect(service.promptPresets().map((preset) => preset.name)).toEqual(['Alpha', 'Zulu']);
  });
});
