import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellUsagePanelComponent } from './usage-panel.component';

function signalStub<T>(value: T): () => T {
  return () => value;
}

describe('ShellUsagePanelComponent', () => {
  it('creates and toggles panel collapse via header action', async () => {
    const vm = {
      usagePanelCollapsed: signalStub(true),
      showTokenHistoryAction: signalStub(false),
      toggleUsagePanel: vi.fn(),
      showTokenHistoryModal: signalStub(false),
      loadingUsage: signalStub(false),
    };

    await TestBed.configureTestingModule({
      imports: [ShellUsagePanelComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: vm }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellUsagePanelComponent);
    fixture.detectChanges();

    const collapseButton = fixture.nativeElement.querySelector('.panel-collapse-btn') as HTMLButtonElement;
    collapseButton.click();

    expect(fixture.componentInstance).toBeTruthy();
    expect(vm.toggleUsagePanel).toHaveBeenCalled();
  });
});
