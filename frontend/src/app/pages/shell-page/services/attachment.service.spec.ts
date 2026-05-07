import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { AttachmentRecord, BackendApiService } from '../../../core/backend-api.service';
import { AttachmentService } from './attachment.service';

describe('AttachmentService', () => {
  let service: AttachmentService;
  let api: {
    uploadAttachments: ReturnType<typeof vi.fn>;
    updateAttachment: ReturnType<typeof vi.fn>;
    deleteAttachment: ReturnType<typeof vi.fn>;
  };

  const attachment: AttachmentRecord = {
    id: 'a1',
    name: 'doc.txt',
    mimeType: 'text/plain',
    sizeBytes: 12,
    active: true,
    usable: true,
    statusLabel: 'Ready',
    displayMeta: '12 B',
    toggleTitle: 'Toggle',
  };

  beforeEach(() => {
    api = {
      uploadAttachments: vi.fn(),
      updateAttachment: vi.fn(),
      deleteAttachment: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [AttachmentService, { provide: BackendApiService, useValue: api }],
    });

    service = TestBed.inject(AttachmentService);
  });

  it('upload toggles uploadingFiles and returns uploaded files', async () => {
    const uploaded = [attachment];
    api.uploadAttachments.mockImplementation(() => {
      expect(service.uploadingFiles()).toBe(true);
      return of({ files: uploaded });
    });

    const file = new File(['content'], 'doc.txt', { type: 'text/plain' });
    const result = await service.upload('s1', 'chat', [file]);

    expect(result).toEqual(uploaded);
    expect(service.uploadingFiles()).toBe(false);
  });

  it('toggle clears busyIds after success', async () => {
    api.updateAttachment.mockImplementation(() => {
      expect(service.isAttachmentBusy(attachment.id)).toBe(true);
      return of({ file: { ...attachment, active: false } });
    });

    await service.toggle('s1', attachment);

    expect(api.updateAttachment).toHaveBeenCalledWith('s1', attachment.id, false);
    expect(service.isAttachmentBusy(attachment.id)).toBe(false);
  });

  it('toggle clears busyIds after failure', async () => {
    api.updateAttachment.mockImplementation(() => {
      expect(service.isAttachmentBusy(attachment.id)).toBe(true);
      return throwError(() => new Error('toggle failed'));
    });

    await expect(service.toggle('s1', attachment)).rejects.toThrow('toggle failed');
    expect(service.isAttachmentBusy(attachment.id)).toBe(false);
  });

  it('remove clears busyIds after success and failure', async () => {
    api.deleteAttachment.mockImplementationOnce(() => {
      expect(service.isAttachmentBusy(attachment.id)).toBe(true);
      return of({ ok: true });
    });
    await service.remove('s1', attachment.id);
    expect(service.isAttachmentBusy(attachment.id)).toBe(false);

    api.deleteAttachment.mockImplementationOnce(() => {
      expect(service.isAttachmentBusy(attachment.id)).toBe(true);
      return throwError(() => new Error('delete failed'));
    });
    await expect(service.remove('s1', attachment.id)).rejects.toThrow('delete failed');
    expect(service.isAttachmentBusy(attachment.id)).toBe(false);
  });
});
