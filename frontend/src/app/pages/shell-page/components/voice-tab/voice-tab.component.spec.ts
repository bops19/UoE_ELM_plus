import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellVoiceTabComponent } from './voice-tab.component';

function signalStub<T>(value: T): (() => T) & { set: (next: T) => void } {
  const fn = (() => value) as (() => T) & { set: (next: T) => void };
  fn.set = () => {};
  return fn;
}

describe('ShellVoiceTabComponent', () => {
  it('creates and triggers TTS generation action', async () => {
    const vm = {
      isVoiceModeActive: (mode: string) => mode === 'tts',
      ttsModel: signalStub('gpt-4o-mini-tts'),
      onTtsModelChange: vi.fn(),
      ttsVoice: signalStub('alloy'),
      ttsText: signalStub('hello'),
      runTts: vi.fn(),
      ttsAudioUrl: signalStub(''),
      voiceStatus: signalStub(''),
    };

    await TestBed.configureTestingModule({
      imports: [ShellVoiceTabComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: vm }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellVoiceTabComponent);
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    const generateButton = Array.from(buttons).find((button) => button.textContent?.includes('Generate speech')) as HTMLButtonElement;
    generateButton.click();

    expect(fixture.componentInstance).toBeTruthy();
    expect(vm.runTts).toHaveBeenCalled();
  });
});
