import { Injectable, signal } from '@angular/core';
import type { ImageProject, ImageResult, SessionMessage } from '../../../core/backend-api.service';
import type {
  ShellPageImageActionSnapshot,
  ShellPagePromptHistoryItem,
  ShellPageWorkspaceImage,
} from '../shell-page.types';

@Injectable({ providedIn: 'root' })
export class VisualService {
  readonly imagePrompt = signal('');
  readonly imageEditInstruction = signal('');
  readonly imageModel = signal('gpt-image-1');
  readonly imageModeration = signal<'auto' | 'low'>('auto');
  readonly imageStyle = signal<'photorealistic' | 'illustration' | '3d_render' | 'poster' | 'minimal'>('photorealistic');
  readonly imageSize = signal<'square' | 'portrait' | 'landscape'>('square');
  readonly imageCount = signal<1 | 2 | 4>(1);
  readonly imageStatus = signal('');
  readonly imageActionBusy = signal(false);
  readonly imageActionPending = signal<'none' | 'regenerate' | 'refine' | 'variation'>('none');
  readonly imageResults = signal<ImageResult[]>([]);
  readonly imageProjects = signal<ImageProject[]>([]);
  readonly imageProjectName = signal('');
  readonly imageProjectFilterId = signal('__all__');
  readonly imageWorkspaceItems = signal<ShellPageWorkspaceImage[]>([]);
  readonly selectedWorkspaceKey = signal('');
  readonly imagePromptHistoryItems = signal<ShellPagePromptHistoryItem[]>([]);

  onImageCountChange(value: number): void {
    this.imageCount.set(this.normalizeImageCount(value));
  }

  selectedWorkspaceImage(): ShellPageWorkspaceImage | null {
    const key = this.selectedWorkspaceKey();
    if (!key) return this.imageWorkspaceItems()[0] || null;
    const selected = this.imageWorkspaceItems().find((item) => item.key === key);
    return selected || this.imageWorkspaceItems()[0] || null;
  }

  selectWorkspaceImage(item: ShellPageWorkspaceImage): void {
    this.selectedWorkspaceKey.set(item.key);
  }

  visualCanvasAspectRatio(item: ShellPageWorkspaceImage | null): string {
    const size = String(item?.size || '').toLowerCase();
    if (size.includes('portrait')) return '3 / 4';
    if (size.includes('landscape')) return '4 / 3';
    return '1 / 1';
  }

  refreshWorkspaceItems(messages: SessionMessage[]): void {
    const previousKey = this.selectedWorkspaceKey();
    const items: ShellPageWorkspaceImage[] = [];
    for (const message of messages || []) {
      if (message.role !== 'assistant' || (message.msgType || 'text') !== 'image') continue;
      const payload = message.payload && typeof message.payload === 'object' ? message.payload : {};
      const b64 = typeof payload['b64'] === 'string' ? payload['b64'] : '';
      if (!b64 || payload['hiddenInWorkspace'] === true) continue;
      const generatedAt = this.numberOrNull(payload['generatedAt']);
      items.push({
        key: typeof message.id === 'number' ? `msg-${message.id}` : `msg-${String(message.id)}`,
        messageId: typeof message.id === 'number' ? message.id : null,
        b64,
        mime: typeof payload['mime'] === 'string' ? payload['mime'] : 'image/png',
        prompt: typeof payload['prompt'] === 'string' ? payload['prompt'] : '',
        model: typeof payload['model'] === 'string' ? payload['model'] : (message.usageModel || ''),
        moderation: typeof payload['moderation'] === 'string' ? payload['moderation'] : 'auto',
        style: typeof payload['style'] === 'string' ? payload['style'] : 'photorealistic',
        size: typeof payload['size'] === 'string' ? payload['size'] : 'square',
        outputIndex: this.numberOrNull(payload['outputIndex']),
        outputTotal: this.numberOrNull(payload['outputTotal']),
        generatedAt,
        createdAt: generatedAt || this.numberOrNull(message.createdAt) || Date.now(),
        favorite: payload['favorite'] === true,
        projectId: typeof payload['projectId'] === 'string' && payload['projectId'] ? payload['projectId'] : null,
      });
    }
    items.sort((a, b) => {
      if (b.createdAt !== a.createdAt) return b.createdAt - a.createdAt;
      if (a.outputIndex !== null && b.outputIndex !== null && a.outputIndex !== b.outputIndex) return a.outputIndex - b.outputIndex;
      return 0;
    });
    const filterId = this.imageProjectFilterId();
    const filtered = filterId !== '__all__' ? items.filter((item) => item.projectId === filterId) : items;
    this.imageWorkspaceItems.set(filtered);
    this.imagePromptHistoryItems.set(this.buildImagePromptHistory(items));
    if (previousKey && filtered.some((item) => item.key === previousKey)) {
      this.selectedWorkspaceKey.set(previousKey);
      return;
    }
    this.selectedWorkspaceKey.set(filtered[0]?.key || '');
  }

