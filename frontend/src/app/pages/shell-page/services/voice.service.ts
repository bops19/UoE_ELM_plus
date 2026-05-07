import { Injectable, OnDestroy, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class VoiceService implements OnDestroy {
  readonly realtimeConnected = signal(false);
  readonly realtimeMuted = signal(false);
  readonly status = signal('');
  readonly turnRecorderState = signal<'idle' | 'recording' | 'ready'>('idle');
  readonly transcribeRecorderState = signal<'idle' | 'recording'>('idle');
  readonly ttsBusy = signal(false);

  private peerConnection: RTCPeerConnection | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private mediaStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;

  setRealtimeResources(resources: {
    peerConnection?: RTCPeerConnection | null;
    dataChannel?: RTCDataChannel | null;
    mediaStream?: MediaStream | null;
    remoteAudio?: HTMLAudioElement | null;
  }): void {
    if (typeof resources.peerConnection !== 'undefined') this.peerConnection = resources.peerConnection;
    if (typeof resources.dataChannel !== 'undefined') this.dataChannel = resources.dataChannel;
    if (typeof resources.mediaStream !== 'undefined') this.mediaStream = resources.mediaStream;
    if (typeof resources.remoteAudio !== 'undefined') this.remoteAudio = resources.remoteAudio;
  }

  endSession(): void {
    try {
      this.dataChannel?.close();
    } catch {}
    try {
      this.peerConnection?.close();
    } catch {}
    try {
      this.mediaStream?.getTracks().forEach((track) => track.stop());
    } catch {}
    try {
      this.remoteAudio?.pause();
      this.remoteAudio?.removeAttribute('src');
    } catch {}
    this.peerConnection = null;
    this.dataChannel = null;
    this.mediaStream = null;
    this.remoteAudio = null;
    this.realtimeConnected.set(false);
    this.realtimeMuted.set(false);
  }

  ngOnDestroy(): void {
    this.endSession();
  }
}
