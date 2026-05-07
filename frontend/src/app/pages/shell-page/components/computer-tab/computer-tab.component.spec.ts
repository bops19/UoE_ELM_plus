import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellComputerTabComponent } from './computer-tab.component';

function signalStub<T>(value: T): (() => T) & { set: (next: T) => void } {
  const fn = (() => value) as (() => T) & { set: (next: T) => void };
  fn.set = () => {};
  return fn;
}

describe('ShellComputerTabComponent', () => {
  it('creates and invokes computer run actions', async () => {
    const vm = {
      settingsModelInput: signalStub('gpt-5.4-mini'),
      settingsEffortInput: signalStub('medium'),
      saveSettings: vi.fn(),
      settingsStatus: signalStub(''),
      computerModel: signalStub('computer-use-preview'),
      computerStartUrl: signalStub('https://example.com'),
      computerPrompt: signalStub('open page'),
      startComputerRun: vi.fn(),
      stepComputerRun: vi.fn(),
      closeComputerRun: vi.fn(),
      computerRun: signalStub(null),
      loadUsageHistory: vi.fn(),
      loadModelCatalogRaw: vi.fn(),
      loadingUsageHistory: signalStub(false),
      usageHistory: signalStub(null),
      toolsStatus: signalStub(''),
      modelCatalogRaw: signalStub(null),
    };

    await TestBed.configureTestingModule({
      imports: [ShellComputerTabComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: vm }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellComputerTabComponent);
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    const startRunButton = Array.from(buttons).find((button) => button.textContent?.includes('Start run')) as HTMLButtonElement;
    const refreshUsageButton = Array.from(buttons).find((button) =>
      button.textContent?.includes('Refresh usage history'),
    ) as HTMLButtonElement;

    startRunButton.click();
    refreshUsageButton.click();

    expect(fixture.componentInstance).toBeTruthy();
    expect(vm.startComputerRun).toHaveBeenCalled();
    expect(vm.loadUsageHistory).toHaveBeenCalled();
  });
});