  updateImagePayloadMetaLocal(
    messages: SessionMessage[],
    messageId: number,
    patch: { favorite?: boolean; hiddenInWorkspace?: boolean; projectId?: string | null },
  ): SessionMessage[] {
    return (messages || []).map((message) => {
      if ((message.msgType || 'text') !== 'image' || Number(message.id) !== Number(messageId)) return message;
      const payload = message.payload && typeof message.payload === 'object' ? { ...message.payload } : {};
      if (Object.prototype.hasOwnProperty.call(patch, 'favorite')) {
        payload['favorite'] = patch.favorite === true;
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'hiddenInWorkspace')) {
        payload['hiddenInWorkspace'] = patch.hiddenInWorkspace === true;
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'projectId')) {
        payload['projectId'] = patch.projectId || null;
      }
      return { ...message, payload };
    });
  }

  updateImagePayloadProjectForAll(
    messages: SessionMessage[],
    projectId: string,
    nextProjectId: string | null,
  ): SessionMessage[] {
    return (messages || []).map((message) => {
      if ((message.msgType || 'text') !== 'image') return message;
      const payload = message.payload && typeof message.payload === 'object' ? { ...message.payload } : {};
      if (payload['projectId'] !== projectId) return message;
      payload['projectId'] = nextProjectId;
      return { ...message, payload };
    });
  }

  snapshotFromWorkspaceItem(selected: ShellPageWorkspaceImage): ShellPageImageActionSnapshot | null {
    const prompt = String(selected.prompt || '').trim();
    if (!prompt) return null;
    const model = String(selected.model || '').trim();
    if (!model) return null;
    return {
      prompt,
      model,
      moderation: selected.moderation === 'low' ? 'low' : 'auto',
      style: this.normalizeImageStyle(selected.style),
      size: this.normalizeImageSize(selected.size),
      count: this.normalizeImageCount(selected.outputTotal || this.imageCount()),
    };
  }

  applyImageSnapshot(snapshot: ShellPageImageActionSnapshot, includePrompt: boolean): void {
    this.imageModel.set(snapshot.model);
    this.imageModeration.set(snapshot.moderation === 'low' ? 'low' : 'auto');
    this.imageStyle.set(this.normalizeImageStyle(snapshot.style));
    this.imageSize.set(this.normalizeImageSize(snapshot.size));
    this.imageCount.set(this.normalizeImageCount(snapshot.count));
    if (includePrompt) this.imagePrompt.set(snapshot.prompt);
  }

  imageRetrySnapshotFromMessage(message: SessionMessage): ShellPageImageActionSnapshot | null {
    if (!message || message.role !== 'assistant' || (message.msgType || 'text') !== 'text' || message.status !== 'error') {
      return null;
    }
    const payload = message.payload && typeof message.payload === 'object' ? message.payload : {};
    const imageRequest = payload['imageRequest'];
    if (!imageRequest || typeof imageRequest !== 'object') return null;
    if ((imageRequest as Record<string, unknown>)['retryable'] !== true) return null;
    const prompt = String((imageRequest as Record<string, unknown>)['prompt'] || '').trim();
    const model = String((imageRequest as Record<string, unknown>)['model'] || '').trim();
    if (!prompt || !model) return null;
    return {
      prompt,
      model,
      moderation: (imageRequest as Record<string, unknown>)['moderation'] === 'low' ? 'low' : 'auto',
      style: this.normalizeImageStyle(String((imageRequest as Record<string, unknown>)['style'] || '')),
      size: this.normalizeImageSize(String((imageRequest as Record<string, unknown>)['size'] || '')),
      count: this.normalizeImageCount((imageRequest as Record<string, unknown>)['count']),
    };
  }

  showImageRetryAction(message: SessionMessage): boolean {
    return !!this.imageRetrySnapshotFromMessage(message);
  }

  imageFilename(selected: ShellPageWorkspaceImage): string {
    const extension = selected.mime === 'image/jpeg' ? 'jpg' : (selected.mime === 'image/webp' ? 'webp' : 'png');
    const stamp = new Date(selected.createdAt || Date.now()).toISOString().replace(/[-:T]/g, '').slice(0, 14);
    return `image-${stamp}.${extension}`;
  }

  private numberOrNull(value: unknown): number | null {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  private normalizeImageStyle(style: string): 'photorealistic' | 'illustration' | '3d_render' | 'poster' | 'minimal' {
    if (style === 'illustration' || style === '3d_render' || style === 'poster' || style === 'minimal') return style;
    return 'photorealistic';
  }

  private normalizeImageSize(size: string): 'square' | 'portrait' | 'landscape' {
    if (size === 'portrait' || size === 'landscape') return size;
    return 'square';
  }

  private normalizeImageCount(value: unknown): 1 | 2 | 4 {
    const numeric = Number(value);
    return numeric === 2 || numeric === 4 ? numeric : 1;
  }

  private buildImagePromptHistory(items: ShellPageWorkspaceImage[]): ShellPagePromptHistoryItem[] {
    const seen = new Set<string>();
    const history: ShellPagePromptHistoryItem[] = [];
    for (const item of items || []) {
      const prompt = String(item.prompt || '').trim();
      if (!prompt) continue;
      const dedupeKey = `${prompt}::${item.model}::${item.style}::${item.size}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      history.push({
        key: `${item.key}-history`,
        prompt,
        createdAt: item.generatedAt || item.createdAt || null,
        favorite: item.favorite,
        snapshot: this.snapshotFromWorkspaceItem(item),
      });
    }
    return history.slice(0, 24);
  }
}
