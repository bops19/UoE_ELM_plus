import { TestBed } from '@angular/core/testing';
import { VisualService } from './visual.service';
import type { SessionMessage } from '../../../core/backend-api.service';

describe('VisualService', () => {
  let service: VisualService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(VisualService);
  });

  it('builds workspace items from assistant image messages', () => {
    const messages = [
      {
        id: 42,
        role: 'assistant',
        msgType: 'image',
        createdAt: Date.now(),
        payload: {
          b64: 'abc',
          mime: 'image/png',
          prompt: 'test prompt',
          model: 'gpt-image-1',
          size: 'square',
        },
      },
    ] as unknown as SessionMessage[];

    service.refreshWorkspaceItems(messages);

    expect(service.imageWorkspaceItems().length).toBe(1);
    expect(service.selectedWorkspaceImage()?.messageId).toBe(42);
    expect(service.imagePromptHistoryItems().length).toBe(1);
  });

  it('applies image snapshot to visual controls', () => {
    service.applyImageSnapshot(
      {
        prompt: 'new prompt',
        model: 'gpt-image-1',
        moderation: 'low',
        style: 'illustration',
        size: 'portrait',
        count: 2,
      },
      true,
    );

    expect(service.imagePrompt()).toBe('new prompt');
    expect(service.imageModeration()).toBe('low');
    expect(service.imageStyle()).toBe('illustration');
    expect(service.imageSize()).toBe('portrait');
    expect(service.imageCount()).toBe(2);
  });
});
