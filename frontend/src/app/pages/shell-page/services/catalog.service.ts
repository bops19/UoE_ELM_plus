import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BackendApiService, ModelCatalogPayload, PromptPreset, VmCatalogView } from '../../../core/backend-api.service';

@Injectable({ providedIn: 'root' })
export class CatalogService {
  readonly modelCatalog = signal<ModelCatalogPayload | null>(null);
  readonly catalogView = signal<VmCatalogView | null>(null);
  readonly promptPresets = signal<PromptPreset[]>([]);
  readonly loading = signal(false);
  readonly error = signal('');

  private readonly cache = new Map<string, { catalog: ModelCatalogPayload | null; view: VmCatalogView | null }>();

  constructor(private readonly api: BackendApiService) {}

  async loadCatalog(selectedModel?: string, voiceMode?: string): Promise<void> {
    const cacheKey = `${selectedModel || ''}::${voiceMode || ''}`;
    const cached = this.cache.get(cacheKey);
    if (cached) {
      this.modelCatalog.set(cached.catalog);
      this.catalogView.set(cached.view);
      return;
    }
    this.loading.set(true);
    this.error.set('');
    try {
      const payload = await firstValueFrom(this.api.getVmCatalog(selectedModel, voiceMode));
      const catalog = payload?.catalog || null;
      const view = payload?.catalogView || null;
      this.modelCatalog.set(catalog);
      this.catalogView.set(view);
      this.cache.set(cacheKey, { catalog, view });
    } catch (error) {
      this.error.set(String((error as { message?: string })?.message || 'Failed to load model catalog.'));
    } finally {
      this.loading.set(false);
    }
  }

  async refreshCatalogView(selectedModel?: string, voiceMode?: string): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const payload = await firstValueFrom(this.api.getVmCatalog(selectedModel, voiceMode));
      const view = payload?.catalogView || null;
      this.catalogView.set(view);
      if (payload?.catalog) this.modelCatalog.set(payload.catalog);
    } catch (error) {
      this.error.set(String((error as { message?: string })?.message || 'Failed to refresh catalog view.'));
    } finally {
      this.loading.set(false);
    }
  }

  async loadPromptPresets(): Promise<void> {
    try {
      const payload = await firstValueFrom(this.api.getPromptPresets());
      const presets = (payload?.presets || []).slice().sort((a, b) => a.name.localeCompare(b.name));
      this.promptPresets.set(presets);
    } catch (error) {
      this.error.set(String((error as { message?: string })?.message || 'Failed to load prompt presets.'));
    }
  }

  invalidate(selectedModel?: string, voiceMode?: string): void {
    if (selectedModel || voiceMode) {
      this.cache.delete(`${selectedModel || ''}::${voiceMode || ''}`);
      return;
    }
    this.cache.clear();
  }
}
