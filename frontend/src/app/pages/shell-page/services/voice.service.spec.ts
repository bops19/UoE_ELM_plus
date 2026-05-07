import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { VoiceService } from './voice.service';

describe('VoiceService', () => {
  let service: VoiceService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [VoiceService],
    });

    service = TestBed.inject(VoiceService);
  });

  it('endSession disposes realtime resources and resets state', () => {
    const closeDataChannel = vi.fn();
    const closePeerConnection = vi.fn();
    const stopTrack = vi.fn();
    const pauseAudio = vi.fn();
    const removeSrc = vi.fn();

    service.realtimeConnected.set(true);
    service.realtimeMuted.set(true);
    service.setRealtimeResources({
      dataChannel: { close: closeDataChannel } as unknown as RTCDataChannel,
      peerConnection: { close: closePeerConnection } as unknown as RTCPeerConnection,
      mediaStream: {
        getTracks: () => [{ stop: stopTrack } as unknown as MediaStreamTrack],
      } as unknown as MediaStream,
      remoteAudio: { pause: pauseAudio, removeAttribute: removeSrc } as unknown as HTMLAudioElement,
    });

    service.endSession();

    expect(closeDataChannel).toHaveBeenCalled();
    expect(closePeerConnection).toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
    expect(pauseAudio).toHaveBeenCalled();
    expect(removeSrc).toHaveBeenCalledWith('src');
    expect(service.realtimeConnected()).toBe(false);
    expect(service.realtimeMuted()).toBe(false);
  });

  it('ngOnDestroy delegates cleanup to endSession', () => {
    const endSessionSpy = vi.spyOn(service, 'endSession');

    service.ngOnDestroy();

    expect(endSessionSpy).toHaveBeenCalled();
  });
});
