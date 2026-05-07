import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AttachmentRecord, BackendApiService } from '../../../core/backend-api.service';

@Injectable({ providedIn: 'root' })
export class AttachmentService {
  readonly attachments = signal<AttachmentRecord[]>([]);
  readonly uploadingFiles = signal(false);
  readonly busyIds = signal<Record<string, boolean>>({});

  constructor(private readonly api: BackendApiService) {}

  setAttachments(attachments: AttachmentRecord[]): void {
    this.attachments.set(attachments || []);
  }

  isAttachmentBusy(attachmentId: string): boolean {
    return !!this.busyIds()[attachmentId];
  }

  private setBusy(attachmentId: string, busy: boolean): void {
    const next = { ...this.busyIds() };
    if (busy) next[attachmentId] = true;
    else delete next[attachmentId];
    this.busyIds.set(next);
  }

  async upload(sessionId: string, useCase: string, files: File[]): Promise<AttachmentRecord[]> {
    this.uploadingFiles.set(true);
    try {
      const payload = await firstValueFrom(this.api.uploadAttachments(sessionId, useCase, files));
      return payload?.files || [];
    } finally {
      this.uploadingFiles.set(false);
    }
  }

  async toggle(sessionId: string, attachment: AttachmentRecord): Promise<void> {
    this.setBusy(attachment.id, true);
    try {
      await firstValueFrom(this.api.updateAttachment(sessionId, attachment.id, !attachment.active));
    } finally {
      this.setBusy(attachment.id, false);
    }
  }

  async remove(sessionId: string, attachmentId: string): Promise<void> {
    this.setBusy(attachmentId, true);
    try {
      await firstValueFrom(this.api.deleteAttachment(sessionId, attachmentId));
    } finally {
      this.setBusy(attachmentId, false);
    }
  }
}
